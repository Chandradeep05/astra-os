"""
ASTRA OS — Scheduled Tasks API Router
=====================================
Defines endpoints for CRUD operations and manual triggering of recurring agent tasks.
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import engine
from sqlmodel import Session
from sqlalchemy import text
from app.services.scheduler_service import scheduler_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Schemas ───────────────────────────────────────────────

class TaskAddRequest(BaseModel):
    name: str = Field(..., description="Descriptive name of the cron task")
    cron_expression: str = Field(..., description="Standard 5-field cron expression")
    agent_prompt: str = Field(..., description="The prompt the agent will execute recursively")
    project_id: str = Field("default", description="RAG project ID context")
    enabled: bool = Field(True, description="Whether this task is active")


class TaskUpdateRequest(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    agent_prompt: Optional[str] = None
    project_id: Optional[str] = None
    enabled: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    name: str
    cron_expression: str
    agent_prompt: str
    project_id: str
    enabled: bool
    created_at: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks():
    """List all registered scheduled tasks."""
    try:
        with Session(engine) as session:
            rows = session.execute(
                text("SELECT * FROM scheduled_tasks ORDER BY id ASC")
            ).fetchall()
            
            tasks = []
            for r in rows:
                t = dict(r._mapping)
                t["enabled"] = bool(t.get("enabled", 1))
                tasks.append(t)
            return tasks
    except Exception as e:
        logger.error(f"Failed to list scheduled tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/tasks", response_model=TaskResponse)
async def add_task(req: TaskAddRequest):
    """Add a new scheduled task and schedule it if enabled."""
    try:
        task = scheduler_service.add_task(
            name=req.name,
            cron_expression=req.cron_expression,
            agent_prompt=req.agent_prompt,
            project_id=req.project_id,
            enabled=req.enabled
        )
        return task
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to add scheduled task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, req: TaskUpdateRequest):
    """Update settings (cron expression, prompt, enabled) of a scheduled task."""
    try:
        # Check if exists
        with Session(engine) as session:
            existing = session.execute(
                text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                {"id": task_id}
            ).first()
            if not existing:
                raise HTTPException(status_code=404, detail="Scheduled task not found")
            existing_dict = dict(existing._mapping)

        # Build updates dictionary
        updates = {}
        if req.name is not None:
            updates["name"] = req.name
        if req.cron_expression is not None:
            updates["cron_expression"] = req.cron_expression
        if req.agent_prompt is not None:
            updates["agent_prompt"] = req.agent_prompt
        if req.project_id is not None:
            updates["project_id"] = req.project_id
        if req.enabled is not None:
            updates["enabled"] = int(req.enabled)

        if not updates:
            existing_dict["enabled"] = bool(existing_dict["enabled"])
            return existing_dict

        updated = scheduler_service.update_task(task_id, updates)
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update scheduled task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    """Remove a scheduled task. Cancels any active scheduler timers."""
    try:
        scheduler_service.remove_task(task_id)
        return {"status": "success", "message": f"Deleted scheduled task with ID {task_id}"}
    except Exception as e:
        logger.error(f"Failed to remove scheduled task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/{task_id}/trigger")
async def trigger_task(task_id: int):
    """Trigger the scheduled task immediately in the background."""
    try:
        await scheduler_service.trigger_task_now(task_id)
        return {"status": "success", "message": f"Manually triggered scheduled task with ID {task_id}"}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to manually trigger task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def scheduler_status():
    """Returns the current scheduler runtime state: running, job_count, next_fire_time."""
    try:
        sched = scheduler_service._scheduler
        if sched is None:
            return {"running": False, "job_count": 0, "next_fire_time": None}

        running = sched.running
        jobs = sched.get_jobs()
        job_count = len(jobs)

        # Find the earliest next fire time across all jobs
        next_fire = None
        for job in jobs:
            if job.next_run_time is not None:
                t = job.next_run_time.isoformat()
                if next_fire is None or t < next_fire:
                    next_fire = t

        return {
            "running": running,
            "job_count": job_count,
            "next_fire_time": next_fire,
        }
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
