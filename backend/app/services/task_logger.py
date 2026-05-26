"""
Central task logging for background_task_runs.
Used by: sleep mode, watcher, scheduler, workflows.
Never duplicate SQL inserts — all background task logging goes through here.
"""
import json
import logging
from app.db import engine
from sqlmodel import Session
from sqlalchemy import text
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def create_task_run(
    task_type: str,
    task_name: str,
    project_id: str = "default",
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Insert a new running task. Returns the row ID."""
    try:
        with Session(engine) as session:
            result = session.execute(
                text("""
                    INSERT INTO background_task_runs
                        (task_type, task_name, status, project_id, metadata, created_at)
                    VALUES (:tt, :tn, 'running', :pid, :meta, datetime('now'))
                """),
                {
                    "tt": task_type,
                    "tn": task_name,
                    "pid": project_id,
                    "meta": json.dumps(metadata) if metadata else None,
                },
            )
            session.commit()
            return result.lastrowid
    except Exception as e:
        logger.error(f"Failed to create task run: {e}")
        return None


def complete_task_run(
    task_id: int,
    result_summary: str,
    duration_ms: Optional[int] = None,
):
    """Mark task as completed."""
    try:
        with Session(engine) as session:
            session.execute(
                text("""
                    UPDATE background_task_runs
                    SET status = 'completed',
                        completed_at = datetime('now'),
                        result_summary = :summary,
                        duration_ms = :dur
                    WHERE id = :tid
                """),
                {"tid": task_id, "summary": result_summary, "dur": duration_ms},
            )
            session.commit()
    except Exception as e:
        logger.error(f"Failed to complete task run {task_id}: {e}")


def fail_task_run(
    task_id: int,
    error: str,
    duration_ms: Optional[int] = None,
):
    """Mark task as failed."""
    try:
        with Session(engine) as session:
            session.execute(
                text("""
                    UPDATE background_task_runs
                    SET status = 'failed',
                        completed_at = datetime('now'),
                        error = :err,
                        duration_ms = :dur
                    WHERE id = :tid
                """),
                {"tid": task_id, "err": error, "dur": duration_ms},
            )
            session.commit()
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as failed: {e}")
