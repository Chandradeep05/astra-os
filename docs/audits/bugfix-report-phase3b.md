# Phase 3B — Deep Forensic Audit Report

> **Auditor:** Senior Developer Analysis  
> **Scope:** Every file created or modified across Pre-0, Commit 1, Commit 2, and Commit 3  
> **Date:** 2026-05-21  

---

## Files Audited (22 total)

### Backend — Modified (7)
| File | Lines | Verdict |
|------|-------|---------|
| [db.py](backend/app/db.py) | 279 | ✅ Fixed — `scheduled_tasks` migrated from TEXT→INTEGER PK |
| [main.py](backend/main.py) | 117 | ✅ Clean — lifespan order correct (watcher→scheduler start, scheduler→watcher stop) |
| [ollama.py](backend/app/services/ollama.py) | 292 | ✅ Clean — sleep/wake/warmup methods solid |
| [agent.py](backend/app/api/agent.py) | 720+ | ✅ Clean — sleep/wake/sleep-status endpoints correct |
| [bypasses.py](backend/app/api/bypasses.py) | 605 | ✅ Clean — auto-wake SSE in all 4 bypass paths |
| [loop.py](backend/app/agent/loop.py) | 650+ | ✅ Clean — session_id propagated to all memory calls |
| [memory.py](backend/app/agent/memory.py) | 480+ | ✅ Clean — session_id stored in episodic_memory table |

### Backend — New (7)
| File | Lines | Verdict |
|------|-------|---------|
| [watcher_service.py](backend/app/services/watcher_service.py) | 678 | 🔧 Fixed 2 bugs (see below) |
| [scheduler_service.py](backend/app/services/scheduler_service.py) | 406 | 🔧 Fixed 2 bugs (see below) |
| [task_logger.py](backend/app/services/task_logger.py) | 91 | ✅ Clean |
| [file_hash.py](backend/app/utils/file_hash.py) | 18 | ✅ Clean |
| [watcher.py](backend/app/api/watcher.py) | 212 | ✅ Clean |
| [scheduler.py](backend/app/api/scheduler.py) | 154 | 🔧 Fixed 1 bug (see below) |
| [requirements.txt](backend/requirements.txt) | 56 | ✅ Clean — watchdog≥4.0.0, apscheduler≥3.10.0 present |

### Frontend — Modified (5)
| File | Lines | Verdict |
|------|-------|---------|
| [api.ts](frontend/src/lib/api.ts) | 483 | 🔧 Fixed 1 bug (see below) |
| [page.tsx](frontend/src/app/page.tsx) | 158 | ✅ Clean — all 7 virtual views routed, AstraRuntimeProvider at page level |
| [Sidebar.tsx](frontend/src/components/Sidebar.tsx) | 195+ | ✅ Clean — Calendar icon + "Scheduled Agents" nav item |
| [SettingsPanel.tsx](frontend/src/components/SettingsPanel.tsx) | 600+ | ✅ Clean — Watcher UI + Sleep Mode sections |
| [ChatInterface.tsx](frontend/src/components/ChatInterface.tsx) | 700+ | ✅ Clean — "Waking up" SSE thought display |

### Frontend — New (3)
| File | Lines | Verdict |
|------|-------|---------|
| [ScheduledTasks.tsx](frontend/src/components/ScheduledTasks.tsx) | 280 | ✅ Clean |
| [useAstraRuntime.tsx](frontend/src/hooks/useAstraRuntime.tsx) | 263 | ✅ Clean — proper cleanup on unmount, single polling interval |

---

## Bugs Found & Fixed

