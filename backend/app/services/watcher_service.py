"""
ASTRA OS — Filesystem Watcher Service
======================================
Monitors registered directories using Watchdog, indexes new/modified files in RAG,
and handles file deletions safely using a soft-delete (missing=1) mechanism.
"""

import os
import asyncio
import logging
import threading
import time
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from app.db import engine
from sqlmodel import Session
from sqlalchemy import text

from app.utils.file_hash import sha256_file
from app.services.document_service import document_service
from app.services.task_logger import create_task_run, complete_task_run, fail_task_run
from app.services.vector_service import vector_service

logger = logging.getLogger(__name__)


class AstraFileHandler(FileSystemEventHandler):
    """Handles file system events with debounce, hashing, and soft-delete."""

    def __init__(self, dir_config: Dict[str, Any], loop: asyncio.AbstractEventLoop):
        self._dir_config = dir_config  # Dict representing the DB row
        self._loop = loop              # Asyncio event loop for thread-safe scheduling
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._debounce_seconds = dir_config.get("debounce_seconds", 2)

        # Parse allowed extensions
        exts_str = dir_config.get("allowed_extensions", "")
        self._allowed_extensions = {
            ext.strip().lower()
            for ext in exts_str.split(",")
            if ext.strip()
        }

    def _is_allowed_ext(self, path: str) -> bool:
        ext = os.path.splitext(path)[1].lower()
        return ext in self._allowed_extensions

    def on_created(self, event):
        if event.is_directory:
            return
        if not self._is_allowed_ext(event.src_path):
            return
        logger.info(f"[Watcher] File created: {event.src_path}")
        self._debounced_index(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        if not self._is_allowed_ext(event.src_path):
            return
        logger.info(f"[Watcher] File modified: {event.src_path}")
        self._debounced_index(event.src_path)

    def on_deleted(self, event):
        if event.is_directory:
            return
        if not self._is_allowed_ext(event.src_path):
            return
        logger.info(f"[Watcher] File deleted: {event.src_path}")
        # Cancel any pending index timers
        if event.src_path in self._debounce_timers:
            self._debounce_timers[event.src_path].cancel()
            del self._debounce_timers[event.src_path]

        # Schedule soft delete in the main asyncio event loop
        asyncio.run_coroutine_threadsafe(
            self._soft_delete(event.src_path), self._loop
        )

    def _debounced_index(self, path: str):
        """Cancel previous timer, start a new one to debounce multiple write events."""
        if path in self._debounce_timers:
            self._debounce_timers[path].cancel()

        timer = threading.Timer(
            self._debounce_seconds,
            lambda: asyncio.run_coroutine_threadsafe(
                self._index_file(path), self._loop
            )
        )
        self._debounce_timers[path] = timer
        timer.start()

    async def _index_file(self, path: str):
        """Hash check -> skip if unchanged -> index via document_service."""
        # Clean up timer reference
        self._debounce_timers.pop(path, None)

        if not os.path.exists(path):
            return

        project_id = self._dir_config["project_id"]
        filename = os.path.basename(path)
        logger.info(f"[Watcher] Indexing file: {path} (project: {project_id})")

        try:
            # 1. Calculate new hash
            new_hash = sha256_file(path)
        except Exception as e:
            logger.error(f"[Watcher] Failed to compute hash for {path}: {e}")
            return

        # 2. Check if file is already in documents registry
        file_id = None
        existing_hash = None
        is_missing = 0
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT file_id, file_hash, missing FROM documents WHERE filename = :path"),
                    {"path": path}
                ).first()
                if row:
                    file_id = row.file_id
                    existing_hash = row.file_hash
                    is_missing = row.missing
        except Exception as e:
            logger.error(f"[Watcher] DB query failed for {path}: {e}")

        # If hash is identical and file is not marked missing, we skip indexing
        if file_id and existing_hash == new_hash and is_missing == 0:
            logger.info(f"[Watcher] File content unchanged, skipping indexing: {path}")
            return

        if not file_id:
            file_id = str(uuid.uuid4())

        # 3. Create background task run log
        task_id = create_task_run(
            task_type="file_watch",
            task_name=f"Watcher Index: {filename}",
            project_id=project_id,
            metadata={"file_path": path, "file_id": file_id}
        )

        start_time = time.time()
        try:
            # Process and index file in ChromaDB
            # Passing project_id from the directory config row!
            success = await document_service.process_and_index_file(
                file_path=path,
                project_id=project_id,
                original_filename=filename,
                file_id=file_id
            )

            if success:
                file_ext = os.path.splitext(filename)[1].lower()
                try:
                    file_size = os.path.getsize(path)
                except Exception:
                    file_size = 0

                # Update or Insert document row in database
                with Session(engine) as session:
                    session.execute(
                        text("""
                            INSERT OR REPLACE INTO documents
                              (file_id, filename, original_name, status, rag_enabled, project_id, chunk_count, uploaded_at, file_type, file_size_bytes, file_hash, missing)
                            VALUES
                              (:file_id, :filename, :original_name, :status, :rag_enabled, :project_id, :chunk_count, :uploaded_at, :file_type, :file_size_bytes, :file_hash, :missing)
                        """),
                        {
                            "file_id": file_id,
                            "filename": path,  # Store absolute path for watched files
                            "original_name": filename,
                            "status": "active",
                            "rag_enabled": 1,
                            "project_id": project_id,
                            "chunk_count": success,
                            "uploaded_at": datetime.utcnow().isoformat(),
                            "file_type": file_ext,
                            "file_size_bytes": file_size,
                            "file_hash": new_hash,
                            "missing": 0
                        }
                    )
                    session.commit()

                duration = int((time.time() - start_time) * 1000)
                if task_id:
                    complete_task_run(
                        task_id=task_id,
                        result_summary=f"Successfully indexed {filename} ({success} chunks)",
                        duration_ms=duration
                    )
                logger.info(f"[Watcher] Successfully indexed file: {path}")
            else:
                duration = int((time.time() - start_time) * 1000)
                if task_id:
                    fail_task_run(
                        task_id=task_id,
                        error="process_and_index_file returned 0 chunks or failed",
                        duration_ms=duration
                    )
                logger.warning(f"[Watcher] Ingestion failed for: {path}")
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            if task_id:
                fail_task_run(
                    task_id=task_id,
                    error=str(e),
                    duration_ms=duration
                )
            logger.error(f"[Watcher] Error indexing file {path}: {e}")

    async def _soft_delete(self, path: str):
        """Mark missing=1, wait 30s, verify, then hard-delete or restore."""
        logger.info(f"[Watcher] File deleted on disk: {path}. Entering soft-delete window.")
        
        # 1. Find the file in database
        file_id = None
        project_id = self._dir_config["project_id"]
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT file_id FROM documents WHERE filename = :path"),
                    {"path": path}
                ).first()
                if row:
                    file_id = row.file_id
        except Exception as e:
            logger.error(f"[Watcher] Soft-delete DB query failed: {e}")

        if not file_id:
            logger.info(f"[Watcher] Deleted file {path} not registered in DB, skipping soft-delete.")
            return

        # 2. Mark missing=1 in DB
        try:
            with Session(engine) as session:
                session.execute(
                    text("UPDATE documents SET missing = 1 WHERE file_id = :fid"),
                    {"fid": file_id}
                )
                session.commit()
            logger.info(f"[Watcher] Marked {path} as missing.")
        except Exception as e:
            logger.error(f"[Watcher] Failed to mark file as missing: {e}")

        # 3. Wait 30 seconds
        await asyncio.sleep(30)

        # 4. Verify if file is still absent
        if os.path.exists(path):
            # File reappeared (e.g., atomic save or sync)
            try:
                with Session(engine) as session:
                    session.execute(
                        text("UPDATE documents SET missing = 0 WHERE file_id = :fid"),
                        {"fid": file_id}
                    )
                    session.commit()
                logger.info(f"[Watcher] File {path} reappeared. Restored registry entry.")
            except Exception as e:
                logger.error(f"[Watcher] Failed to restore missing flag: {e}")
        else:
            # File still absent -> Hard delete from ChromaDB + SQLite
            logger.info(f"[Watcher] File {path} still missing after 30s. Performing hard-delete.")
            task_id = create_task_run(
                task_type="file_watch",
                task_name=f"Watcher Purge: {os.path.basename(path)}",
                project_id=project_id,
                metadata={"file_path": path, "file_id": file_id}
            )
            
            start_time = time.time()
            errors = []
            
            # Delete from ChromaDB
            collection_name = f"project_{project_id}"
            try:
                collection = vector_service.get_collection(collection_name)
                if collection:
                    collection.delete(where={"file_id": {"$eq": file_id}})
                    logger.info(f"[Watcher] Purged chunks for file_id='{file_id}' from vector store.")
            except Exception as e:
                errors.append(f"Vector store purge failed: {e}")
                logger.error(f"[Watcher] Vector store purge failed: {e}")

            # Delete from documents database
            try:
                with Session(engine) as session:
                    session.execute(
                        text("DELETE FROM documents WHERE file_id = :fid"),
                        {"fid": file_id}
                    )
                    session.commit()
                logger.info(f"[Watcher] Deleted document registry row for {path}")
            except Exception as e:
                errors.append(f"DB delete failed: {e}")
                logger.error(f"[Watcher] Failed to delete document from DB: {e}")

            duration = int((time.time() - start_time) * 1000)
            if task_id:
                if errors:
                    fail_task_run(
                        task_id=task_id,
                        error="; ".join(errors),
                        duration_ms=duration
                    )
                else:
                    complete_task_run(
                        task_id=task_id,
                        result_summary=f"Successfully purged {os.path.basename(path)} from index",
                        duration_ms=duration
                    )


