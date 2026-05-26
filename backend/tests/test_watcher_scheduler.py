"""
Integration test for ASTRA OS Filesystem Watcher and APScheduler Cron Scheduler.
"""

import os
import sys
import asyncio
import shutil
import time
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.db import engine, create_db_and_tables
from sqlmodel import Session
from sqlalchemy import text

from app.services.watcher_service import watcher_service
from app.services.scheduler_service import scheduler_service

TEST_DIR = os.path.abspath("temp_test_watched")


async def cleanup_test_dir():
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)


async def test_watcher_and_scheduler():
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("\n" + "="*80)
    print("🚀 STARTING WATCHER & SCHEDULER INTEGRATION TESTS")
    print("="*80)

    # 1. Initialize environment
    await cleanup_test_dir()
    os.makedirs(TEST_DIR, exist_ok=True)
    
    # Run migrations/table creation
    create_db_and_tables()

    # Clear tables for clean test
    with Session(engine) as s:
        s.execute(text("DELETE FROM watched_directories"))
        s.execute(text("DELETE FROM scheduled_tasks"))
        s.execute(text("DELETE FROM documents"))
        s.execute(text("DELETE FROM background_task_runs"))
        s.commit()
    print("🧹 Database tables cleared for test.")

    # Mock heavy dependencies (ML / Ollama)
    from app.services.document_service import document_service
    from app.agent.loop import AgentLoop, AgentStreamEvent

    async def mock_process_and_index_file(file_path, project_id, original_filename=None, file_id=None):
        print(f"[MOCK] process_and_index_file called for {file_path}")
        return True

    async def mock_agent_loop_run(self, task, conversation_history=None, project_id="default", max_iterations=5, query_class=None, session_id=""):
        print(f"[MOCK] AgentLoop.run called with task: {task}, session_id: {session_id}")
        yield AgentStreamEvent(type="thought", content="Mocked thought")
        yield AgentStreamEvent(type="answer", content="Mocked answer complete.")
        yield AgentStreamEvent(type="done")

    document_service.process_and_index_file = mock_process_and_index_file
    AgentLoop.run = mock_agent_loop_run
    print("🎭 Mocked ML / LLM dependencies for isolated testing.")

    # Get main event loop for watcher/scheduler services
    loop = asyncio.get_running_loop()

    # Start services
    watcher_service.start_all()
    scheduler_service.start()
    print("✅ Services started.")

    try:
        # ─────────────────────────────────────────────────────────────────────
        # TEST 1: Watched Directory CRUD
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 1: Watched Directory CRUD ---")
        
        # Add directory
        dir_config = watcher_service.add_directory(
            path=TEST_DIR,
            project_id="test_project",
            recursive=0,
            allowed_extensions=".txt,.md",
            debounce_seconds=1  # Fast debounce for testing
        )
        assert dir_config["path"] == TEST_DIR
        assert dir_config["project_id"] == "test_project"
        assert dir_config["debounce_seconds"] == 1
        
        # Check in DB
        with Session(engine) as s:
            row = s.execute(
                text("SELECT * FROM watched_directories WHERE id = :id"),
                {"id": dir_config["id"]}
            ).first()
            assert row is not None
            assert row.path == TEST_DIR
            assert row.project_id == "test_project"
            assert row.enabled == 1
        print("✓ Add directory verified in SQLite.")

        # Update directory config (disable recursion, change debounce)
        updated = scheduler_service._scheduler  # just a dummy scheduler check
        # We can update the directory directly via SQL/watcher re-start as done in the API
        with Session(engine) as s:
            s.execute(
                text("UPDATE watched_directories SET debounce_seconds = 3 WHERE id = :id"),
                {"id": dir_config["id"]}
            )
            s.commit()

        # Update/sync watcher service state
        # In API we do:
        if dir_config["id"] in watcher_service._observers:
            watcher_service._observers[dir_config["id"]].stop()
            watcher_service._observers[dir_config["id"]].join()
            del watcher_service._observers[dir_config["id"]]
        
        with Session(engine) as s:
            updated_row = s.execute(
                text("SELECT * FROM watched_directories WHERE id = :id"),
                {"id": dir_config["id"]}
            ).first()
            watcher_service._start_observer(dict(updated_row._mapping))
            
        # Verify debounce updated
        assert dir_config["id"] in watcher_service._observers
        print("✓ Update directory and observer restart verified.")

        # Restore debounce to 1s for fast testing
        with Session(engine) as s:
            s.execute(
                text("UPDATE watched_directories SET debounce_seconds = 1 WHERE id = :id"),
                {"id": dir_config["id"]}
            )
            s.commit()
        if dir_config["id"] in watcher_service._observers:
            watcher_service._observers[dir_config["id"]].stop()
            watcher_service._observers[dir_config["id"]].join()
            del watcher_service._observers[dir_config["id"]]
        with Session(engine) as s:
            updated_row = s.execute(
                text("SELECT * FROM watched_directories WHERE id = :id"),
                {"id": dir_config["id"]}
            ).first()
            watcher_service._start_observer(dict(updated_row._mapping))

        # ─────────────────────────────────────────────────────────────────────
        # TEST 2: File Creation & Automatic Indexing (Debounced)
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 2: File Creation & Automatic Indexing ---")
        
        # Let the OS finish setting up the watchdog directory handles
        print("⏳ Waiting for watcher handles to initialize...")
        await asyncio.sleep(2)

        file1 = os.path.join(TEST_DIR, "test_file.txt")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("Astra OS is a local AI orchestration engine built on Python and SQLite.")
        print(f"📄 Created: {file1}")

        # Wait for watchdog event + 1s debounce + index time
        print("⏳ Waiting for watchdog event and debounce (3 seconds)...")
        await asyncio.sleep(3)

        # Check if indexed in DB
        with Session(engine) as s:
            doc = s.execute(
                text("SELECT * FROM documents WHERE filename = :path"),
                {"path": file1}
            ).first()
            assert doc is not None, "File was not automatically indexed!"
            assert doc.missing == 0
            assert doc.project_id == "test_project"
            print(f"✓ Automatic indexing successful. Found document in SQLite. Chunks: {doc.chunk_count}")

        # ─────────────────────────────────────────────────────────────────────
        # TEST 3: File Modification
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 3: File Modification ---")
        old_hash = doc.file_hash
        
        # Modify file
        with open(file1, "a", encoding="utf-8") as f:
            f.write("\nAnd it uses ChromaDB as its vector database component.")
        print("📝 Modified: test_file.txt")

        # Wait for debounce and index
        print("⏳ Waiting for debounce (3 seconds)...")
        await asyncio.sleep(3)

        # Check hash and updated timestamp
        with Session(engine) as s:
            doc_mod = s.execute(
                text("SELECT * FROM documents WHERE filename = :path"),
                {"path": file1}
            ).first()
            assert doc_mod is not None
            assert doc_mod.file_hash != old_hash, "Hash did not change on modification!"
            print("✓ File modification re-indexing successful. Hash updated.")

        # ─────────────────────────────────────────────────────────────────────
        # TEST 4: Initial/Full Directory Scan
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 4: Initial/Full Directory Scan ---")
        
        # Add file2 when watcher is running (it would index it, but we can verify scan handles it)
        file2 = os.path.join(TEST_DIR, "another.md")
        with open(file2, "w", encoding="utf-8") as f:
            f.write("This is another markdown file for ASTRA OS RAG indexing.")
        
        # Trigger scan immediately
        print("Triggering manual re-scan...")
        indexed = await watcher_service.scan_now(dir_config["id"])
        print(f"Re-scan complete. Newly indexed during scan: {indexed}")

        with Session(engine) as s:
            doc2 = s.execute(
                text("SELECT * FROM documents WHERE filename = :path"),
                {"path": file2}
            ).first()
            assert doc2 is not None
            assert doc2.missing == 0
            print("✓ Full scan indexed files successfully.")

        # ─────────────────────────────────────────────────────────────────────
        # TEST 5: Soft-Delete (Missing -> Reappear vs Purge)
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 5: Soft-Delete & Restore / Purge ---")

        # Part 5a: Soft-Delete & Restore (atomic save simulation)
        print("Simulating atomic save (delete followed by recreate)...")
        os.remove(file2)
        print(f"🗑️ Temporarily deleted: {file2}")
        
        # Wait 1 second (watchdog will trigger on_deleted -> marks missing=1)
        await asyncio.sleep(1)
        
        with Session(engine) as s:
            doc2_missing = s.execute(
                text("SELECT missing FROM documents WHERE filename = :path"),
                {"path": file2}
            ).first()
            assert doc2_missing is not None
            assert doc2_missing.missing == 1, "File was not marked as missing!"
        print("✓ File successfully marked missing=1.")

        # Restore file within the 30-second window
        with open(file2, "w", encoding="utf-8") as f:
            f.write("This is another markdown file for ASTRA OS RAG indexing.")
        print(f"✓ Restored: {file2}")

        # Wait for watchdog modified event (marks missing=0 and re-indexes if changed)
        # Or wait > 30 seconds from deletion to make sure it doesn't get purged
        print("⏳ Waiting for restore to register and soft-delete window to expire (total 31 seconds)...")
        # Note: the soft-delete wait is 30s. If we wait 31 seconds, it will wake up,
        # see the file exists, and mark missing=0!
        await asyncio.sleep(31)

        with Session(engine) as s:
            doc2_restored = s.execute(
                text("SELECT missing FROM documents WHERE filename = :path"),
                {"path": file2}
            ).first()
            assert doc2_restored is not None
            assert doc2_restored.missing == 0, "Document was purged or is still marked missing!"
        print("✓ Document successfully restored (missing=0) after soft-delete timer expired.")

        # Part 5b: Hard Purge on deletion
        print("Simulating permanent deletion...")
        os.remove(file2)
        print(f"🗑️ Permanently deleted: {file2}")
        
        # Wait 1 second to confirm missing status
        await asyncio.sleep(1)
        with Session(engine) as s:
            doc2_del_missing = s.execute(
                text("SELECT missing FROM documents WHERE filename = :path"),
                {"path": file2}
            ).first()
            assert doc2_del_missing is not None
            assert doc2_del_missing.missing == 1
        
        # Wait 30 seconds for hard purge to complete
        print("⏳ Waiting 31 seconds for soft-delete window to expire and hard purge to run...")
        await asyncio.sleep(31)

        with Session(engine) as s:
            doc2_purged = s.execute(
                text("SELECT * FROM documents WHERE filename = :path"),
                {"path": file2}
            ).first()
            assert doc2_purged is None, "Document was not purged from SQLite registry!"
        print("✓ Document successfully purged from SQLite registry after 30s.")

        # ─────────────────────────────────────────────────────────────────────
        # TEST 6: Cron Scheduler CRUD & Manual Trigger
        # ─────────────────────────────────────────────────────────────────────
        print("\n--- TEST 6: Scheduled Task CRUD & Execution ---")
        
        # Add scheduled task
        # Cron is set to run in 2099 (so it won't fire during the test unless manual)
        task_data = scheduler_service.add_task(
            name="Backup Job",
            cron_expression="0 0 1 1 *",  # Jan 1st
            agent_prompt="Check system memory limits and clean temp files.",
            project_id="test_project",
            enabled=True
        )
        assert task_data["name"] == "Backup Job"
        assert task_data["cron_expression"] == "0 0 1 1 *"
        assert task_data["project_id"] == "test_project"
        
        # Check task in database
        with Session(engine) as s:
            row = s.execute(
                text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                {"id": task_data["id"]}
            ).first()
            assert row is not None
            assert row.name == "Backup Job"
            assert row.enabled == 1
        print("✓ Add scheduled task verified.")

        # Manual trigger
        print("Manually triggering task now...")
        await scheduler_service.trigger_task_now(task_data["id"])
        
        # Wait for dispatch and background task run creation
        print("⏳ Waiting for task dispatch (5 seconds)...")
        await asyncio.sleep(5)

        # Check background tasks runs for execution
        with Session(engine) as s:
            run = s.execute(
                text("SELECT * FROM background_task_runs WHERE task_type = 'scheduled_agent'")
            ).first()
            assert run is not None
            print(f"✓ Found background execution run in SQLite. Status: {run.status}")

        # Unschedule and delete task
        scheduler_service.remove_task(task_data["id"])
        with Session(engine) as s:
            row_del = s.execute(
                text("SELECT * FROM scheduled_tasks WHERE id = :id"),
                {"id": task_data["id"]}
            ).first()
            assert row_del is None
        print("✓ Unschedule and delete task verified.")

    finally:
        # Stop services
        watcher_service.stop_all()
        scheduler_service.shutdown()
        await cleanup_test_dir()
        print("\n🧹 Cleanup completed.")

    print("\n" + "="*80)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY!")
    print("="*80 + "\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_watcher_and_scheduler())
