"""
ASTRA OS — Scheduled Tasks Service
===================================
Manages background recurring tasks (crons) using APScheduler.
Runs tasks on the asyncio event loop without blocking the scheduler thread.
"""

import os
import uuid
import time
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import engine
from sqlmodel import Session
from sqlalchemy import text

from app.agent.loop import AgentLoop
from app.services.task_logger import create_task_run, complete_task_run, fail_task_run

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages APScheduler cron jobs for Astra AI Agent."""

    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None

    def start(self):
        """Called from lifespan startup. Loads enabled tasks from SQLite."""
        if self._scheduler is not None:
            logger.warning("[Scheduler] Service already started.")
            return

        logger.info("[Scheduler] Starting scheduler service...")
        self._scheduler = AsyncIOScheduler()

        try:
            with Session(engine) as session:
                rows = session.execute(
                    text("SELECT * FROM scheduled_tasks WHERE enabled = 1")
                ).fetchall()
                tasks = [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f"[Scheduler] Failed to load tasks from DB: {e}")
            tasks = []

        for task in tasks:
            self._schedule_job(task)

        self._scheduler.start()
        logger.info(f"[Scheduler] Started. Loaded {len(tasks)} scheduled task(s).")

    def shutdown(self):
        """Called from lifespan shutdown. Gracefully shuts down the scheduler."""
        if self._scheduler:
            logger.info("[Scheduler] Shutting down scheduler service...")
            try:
                self._scheduler.shutdown()
            except Exception as e:
                logger.error(f"[Scheduler] Error shutting down scheduler: {e}")
            self._scheduler = None
            logger.info("[Scheduler] Scheduler service shut down.")

    def _schedule_job(self, task: Dict[str, Any]):
        """Schedule a job in APScheduler from database task row."""
        if not self._scheduler:
            return

        job_id = str(task["id"])
        cron = task["cron_expression"]

        # If job already exists, remove it first
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        try:
            trigger = CronTrigger.from_crontab(cron)
            self._scheduler.add_job(
                func=self._dispatch_agent_task,
                trigger=trigger,
                id=job_id,
                args=[task["id"], task["name"], task["agent_prompt"], task["project_id"]],
                replace_existing=True
            )
            logger.info(f"[Scheduler] Scheduled task {job_id} ({task['name']}) with cron: {cron}")
        except Exception as e:
            logger.error(f"[Scheduler] Failed to schedule task {job_id} ({task['name']}): {e}")

    def _unschedule_job(self, task_id: int):
        """Remove a job from APScheduler."""
        if not self._scheduler:
            return
        job_id = str(task_id)
        if self._scheduler.get_job(job_id):
            try:
                self._scheduler.remove_job(job_id)
                logger.info(f"[Scheduler] Unscheduled task {job_id}")
            except Exception as e:
                logger.error(f"[Scheduler] Failed to unschedule task {job_id}: {e}")

    # ── Workflow Cron Bridge ─────────────────────────────────────────────
    # These methods allow workflows with trigger_type=scheduled to register
    # APScheduler jobs. Job IDs are prefixed with "wf_" to avoid collisions
    # with regular scheduled task IDs.

    def register_cron_bridge_job(
        self, workflow_id: str, workflow_name: str,
        cron_expression: str, project_id: str, steps: list
    ):
        """Register an APScheduler cron job for a workflow."""
        if not self._scheduler:
            logger.warning("[WorkflowCronBridge] Scheduler not started, cannot register job")
            return

        job_id = f"wf_{workflow_id}"

        # Remove existing job if any
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        try:
            trigger = CronTrigger.from_crontab(cron_expression)
            self._scheduler.add_job(
                func=self._dispatch_workflow_task,
                trigger=trigger,
                id=job_id,
                args=[workflow_id, workflow_name, project_id, steps],
                replace_existing=True,
            )
            logger.info(f"[WorkflowCronBridge] Registered job {job_id} ({workflow_name}) cron: {cron_expression}")
        except Exception as e:
            logger.error(f"[WorkflowCronBridge] Failed to register job {job_id}: {e}")
            raise ValueError(f"Invalid cron expression: {e}")

    def remove_cron_bridge_job(self, workflow_id: str):
        """Remove the APScheduler cron job for a workflow."""
        if not self._scheduler:
            return
        job_id = f"wf_{workflow_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info(f"[WorkflowCronBridge] Removed job {job_id}")

    async def _dispatch_workflow_task(
        self, workflow_id: str, workflow_name: str, project_id: str, steps: list
    ):
        """APScheduler target for workflow cron bridge. Runs workflow steps via AgentLoop."""
        from app.api.workflows import run_workflow_task
        asyncio.create_task(
            run_workflow_task(workflow_id, workflow_name, project_id, steps)
        )

    async def _dispatch_agent_task(self, task_id: int, name: str, prompt: str, project_id: str):
        """
        APScheduler job target. Dispatches the heavy execution to the async event loop.
        Must be async so AsyncIOScheduler can await it directly on the event loop.
        """
        # Fire-and-forget: create task on the current event loop
        asyncio.create_task(
            self._execute_task_with_timeout(task_id, name, prompt, project_id)
        )

    async def _execute_task_with_timeout(self, task_id: int, name: str, prompt: str, project_id: str):
        """Executes the agent loop for the task with a 30-minute timeout."""
        session_id = str(uuid.uuid4())
        logger.info(f"[Scheduler] Starting scheduled execution: {name} (id: {task_id}, session_id: {session_id})")

        # 1. Create a background task run log
        run_id = create_task_run(
            task_type="scheduled_agent",
            task_name=f"Cron: {name}",
            project_id=project_id,
            metadata={
                "task_id": task_id,
                "session_id": session_id,
                "prompt": prompt
            }
        )

        start_time = time.time()
        timeout_seconds = 1800  # 30 minutes

        try:
            # Ensure model is loaded before executing (OLL013: wake during scheduled job is safe)
            try:
                from app.services.ollama import ollama_service
                await ollama_service.warmup_model()
                logger.info(f"[Scheduler] Model warmed up for task: {name}")
            except Exception as e:
                logger.warning(f"[Scheduler] Model warmup failed (non-fatal): {e}")

            # Wrap execution with wait_for timeout
            result_summary = await asyncio.wait_for(
                self._run_agent(prompt, project_id, session_id),
                timeout=timeout_seconds
            )

            # Update last_run and calculate next_run
            last_run_time = datetime.utcnow().isoformat()
            next_run_time = None
            if self._scheduler:
                job = self._scheduler.get_job(str(task_id))
                if job and job.next_run_time:
                    next_run_time = job.next_run_time.isoformat()

            # Save task execution status in DB
            with Session(engine) as session:
                session.execute(
                    text("""
                        UPDATE scheduled_tasks
                        SET last_run = :last,
                            next_run = :next
                        WHERE id = :id
                    """),
                    {
                        "last": last_run_time,
                        "next": next_run_time,
                        "id": task_id
                    }
                )
                session.commit()

            duration = int((time.time() - start_time) * 1000)
            if run_id:
                complete_task_run(
                    task_id=run_id,
                    result_summary=result_summary[:500],
                    duration_ms=duration
                )
            logger.info(f"[Scheduler] Completed execution for {name} in {duration}ms")

        except asyncio.TimeoutError:
            duration = int((time.time() - start_time) * 1000)
            logger.error(f"[Scheduler] Execution timed out for {name}")
            if run_id:
                fail_task_run(
                    task_id=run_id,
                    error="Execution exceeded 30 minute timeout limit",
                    duration_ms=duration
                )

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            logger.error(f"[Scheduler] Execution failed for {name}: {e}")
            if run_id:
                fail_task_run(
                    task_id=run_id,
                    error=str(e),
                    duration_ms=duration
                )

    async def _run_agent(self, prompt: str, project_id: str, session_id: str) -> str:
        """Run the AgentLoop to completion and collect output answers."""
        loop = AgentLoop()
        output_parts = []
        try:
            # We run the OTPAR loop with the unique session_id to isolate memory
            async for event in loop.run(
                task=prompt,
                project_id=project_id,
                session_id=session_id
            ):
                if event.type == "answer" and event.content:
                    output_parts.append(event.content)
                elif event.type == "error" and event.content:
                    output_parts.append(f"\n[Error: {event.content}]")

            answer = "".join(output_parts).strip()
            return answer if answer else "No answer returned by agent loop."
        except Exception as e:
            logger.error(f"[Scheduler] AgentLoop execution crashed: {e}")
            raise

    # ── CRUD Operations called by API endpoints ─────────────────────────────

    def add_task(
        self,
        name: str,
        cron_expression: str,
        agent_prompt: str,
        project_id: str = "default",
        enabled: bool = True
    ) -> Dict[str, Any]:
        """Inserts task into database and schedules it if enabled."""
        # Simple validation
        try:
            CronTrigger.from_crontab(cron_expression)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {e}")

        created_at = datetime.utcnow().isoformat()
        try:
            with Session(engine) as session:
                result = session.execute(
                    text("""
                        INSERT INTO scheduled_tasks
                          (name, cron_expression, agent_prompt, project_id, enabled, created_at)
                        VALUES
                          (:name, :cron, :prompt, :pid, :enabled, :created)
                    """),
                    {
                        "name": name,
                        "cron": cron_expression,
                        "prompt": agent_prompt,
                        "pid": project_id,
                        "enabled": 1 if enabled else 0,
                        "created": created_at
                    }
                )
                session.commit()
                task_id = result.lastrowid
        except Exception as e:
            logger.error(f"[Scheduler] Failed to insert scheduled task: {e}")
            raise RuntimeError(f"Database error: {e}")

        task = {
            "id": task_id,
            "name": name,
            "cron_expression": cron_expression,
            "agent_prompt": agent_prompt,
            "project_id": project_id,
            "enabled": enabled,
            "created_at": created_at,
            "last_run": None,
            "next_run": None
        }

        if enabled:
            self._schedule_job(task)

        # Get next run time
        if self._scheduler and enabled:
            job = self._scheduler.get_job(str(task_id))
            if job and job.next_run_time:
                task["next_run"] = job.next_run_time.isoformat()

        return task

    def remove_task(self, task_id: int):
        """Unschedule from APScheduler and delete from SQLite."""
        self._unschedule_job(task_id)

        try:
            with Session(engine) as session:
                session.execute(
                    text("DELETE FROM scheduled_tasks WHERE id = :id"),
                    {"id": task_id}
                )
                session.commit()
        except Exception as e:
            logger.error(f"[Scheduler] Failed to delete task {task_id} from DB: {e}")
            raise RuntimeError(f"Database error: {e}")

    def update_task(self, task_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update task settings in database, then update scheduler config."""
        # 1. Fetch current task
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                    {"id": task_id}
                ).first()
                if not row:
                    raise ValueError(f"Scheduled task {task_id} not found.")
                task = dict(row._mapping)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to fetch task {task_id} on update: {e}")
            raise

        # 2. Validate cron expression if updated
        if "cron_expression" in updates:
            try:
                CronTrigger.from_crontab(updates["cron_expression"])
            except Exception as e:
                raise ValueError(f"Invalid cron expression: {e}")

        # 3. Apply updates to SQLite
        set_clauses = [f"{k} = :{k}" for k in updates.keys()]
        query = f"UPDATE scheduled_tasks SET {', '.join(set_clauses)} WHERE id = :id"
        updates["id"] = task_id

        try:
            with Session(engine) as session:
                session.execute(text(query), updates)
                session.commit()
        except Exception as e:
            logger.error(f"[Scheduler] Failed to update task {task_id} in DB: {e}")
            raise RuntimeError(f"Database error: {e}")

        # 4. Fetch updated task config
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                    {"id": task_id}
                ).first()
                updated_task = dict(row._mapping)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to load updated task {task_id}: {e}")
            raise

        # Convert bools for SQLite INTEGER
        updated_task["enabled"] = bool(updated_task["enabled"])

        # 5. Sync with APScheduler
        if updated_task["enabled"]:
            self._schedule_job(updated_task)
            # Update next_run column in SQLite
            if self._scheduler:
                job = self._scheduler.get_job(str(task_id))
                if job and job.next_run_time:
                    next_run_val = job.next_run_time.isoformat()
                    try:
                        with Session(engine) as session:
                            session.execute(
                                text("UPDATE scheduled_tasks SET next_run = :next WHERE id = :id"),
                                {"next": next_run_val, "id": task_id}
                            )
                            session.commit()
                        updated_task["next_run"] = next_run_val
                    except Exception as e:
                        logger.error(f"[Scheduler] Failed to update next_run in DB: {e}")
        else:
            self._unschedule_job(task_id)
            try:
                with Session(engine) as session:
                    session.execute(
                        text("UPDATE scheduled_tasks SET next_run = NULL WHERE id = :id"),
                        {"id": task_id}
                    )
                    session.commit()
                updated_task["next_run"] = None
            except Exception as e:
                logger.error(f"[Scheduler] Failed to nullify next_run: {e}")

        return updated_task

    async def trigger_task_now(self, task_id: int):
        """Trigger execution immediately in the background."""
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                    {"id": task_id}
                ).first()
                if not row:
                    raise ValueError(f"Task with ID {task_id} not found.")
                task = dict(row._mapping)
        except Exception as e:
            logger.error(f"[Scheduler] Failed to read task {task_id} for manual trigger: {e}")
            raise

        # Trigger on async event loop
        await self._dispatch_agent_task(task["id"], task["name"], task["agent_prompt"], task["project_id"])
        logger.info(f"[Scheduler] Manually triggered task {task_id} ({task['name']})")


scheduler_service = SchedulerService()