class WatcherService:
    """Manages watchdog observers for all watched directories."""

    def __init__(self):
        self._observers: Dict[int, Observer] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start_all(self):
        """Called from lifespan startup. Reads watched_directories, starts observers."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        logger.info("[Watcher] Starting all directory watchers...")
        try:
            with Session(engine) as session:
                rows = session.execute(
                    text("SELECT * FROM watched_directories WHERE enabled = 1")
                ).fetchall()
                dirs = [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f"[Watcher] Failed to read watched_directories table: {e}")
            return

        for dir_config in dirs:
            self._start_observer(dir_config)

    def _start_observer(self, dir_config: Dict[str, Any]):
        dir_id = dir_config["id"]
        path = dir_config["path"]

        if dir_id in self._observers:
            logger.warning(f"[Watcher] Observer already exists for dir_id {dir_id}")
            return

        if not os.path.exists(path):
            logger.error(f"[Watcher] Path does not exist: {path}. Cannot start observer.")
            return

        logger.info(f"[Watcher] Starting observer for {path} (id: {dir_id})")
        try:
            observer = Observer()
            handler = AstraFileHandler(dir_config, self._loop)
            observer.schedule(handler, path=path, recursive=bool(dir_config.get("recursive", 0)))
            observer.start()
            self._observers[dir_id] = observer
        except Exception as e:
            logger.error(f"[Watcher] Failed to start observer for {path}: {e}")

    def stop_all(self):
        """Called from lifespan shutdown. Stops all observers gracefully."""
        logger.info("[Watcher] Stopping all directory watchers...")
        for dir_id, observer in list(self._observers.items()):
            try:
                observer.stop()
                observer.join()
            except Exception as e:
                logger.error(f"[Watcher] Error stopping observer for dir_id {dir_id}: {e}")
        self._observers.clear()
        logger.info("[Watcher] All directory watchers stopped.")

    def add_directory(
        self,
        path: str,
        project_id: str,
        recursive: int = 0,
        allowed_extensions: str = ".pdf,.txt,.md,.docx,.csv,.xlsx,.pptx",
        debounce_seconds: int = 2
    ) -> Dict[str, Any]:
        """Insert DB row + start new observer."""
        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")
        if not os.path.isdir(path):
            raise ValueError(f"Path is not a directory: {path}")

        try:
            with Session(engine) as session:
                result = session.execute(
                    text("""
                        INSERT INTO watched_directories
                          (path, project_id, enabled, recursive, allowed_extensions, debounce_seconds)
                        VALUES
                          (:path, :pid, 1, :rec, :exts, :deb)
                    """),
                    {
                        "path": path,
                        "pid": project_id,
                        "rec": recursive,
                        "exts": allowed_extensions,
                        "deb": debounce_seconds
                    }
                )
                session.commit()
                dir_id = result.lastrowid
        except Exception as e:
            logger.error(f"[Watcher] Failed to insert directory in DB: {e}")
            raise RuntimeError(f"Failed to add watched directory: {e}")

        # Start the observer for the newly added directory
        dir_config = {
            "id": dir_id,
            "path": path,
            "project_id": project_id,
            "enabled": 1,
            "recursive": recursive,
            "allowed_extensions": allowed_extensions,
            "debounce_seconds": debounce_seconds,
            "created_at": datetime.utcnow().isoformat(),
            "last_scan_at": None,
            "file_count": 0
        }
        self._start_observer(dir_config)
        return dir_config

    def remove_directory(self, dir_id: int):
        """Stop observer + delete DB row."""
        # 1. Stop observer
        observer = self._observers.pop(dir_id, None)
        if observer:
            try:
                observer.stop()
                observer.join()
                logger.info(f"[Watcher] Stopped observer for dir_id {dir_id}")
            except Exception as e:
                logger.error(f"[Watcher] Error stopping observer for dir_id {dir_id}: {e}")

        # 2. Delete row
        try:
            with Session(engine) as session:
                session.execute(
                    text("DELETE FROM watched_directories WHERE id = :id"),
                    {"id": dir_id}
                )
                session.commit()
            logger.info(f"[Watcher] Removed directory entry dir_id {dir_id} from DB")
        except Exception as e:
            logger.error(f"[Watcher] Failed to delete directory from DB: {e}")
            raise RuntimeError(f"Failed to remove watched directory: {e}")

    async def scan_now(self, dir_id: int) -> int:
        """Full re-scan: walk directory, hash all files, index new/changed ones, purge missing."""
        try:
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT * FROM watched_directories WHERE id = :id"),
                    {"id": dir_id}
                ).first()
                if not row:
                    raise ValueError(f"Watched directory with ID {dir_id} not found.")
                dir_config = dict(row._mapping)
        except Exception as e:
            logger.error(f"[Watcher] DB query failed for scan: {e}")
            raise

        path = dir_config["path"]
        project_id = dir_config["project_id"]
        recursive = bool(dir_config.get("recursive", 0))
        exts_str = dir_config.get("allowed_extensions", "")
        allowed_extensions = {
            ext.strip().lower()
            for ext in exts_str.split(",")
            if ext.strip()
        }

        if not os.path.exists(path):
            raise FileNotFoundError(f"Path does not exist: {path}")

        logger.info(f"[Watcher] Starting full scan of directory: {path}")

        # 1. Walk directory and collect all files
        found_files = []
        try:
            if recursive:
                for root, _, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.splitext(file_path)[1].lower() in allowed_extensions:
                            found_files.append(os.path.abspath(file_path))
            else:
                for item in os.listdir(path):
                    file_path = os.path.join(path, item)
                    if os.path.isfile(file_path) and os.path.splitext(file_path)[1].lower() in allowed_extensions:
                        found_files.append(os.path.abspath(file_path))
        except Exception as e:
            logger.error(f"[Watcher] Failed to walk directory {path}: {e}")
            raise

        indexed_count = 0
        scanned_file_ids = set()

        # 2. Process and index all found files
        for file_path in found_files:
            filename = os.path.basename(file_path)
            try:
                new_hash = sha256_file(file_path)
            except Exception as e:
                logger.error(f"[Watcher] Scan failed to compute hash for {file_path}: {e}")
                continue

            file_id = None
            existing_hash = None
            is_missing = 0

            # Get document info from DB
            try:
                with Session(engine) as session:
                    row = session.execute(
                        text("SELECT file_id, file_hash, missing FROM documents WHERE filename = :path"),
                        {"path": file_path}
                    ).first()
                    if row:
                        file_id = row.file_id
                        existing_hash = row.file_hash
                        is_missing = row.missing
            except Exception as e:
                logger.error(f"[Watcher] Scan DB check failed for {file_path}: {e}")

            if not file_id:
                file_id = str(uuid.uuid4())

            scanned_file_ids.add(file_id)

            # Skip indexing if hash is unchanged and file is not missing
            if existing_hash == new_hash and is_missing == 0:
                continue

            # Index the file
            success = await document_service.process_and_index_file(
                file_path=file_path,
                project_id=project_id,
                original_filename=filename,
                file_id=file_id
            )

            if success:
                indexed_count += 1
                file_ext = os.path.splitext(filename)[1].lower()
                try:
                    file_size = os.path.getsize(file_path)
                except Exception:
                    file_size = 0

                try:
                    with Session(engine) as session:
                        session.execute(
                            text("""
                                INSERT OR REPLACE INTO documents
                                  (file_id, filename, original_name, status, rag_enabled, project_id, chunk_count, uploaded_at, file_type, file_size_bytes, file_hash, missing)
                                VALUES
                                  (:file_id, :filename, :original_name, :status, :rag_enabled, :project_id, :chunk_count, :uploaded_at, :file_type, :file_size_bytes, :file_hash, :missing)
                            """),
                            {
                                "file_id": file_id,
                                "filename": file_path,
                                "original_name": filename,
                                "status": "active",
                                "rag_enabled": 1,
                                "project_id": project_id,
                                "chunk_count": success,
                                "uploaded_at": datetime.utcnow().isoformat(),
                                "file_type": file_ext,
                                "file_size_bytes": file_size,
                                "file_hash": new_hash,
                                "missing": 0
                            }
                        )
                        session.commit()
                except Exception as e:
                    logger.error(f"[Watcher] Scan failed to save document to DB: {e}")

        # 3. Purge orphaned database entries for files that no longer exist under this directory
        # Find all documents registered for this project where filename starts with directory path
        try:
            with Session(engine) as session:
                # We fetch documents under this directory path
                # To be exact, filename is the absolute file path.
                pattern = path + os.sep
                rows = session.execute(
                    text("SELECT file_id, filename FROM documents WHERE project_id = :pid AND (filename LIKE :pat OR filename = :dir)"),
                    {"pid": project_id, "pat": f"{path}%", "dir": path}
                ).fetchall()
                db_docs = [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f"[Watcher] Failed to fetch documents for purge check: {e}")
            db_docs = []

        purged_count = 0
        for doc in db_docs:
            doc_file_id = doc["file_id"]
            doc_path = doc["filename"]

            # Double check: is this document under our watched directory?
            # Check if it was scanned. If it wasn't scanned and doesn't exist on disk, we purge it.
            if doc_file_id not in scanned_file_ids:
                # Is it actually within this watched directory?
                # Using commonpath is extremely safe.
                try:
                    in_dir = os.path.commonpath([path, doc_path]) == path
                except Exception:
                    in_dir = doc_path.startswith(path)

                if in_dir and not os.path.exists(doc_path):
                    # Purge from ChromaDB
                    collection_name = f"project_{project_id}"
                    try:
                        collection = vector_service.get_collection(collection_name)
                        if collection:
                            collection.delete(where={"file_id": {"$eq": doc_file_id}})
                            logger.info(f"[Watcher] Scan purged chunks for file_id='{doc_file_id}' from vector store.")
                    except Exception as e:
                        logger.error(f"[Watcher] Scan vector store purge failed: {e}")

                    # Delete from SQLite documents
                    try:
                        with Session(engine) as session:
                            session.execute(
                                text("DELETE FROM documents WHERE file_id = :fid"),
                                {"fid": doc_file_id}
                            )
                            session.commit()
                        logger.info(f"[Watcher] Scan deleted document registry row for {doc_path}")
                        purged_count += 1
                    except Exception as e:
                        logger.error(f"[Watcher] Scan DB delete failed: {e}")

        # 4. Update watched_directories metadata
        try:
            with Session(engine) as session:
                session.execute(
                    text("""
                        UPDATE watched_directories
                        SET last_scan_at = :scan_at,
                            file_count = :count
                        WHERE id = :id
                    """),
                    {
                        "scan_at": datetime.utcnow().isoformat(),
                        "count": len(found_files),
                        "id": dir_id
                    }
                )
                session.commit()
        except Exception as e:
            logger.error(f"[Watcher] Failed to update scan metadata: {e}")

        logger.info(f"[Watcher] Scan completed. Scanned: {len(found_files)}, Indexed: {indexed_count}, Purged: {purged_count}")
        return indexed_count


watcher_service = WatcherService()
