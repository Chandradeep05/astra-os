from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlmodel import Session, select
from typing import List, Optional
from app.schemas.workflow import Workflow, WorkflowCreate, WorkflowUpdate
from app.models.workflow import WorkflowModel
from app.db import get_session
from app.agent.loop import AgentLoop
from app.agent.schemas import AgentStreamEvent
from app.services.audit_service import audit_service
from app.services.scheduler_service import scheduler_service
import uuid
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


def _sync_workflow_cron(workflow: WorkflowModel, action: str = "upsert"):
    """
    Bridge between Workflow system and APScheduler.
    When a workflow has trigger_type='scheduled', its trigger_config
    should contain a JSON object with a 'cron' field (5-field cron expression).
    This function registers/updates/removes the corresponding APScheduler job.
    """
    if action == "delete":
        # Always try to remove on delete, regardless of trigger_type
        try:
            scheduler_service.remove_cron_bridge_job(workflow.id)
        except Exception:
            pass
        return

    if workflow.trigger_type != "scheduled":
        return

    # Parse trigger_config for cron expression
    try:
        config = json.loads(workflow.trigger_config or "{}")
        cron_expr = config.get("cron")
        if not cron_expr:
            logger.warning(f"[WorkflowCronBridge] Workflow {workflow.id} has trigger_type=scheduled but no cron in trigger_config")
            return
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[WorkflowCronBridge] Invalid trigger_config for workflow {workflow.id}")
        return

    # Register with scheduler service
    try:
        scheduler_service.register_cron_bridge_job(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            cron_expression=cron_expr,
            project_id=workflow.project_id,
            steps=json.loads(workflow.steps_json or "[]"),
        )
        logger.info(f"[WorkflowCronBridge] Registered cron job for workflow '{workflow.name}' with cron: {cron_expr}")
    except Exception as e:
        logger.error(f"[WorkflowCronBridge] Failed to register cron job for workflow {workflow.id}: {e}")

router = APIRouter()

@router.get("/", response_model=List[Workflow])
async def list_workflows(project_id: Optional[str] = None, session: Session = Depends(get_session)):
    if project_id:
        statement = select(WorkflowModel).where(WorkflowModel.project_id == project_id)
    else:
        statement = select(WorkflowModel)
    
    workflows = session.exec(statement).all()
    return [
        Workflow(
            id=wf.id, name=wf.name, description=wf.description,
            project_id=wf.project_id, type=wf.type, trigger_type=wf.trigger_type,
            trigger_config=wf.trigger_config, status=wf.status,
            last_run=wf.last_run, created_at=wf.created_at,
            steps=json.loads(wf.steps_json or "[]")
        ) for wf in workflows
    ]

@router.post("/", response_model=Workflow)
async def create_workflow(workflow_in: WorkflowCreate, session: Session = Depends(get_session)):
    workflow = WorkflowModel(
        id=str(uuid.uuid4()),
        name=workflow_in.name,
        description=workflow_in.description,
        project_id=workflow_in.project_id,
        type=workflow_in.type,
        trigger_type=workflow_in.trigger_type,
        trigger_config=workflow_in.trigger_config,
        status="active",
        steps_json=json.dumps(workflow_in.steps or []),
        created_at=datetime.utcnow()
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    # Bridge: register APScheduler job if trigger_type=scheduled
    _sync_workflow_cron(workflow, action="upsert")
    return workflow

@router.get("/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str, session: Session = Depends(get_session)):
    workflow = session.get(WorkflowModel, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.steps = json.loads(workflow.steps_json or "[]")
    return workflow

@router.patch("/{workflow_id}", response_model=Workflow)
async def update_workflow(workflow_id: str, workflow_in: WorkflowUpdate, session: Session = Depends(get_session)):
    workflow = session.get(WorkflowModel, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    data = workflow_in.dict(exclude_unset=True)
    if "steps" in data:
        workflow.steps_json = json.dumps(data.pop("steps"))
    
    for key, value in data.items():
        setattr(workflow, key, value)
    
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    # Bridge: update APScheduler job if trigger changed
    _sync_workflow_cron(workflow, action="upsert")
    workflow.steps = json.loads(workflow.steps_json or "[]")
    return workflow

@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, session: Session = Depends(get_session)):
    workflow = session.get(WorkflowModel, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Bridge: remove APScheduler job before deleting
    _sync_workflow_cron(workflow, action="delete")
    session.delete(workflow)
    session.commit()
    return {"status": "success"}

async def run_workflow_task(workflow_id: str, workflow_name: str, project_id: str, steps: list[str]):
    """Background task to execute workflow steps via the AgentLoop (OTPAR)."""
    import asyncio
    await asyncio.to_thread(
        audit_service.log_action,
        "WORKFLOW_EXECUTION",
        f"Starting background workflow: {workflow_name}",
        project_id,
    )

    agent = AgentLoop()  # Uses DEFAULT_MODEL from settings

    try:
        if not steps:
            steps = [f"Automated Task: {workflow_name}"]

        for i, step in enumerate(steps):
            await asyncio.to_thread(
                audit_service.log_action,
                "STEP_START",
                f"Running step {i + 1}: {step}",
                project_id,
            )

            # Drain the async generator — results go to audit log only
            # (no SSE stream in background context)
            try:
                async for event in agent.run(
                    task=step,
                    conversation_history=[],
                    project_id=project_id,
                    max_iterations=5,
                ):
                    # Log answers and errors to audit trail
                    if isinstance(event, AgentStreamEvent):
                        if event.type == "answer" and event.content:
                            await asyncio.to_thread(
                                audit_service.log_action,
                                "STEP_RESULT",
                                f"Step {i + 1} answer: {event.content[:300]}",
                                project_id,
                            )
                        elif event.type == "error" and event.content:
                            await asyncio.to_thread(
                                audit_service.log_action,
                                "STEP_ERROR",
                                f"Step {i + 1} error: {event.content}",
                                project_id,
                            )
            except Exception as step_err:
                await asyncio.to_thread(
                    audit_service.log_action,
                    "STEP_FAILED",
                    f"Step {i + 1} raised exception: {str(step_err)}",
                    project_id,
                )
                # Don't abort the whole workflow on a single step failure
                continue

            await asyncio.to_thread(
                audit_service.log_action,
                "STEP_COMPLETED",
                f"Finished step {i + 1}",
                project_id,
            )

        await asyncio.to_thread(
            audit_service.log_action,
            "WORKFLOW_COMPLETED",
            f"Successfully finished workflow: {workflow_name}",
            project_id,
        )

    except Exception as e:
        await asyncio.to_thread(
            audit_service.log_action,
            "WORKFLOW_ERROR",
            f"Failed workflow {workflow_name}: {str(e)}",
            project_id,
        )

@router.post("/{workflow_id}/trigger")
async def trigger_workflow(
    workflow_id: str, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    workflow = session.get(WorkflowModel, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Pre-parse steps for the background task
    steps = json.loads(workflow.steps_json or "[]")
    
    # 1. Update state
    workflow.last_run = datetime.utcnow()
    session.add(workflow)
    session.commit()
    
    # 2. Add to background queue
    background_tasks.add_task(run_workflow_task, workflow.id, workflow.name, workflow.project_id, steps)
    
    return {"status": "triggered_async", "workflow": workflow.name}
