"""
ASTRA OS — Documents API
==========================
Endpoints:
  POST /upload                   — Upload and index document (background task)
  GET  /list/{project_id}        — List all documents for a project
  GET  /status/{file_id}         — Get ingestion status for a document
  DELETE /{file_id}              — Delete document + purge all chunks from vector store
  PATCH /toggle/{file_id}        — Enable/disable document from RAG retrieval
  GET  /download/{filename}      — Download exported document
  GET  /preview/{file_id}        — Preview uploaded file
  GET  /ingestion-stream/{file_id} — SSE stream of ingestion progress
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from app.services.document_service import document_service
from app.services.vector_service import vector_service
from app.services.audit_service import audit_service
import os
import shutil
import logging
import asyncio
import json
import uuid
import time
from typing import Dict
from app.db import engine
from sqlmodel import Session
from sqlalchemy import text
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# ── In-memory ingestion status registry ──────────────────────────────────────
# Tracks ingestion progress per file_id for SSE streaming.
# Format: { file_id: { "status": str, "stage": str, "chunks": int, "error": str } }
_ingestion_status: Dict[str, dict] = {}


def _set_status(file_id: str, status: str, stage: str, chunks: int = 0, error: str = ""):
    _ingestion_status[file_id] = {
        "status": status,   # "pending" | "processing" | "done" | "error"
        "stage": stage,     # human-readable stage description
        "chunks": chunks,
        "error": error,
        "timestamp": time.time(),
    }


# ── In-memory document registry ───────────────────────────────────────────────
# Migrated to SQLite (C1 Fix)
# STUB: Kept as empty dict for backward compatibility with old imports
_documents: Dict[str, dict] = {}


# ── Background task: parse, embed, index ─────────────────────────────────────

async def _background_parse_and_index(
    file_path: str,
    project_id: str,
    file_name: str,
    file_id: str,
):
    try:
        _set_status(file_id, "processing", "Parsing document...")

        success = await document_service.process_and_index_file(
            file_path,
            project_id,
            original_filename=file_name,
            file_id=file_id,  # ASTRA-FIX-2: UUID for unique delete targeting
        )

        if success:
            _set_status(file_id, "done", "Indexed and ready", chunks=0)
            logger.info(f"✅ Background indexing completed: {file_name}")
            await asyncio.to_thread(
                audit_service.log_action,
                "FILE_INGESTION",
                f"Successfully indexed: {file_name} (ID: {file_id})",
                project_id,
            )
            # Insert into SQLite with deduplication (Fix #4)
            with Session(engine) as session:
                # Remove any existing rows with the same name/project before inserting new one
                session.execute(
                    text("DELETE FROM documents WHERE LOWER(original_name) = LOWER(:name) AND project_id = :pid"),
                    {"name": file_name, "pid": project_id}
                )
                session.commit()

            with Session(engine) as session:
                session.execute(
                    text("""
                        INSERT OR REPLACE INTO documents
                          (file_id, filename, original_name, status, rag_enabled, project_id, chunk_count, uploaded_at)
                        VALUES
                          (:file_id, :filename, :original_name, :status, :rag_enabled, :project_id, :chunk_count, :uploaded_at)
                    """),
                    {
                        "file_id": file_id,
                        "filename": file_id + os.path.splitext(file_name)[1],
                        "original_name": file_name,
                        "status": "active",
                        "rag_enabled": 1,
                        "project_id": project_id,
                        "chunk_count": 0,
                        "uploaded_at": datetime.utcnow().isoformat()
                    }
                )
                session.commit()
        else:
            _set_status(file_id, "error", "Indexing returned False", error="process_and_index_file returned False")
            logger.warning(f"⚠️ Indexing returned False for: {file_name}")

    except Exception as e:
        _set_status(file_id, "error", "Indexing failed", error=str(e))
        logger.error(f"❌ Background indexing failed for {file_name}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/upload-test")
async def upload_test():
    return {"status": "reached"}


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Form("default"),
):
    try:
        logger.info(f"🚀 ENTERED /upload handled for {file.filename}")

        from app.core.config import settings
        content = await file.read()
        max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_size:
            raise HTTPException(413, f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB.")

        # Save file with UUID name, track original name separately
        file_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1]
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_extension}")

        def save_file_to_disk():
            with open(file_path, "wb") as f:
                f.write(content)

        await asyncio.to_thread(save_file_to_disk)

        # Removed in-memory _documents assignment; done after indexing in DB.

        # Set initial status
        _set_status(file_id, "pending", "Queued for indexing...")

        # Queue background indexing
        background_tasks.add_task(
            _background_parse_and_index,
            file_path,
            project_id,
            file.filename,
            file_id,
        )

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "file_id": file_id,
                "filename": file.filename,
                "project_id": project_id,
                "message": "Document uploaded. Indexing started — stream progress at /documents/ingestion-stream/{file_id}",
                "stream_url": f"/api/v1/documents/ingestion-stream/{file_id}",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingestion-stream/{file_id}")
async def ingestion_stream(file_id: str):
    """
    SSE stream for document ingestion progress.
    Frontend polls this after upload to show: Queued → Parsing → Indexing → Done.
    Stream closes automatically when status reaches "done" or "error".
    """
    async def event_generator():
        max_wait_seconds = 300  # 5 minute timeout
        start = time.time()

        while True:
            status_data = _ingestion_status.get(file_id)

            if status_data:
                yield f"data: {json.dumps(status_data)}\n\n"
                if status_data["status"] in ("done", "error"):
                    break
            else:
                yield f"data: {json.dumps({'status': 'pending', 'stage': 'Waiting for worker...'})}\n\n"

            if time.time() - start > max_wait_seconds:
                yield f"data: {json.dumps({'status': 'error', 'stage': 'Timeout waiting for indexing'})}\n\n"
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status/{file_id}")
async def get_ingestion_status(file_id: str):
    """Poll-based alternative to SSE for ingestion progress."""
    status_data = _ingestion_status.get(file_id)
    if not status_data:
        raise HTTPException(404, f"No ingestion record found for file_id: {file_id}")
    return status_data


@router.get("/list/{project_id}")
async def list_documents(project_id: str):
    """List all documents for a project with their RAG enabled state."""
    with Session(engine) as session:
        rows = session.execute(
            text("SELECT * FROM documents WHERE project_id = :pid"),
            {"pid": project_id}
        )
        docs = [dict(r._mapping) for r in rows.fetchall()]
        
    return {
        "project_id": project_id,
        "count": len(docs),
        "documents": docs,
    }


@router.patch("/toggle/{file_id}")
async def toggle_rag_enabled(file_id: str, enabled: bool):
    """
    Enable or disable a document from RAG retrieval without deleting it.
    When disabled: chunks remain in vector store but document is excluded
    from search results via metadata filter.
    """
    with Session(engine) as session:
        row = session.execute(
            text("SELECT original_name FROM documents WHERE file_id = :fid"),
            {"fid": file_id}
        ).first()
        if not row:
            raise HTTPException(404, f"Document {file_id} not found.")
            
        session.execute(
            text("UPDATE documents SET rag_enabled = :enabled WHERE file_id = :fid"),
            {"fid": file_id, "enabled": 1 if enabled else 0}
        )
        session.commit()
        filename = row.original_name

    action = "enabled" if enabled else "disabled"

    return {
        "file_id": file_id,
        "filename": filename,
        "rag_enabled": enabled,
        "message": f"Document {action} for RAG retrieval.",
    }


@router.delete("/{file_id}")
async def delete_document(file_id: str):
    """
    Delete a document and PURGE all its chunks from ChromaDB.
    This is the correct deletion behavior — orphaned chunks break RAG quality.
    """
    with Session(engine) as session:
        row = session.execute(
            text("SELECT filename, original_name, project_id FROM documents WHERE file_id = :fid"),
            {"fid": file_id}
        ).first()
        
        if not row:
            raise HTTPException(404, f"Document {file_id} not found.")
            
        filename = row.filename
        original_name = row.original_name
        project_id = row.project_id

    errors = []

    # 1. Delete the physical file
    file_path = os.path.join(UPLOAD_DIR, filename)
    if file_path and os.path.exists(file_path):
        try:
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"🗑️  Deleted file: {file_path}")
        except Exception as e:
            errors.append(f"File delete failed: {e}")
            logger.error(f"Failed to delete file {file_path}: {e}")

    # 2. Purge ALL chunks from ChromaDB for this file_id
    # ASTRA-FIX-2: Use the UUID file_id (same value stored in chunk metadata)
    # instead of filename stem. This prevents duplicate-filename collisions.
    collection_name = f"project_{project_id}"

    try:
        collection = vector_service.get_collection(collection_name)
        if collection:
            # ChromaDB where filter: delete all chunks where file_id matches UUID
            collection.delete(where={"file_id": {"$eq": file_id}})
            logger.info(f"🗑️  Purged chunks for file_id='{file_id}' from '{collection_name}'")
    except Exception as e:
        errors.append(f"Vector store purge failed: {e}")
        logger.error(f"Failed to purge chunks for {file_id}: {e}")

    # 3. Remove from status and registry
    _ingestion_status.pop(file_id, None)
    
    with Session(engine) as session:
        session.execute(
            text("DELETE FROM documents WHERE file_id = :fid"),
            {"fid": file_id}
        )
        session.commit()

    if errors:
        return {
            "file_id": file_id,
            "deleted": True,
            "warnings": errors,
            "message": "Document deleted with some errors. Check server logs.",
        }

    return {
        "file_id": file_id,
        "deleted": True,
        "message": f"Document '{original_name}' and all its vector chunks deleted.",
    }


@router.get("/download/{filename}")
async def download_document(filename: str):
    """Download a generated document from the exports directory."""
    export_dir = os.path.join(os.getcwd(), "exports")

    safe_filename = os.path.basename(filename)
    file_path = os.path.join(export_dir, safe_filename)

    if not os.path.realpath(file_path).startswith(os.path.realpath(export_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document not found")

    await asyncio.to_thread(
        audit_service.log_action,
        "FILE_DOWNLOAD",
        f"Downloaded: {safe_filename}",
        "default",
    )

    return FileResponse(path=file_path, filename=safe_filename)


@router.get("/preview/{file_id}")
async def preview_document(file_id: str):
    """Serve an uploaded file for previewing (e.g., images)."""
    safe_file_id = os.path.basename(file_id)
    for filename in os.listdir(UPLOAD_DIR):
        if filename.startswith(safe_file_id):
            file_path = os.path.join(UPLOAD_DIR, filename)
            if os.path.realpath(file_path).startswith(os.path.realpath(UPLOAD_DIR)):
                return FileResponse(file_path)

    raise HTTPException(status_code=404, detail="File preview not found")
