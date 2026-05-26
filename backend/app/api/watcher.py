"""
ASTRA OS — Filesystem Watcher API Router
========================================
Defines endpoints for managing watched directories and triggering scans.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.db import engine
from sqlmodel import Session
from sqlalchemy import text
from app.services.watcher_service import watcher_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response Schemas ───────────────────────────────────────────────

class DirectoryAddRequest(BaseModel):
    path: str = Field(..., description="Absolute path to the directory to watch")
    project_id: str = Field("default", description="RAG project association ID")
    recursive: bool = Field(False, description="Watch subdirectories recursively")
    allowed_extensions: str = Field(
        ".pdf,.txt,.md,.docx,.csv,.xlsx,.pptx",
        description="Comma-separated file extensions to watch"
    )
    debounce_seconds: int = Field(2, ge=0, le=60, description="Debounce timer in seconds")


class DirectoryUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    recursive: Optional[bool] = None
    allowed_extensions: Optional[str] = None
    debounce_seconds: Optional[int] = Field(None, ge=0, le=60)


class DirectoryResponse(BaseModel):
    id: int
    path: str
    project_id: str
    enabled: bool
    recursive: bool
    allowed_extensions: str
    debounce_seconds: int
    created_at: Optional[str] = None
    last_scan_at: Optional[str] = None
    file_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/directories", response_model=List[DirectoryResponse])
async def list_directories():
    """List all registered watched directories."""
    try:
        with Session(engine) as session:
            rows = session.execute(
                text("SELECT * FROM watched_directories ORDER BY id ASC")
            ).fetchall()
            
            # Map database rows to list of dicts for Pydantic serialization
            dirs = []
            for r in rows:
                d = dict(r._mapping)
                # Convert SQLite INTEGER (0/1) to boolean
                d["enabled"] = bool(d.get("enabled", 1))
                d["recursive"] = bool(d.get("recursive", 0))
                dirs.append(d)
            return dirs
    except Exception as e:
        logger.error(f"Failed to list directories: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/directories", response_model=DirectoryResponse)
async def add_directory(req: DirectoryAddRequest, background_tasks: BackgroundTasks):
    """Register a new directory for filesystem watching and trigger an initial scan."""
    try:
        # 1. Add via watcher service
        dir_config = watcher_service.add_directory(
            path=req.path,
            project_id=req.project_id,
            recursive=int(req.recursive),
            allowed_extensions=req.allowed_extensions,
            debounce_seconds=req.debounce_seconds
        )
        
        # 2. Trigger an initial scan in the background to index existing files
        background_tasks.add_task(watcher_service.scan_now, dir_config["id"])
        
        # Convert response fields
        dir_config["enabled"] = bool(dir_config["enabled"])
        dir_config["recursive"] = bool(dir_config["recursive"])
        return dir_config
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to add directory: {e}")
        raise HTTPException(status_code=500, detail=f"Error registering directory: {str(e)}")


@router.put("/directories/{dir_id}", response_model=DirectoryResponse)
async def update_directory(dir_id: int, req: DirectoryUpdateRequest):
    """Update settings (enabled/disabled, filters, debounce) of a watched directory."""
    try:
        # Check if exists
        with Session(engine) as session:
            existing = session.execute(
                text("SELECT * FROM watched_directories WHERE id = :id"),
                {"id": dir_id}
            ).first()
            if not existing:
                raise HTTPException(status_code=404, detail="Watched directory not found")
            
            existing_dict = dict(existing._mapping)

        # Build update updates
        updates = {}
        if req.enabled is not None:
            updates["enabled"] = int(req.enabled)
        if req.recursive is not None:
            updates["recursive"] = int(req.recursive)
        if req.allowed_extensions is not None:
            updates["allowed_extensions"] = req.allowed_extensions
        if req.debounce_seconds is not None:
            updates["debounce_seconds"] = req.debounce_seconds

        if not updates:
            # Nothing to update, return current state
            existing_dict["enabled"] = bool(existing_dict["enabled"])
            existing_dict["recursive"] = bool(existing_dict["recursive"])
            return existing_dict

        # Apply database update
        set_clauses = [f"{k} = :{k}" for k in updates.keys()]
        query = f"UPDATE watched_directories SET {', '.join(set_clauses)} WHERE id = :id"
        updates["id"] = dir_id

        with Session(engine) as session:
            session.execute(text(query), updates)
            session.commit()

        # Fetch updated configuration
        with Session(engine) as session:
            updated = session.execute(
                text("SELECT * FROM watched_directories WHERE id = :id"),
                {"id": dir_id}
            ).first()
            updated_dict = dict(updated._mapping)

        # Restart observer with new settings
        # First, remove it if it exists
        if dir_id in watcher_service._observers:
            try:
                watcher_service._observers[dir_id].stop()
                watcher_service._observers[dir_id].join()
                del watcher_service._observers[dir_id]
            except Exception as e:
                logger.error(f"Failed to stop observer on update: {e}")

        # Restart observer if enabled
        if updated_dict.get("enabled", 1):
            watcher_service._start_observer(updated_dict)

        updated_dict["enabled"] = bool(updated_dict["enabled"])
        updated_dict["recursive"] = bool(updated_dict["recursive"])
        return updated_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update directory {dir_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/directories/{dir_id}")
async def delete_directory(dir_id: int):
    """Remove a watched directory. Does NOT delete files, just stops watching."""
    try:
        watcher_service.remove_directory(dir_id)
        return {"status": "success", "message": f"Stopped watching directory with ID {dir_id}"}
    except Exception as e:
        logger.error(f"Failed to remove directory {dir_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/directories/{dir_id}/scan")
async def scan_directory(dir_id: int, background_tasks: BackgroundTasks):
    """Trigger an immediate full re-scan of the directory in the background."""
    try:
        # Verify directory exists
        with Session(engine) as session:
            row = session.execute(
                text("SELECT id FROM watched_directories WHERE id = :id"),
                {"id": dir_id}
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Watched directory not found")

        # Queue scan in background
        background_tasks.add_task(watcher_service.scan_now, dir_id)
        return {"status": "accepted", "message": "Directory scan triggered."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger scan for directory {dir_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