### BUG #1 — Missing `Optional` import in `watcher_service.py`
- **Severity:** Runtime crash on import
- **Location:** [watcher_service.py:14](backend/app/services/watcher_service.py#L14)
- **Root Cause:** `Optional` was used for `self._loop` type annotation (line 330) but not imported from `typing`
- **Fix:** Added `Optional` to `from typing import Dict, Any, List, Optional`

### BUG #2 — Missing response fields in `add_directory()`
- **Severity:** HTTP 500 on POST `/api/v1/watcher/directories`
- **Location:** [watcher_service.py:427-437](backend/app/services/watcher_service.py#L427-L440)
- **Root Cause:** The return dict was missing `file_count`, `created_at`, `last_scan_at` — Pydantic's `DirectoryResponse` model requires `file_count: int` which would cause a validation error
- **Fix:** Added `"file_count": 0`, `"created_at": datetime.utcnow().isoformat()`, `"last_scan_at": None` to the return dict

### BUG #3 — Frontend `WatchedDirectory` interface incomplete
- **Severity:** Data loss (missing fields silently dropped)
- **Location:** [api.ts:1-10](frontend/src/lib/api.ts#L1-L12)
- **Root Cause:** Interface was missing `last_scan_at` and `file_count` fields that the backend returns
- **Fix:** Added `last_scan_at?: string` and `file_count?: number` as optional fields

### BUG #4 — `_dispatch_agent_task` was sync, would crash on cron trigger
- **Severity:** Runtime crash when APScheduler fires a cron job
- **Location:** [scheduler_service.py:108](backend/app/services/scheduler_service.py#L108) and [scheduler_service.py:385](backend/app/services/scheduler_service.py#L385)
- **Root Cause:** `_dispatch_agent_task` was a sync method calling `asyncio.get_running_loop()`. `AsyncIOScheduler` runs sync functions in a thread executor where there's no running event loop. Additionally, `trigger_task_now` called this sync method without await.
- **Fix:** Made both `_dispatch_agent_task` and `trigger_task_now` async. Updated the API route handler in [scheduler.py:147](backend/app/api/scheduler.py#L147) and test to use `await`.

### Previously Fixed (from earlier sessions)
- **scheduled_tasks TEXT→INTEGER PK** — `db.py` table had `id TEXT PRIMARY KEY`, causing type affinity mismatch when querying with integer IDs. Fixed to `INTEGER PRIMARY KEY AUTOINCREMENT` with automatic migration.

---

## Verification Results

### 1. Bug Fix Regression Tests (6/6 passed)
```
✅ Optional import is present. WatcherService instantiates correctly.
✅ All required fields present in add_directory response
✅ _dispatch_agent_task is an async method.
✅ trigger_task_now is an async method.
✅ scheduled_tasks.id is INTEGER (correct).
✅ Scheduler CRUD with INTEGER id — create, fetch, delete all work.
```

### 2. Integration Test Suite (6/6 passed)
```
✓ TEST 1: Watched Directory CRUD
✓ TEST 2: File Creation & Automatic Indexing (2s debounce)
✓ TEST 3: File Modification Re-indexing (SHA-256 hash change detection)
✓ TEST 4: Full Directory Scan
✓ TEST 5: Soft-Delete & Restore / Hard Purge (30s window)
✓ TEST 6: Scheduled Task CRUD, Manual Trigger, Background Execution
```

### 3. Frontend TypeScript Compilation
```
npx tsc --noEmit → 0 errors, 0 warnings
```

---

## Architecture Verification Checklist

| Requirement | Status | Evidence |
|------------|--------|----------|
| Watcher debounce = 2s default | ✅ | `debounce_seconds INTEGER NOT NULL DEFAULT 2` in schema |
| AstraRuntimeProvider at page.tsx level | ✅ | Wraps entire `<div>` in page.tsx:34-155 |
| Scheduler starts AFTER watcher | ✅ | main.py:36-37: `watcher_service.start_all()` then `scheduler_service.start()` |
| Scheduler stops BEFORE watcher | ✅ | main.py:44-45: `scheduler_service.shutdown()` then `watcher_service.stop_all()` |
| Every scheduled execution gets unique session_id | ✅ | scheduler_service.py:121: `session_id = str(uuid.uuid4())` |
| project_id from dir_config (not hardcoded "default") | ✅ | watcher_service.py:107: `project_id = self._dir_config["project_id"]` |
| No /api/ps polling for model status | ✅ | Only called once at startup health_check; uses `_model_loaded` flag elsewhere |
| Zombie task recovery on startup | ✅ | db.py:228-241: marks all `status='running'` as `'failed'` on startup |

---

## Verdict

> **Phase 3B is production-ready.** All 4 bugs found during the deep audit have been fixed and verified. Zero TypeScript errors, zero Python import errors, zero schema mismatches. The system is clean.
