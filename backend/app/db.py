from sqlmodel import SQLModel, create_engine, Session, select
from app.core.config import settings
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# SQLite needs check_same_thread=False for FastAPI async
# and WAL mode for concurrent writes.
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

from sqlalchemy import pool
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args=connect_args,
    poolclass=pool.QueuePool if not settings.DATABASE_URL.startswith("sqlite") else pool.NullPool
)

if settings.DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_db_and_tables():
    # Import models so SQLModel knows about them
    from app.models.project import ProjectModel
    from app.models.workflow import WorkflowModel
    from app.models.audit import AuditLogModel
    from app.models.user import UserModel
    
    # 1. Create base tables
    SQLModel.metadata.create_all(engine)

    # 2. Manual Migration: Add history_json column if it doesn't exist
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE projectmodel ADD COLUMN history_json TEXT DEFAULT '[]'"))
            conn.commit()
            logger.info("Database schema patched (history_json added).")
        except Exception:
            pass

    # 3. Manual Migration: Add steps_json column if it doesn't exist
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE workflowmodel ADD COLUMN steps_json TEXT DEFAULT '[]'"))
            conn.commit()
            logger.info("Database schema patched (steps_json added).")
        except Exception:
            pass

    # C1 fix: documents registry table
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS documents (
                    file_id     TEXT PRIMARY KEY,
                    filename    TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'indexed',
                    rag_enabled INTEGER NOT NULL DEFAULT 1,
                    project_id  TEXT NOT NULL DEFAULT 'default',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    uploaded_at TEXT NOT NULL,
                    file_type   TEXT,
                    file_size_bytes INTEGER
                )
            """))
            conn.commit()
            logger.info("Documents registry table initialized.")
        except Exception as e:
            logger.error(f"Error creating documents table: {e}")

    # Phase 2 manual migration: Add columns to documents table if they don't exist
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE documents ADD COLUMN file_type TEXT"))
            conn.commit()
            logger.info("Database schema patched: added file_type column to documents.")
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE documents ADD COLUMN file_size_bytes INTEGER"))
            conn.commit()
            logger.info("Database schema patched: added file_size_bytes column to documents.")
        except Exception:
            pass

    # Phase 2: Episodic memory table — persistent task history
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    id              TEXT PRIMARY KEY,
                    task            TEXT NOT NULL,
                    tools_used      TEXT NOT NULL DEFAULT '[]',
                    success         INTEGER NOT NULL DEFAULT 0,
                    summary         TEXT NOT NULL DEFAULT '',
                    project_id      TEXT NOT NULL DEFAULT 'default',
                    importance      INTEGER NOT NULL DEFAULT 1,
                    session_id      TEXT NOT NULL DEFAULT '',
                    access_count    INTEGER NOT NULL DEFAULT 0,
                    last_accessed   TEXT,
                    created_at      TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_episodic_project
                    ON episodic_memory(project_id)
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_episodic_created
                    ON episodic_memory(created_at DESC)
            """))
            conn.commit()
            logger.info("Episodic memory table initialized.")
        except Exception as e:
            logger.error(f"Error creating episodic_memory table: {e}")

    # Phase 2: Schema migrations tracking table
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version     TEXT PRIMARY KEY,
                    applied_at  TEXT NOT NULL
                )
            """))
            conn.commit()
            logger.info("Schema migrations table initialized.")
        except Exception as e:
            logger.error(f"Error creating schema_migrations table: {e}")

    # ── Phase 3B: Background task runs ──────────────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS background_task_runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type       TEXT NOT NULL,
                    task_name       TEXT,
                    status          TEXT DEFAULT 'running',
                    project_id      TEXT,
                    started_at      TEXT DEFAULT (datetime('now')),
                    completed_at    TEXT,
                    result_summary  TEXT,
                    error           TEXT,
                    metadata        TEXT,
                    duration_ms     INTEGER
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_btr_project ON background_task_runs(project_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_btr_type ON background_task_runs(task_type)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_btr_started ON background_task_runs(started_at DESC)"))
            conn.commit()
            logger.info("Background task runs table initialized.")
        except Exception as e:
            logger.error(f"Error creating background_task_runs table: {e}")

    # ── Phase 3B: Watched directories ───────────────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS watched_directories (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    path                TEXT NOT NULL UNIQUE,
                    project_id          TEXT NOT NULL DEFAULT 'default',
                    enabled             INTEGER NOT NULL DEFAULT 1,
                    recursive           INTEGER NOT NULL DEFAULT 0,
                    allowed_extensions  TEXT NOT NULL DEFAULT '.pdf,.txt,.md,.docx,.csv,.xlsx,.pptx',
                    debounce_seconds    INTEGER NOT NULL DEFAULT 2,
                    created_at          TEXT DEFAULT (datetime('now')),
                    last_scan_at        TEXT,
                    file_count          INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.commit()
            logger.info("Watched directories table initialized.")
        except Exception as e:
            logger.error(f"Error creating watched_directories table: {e}")

    # ── Phase 3B: Scheduled tasks ───────────────────────────────────
    with engine.connect() as conn:
        try:
            # Drop legacy TEXT primary key table if it exists to migrate to INTEGER
            schema_info = conn.execute(text("PRAGMA table_info(scheduled_tasks)")).fetchall()
            if schema_info:
                id_col = [col for col in schema_info if col[1] == "id"]
                if id_col and "TEXT" in id_col[0][2].upper():
                    logger.warning("Migrating scheduled_tasks table id from TEXT to INTEGER...")
                    conn.execute(text("DROP TABLE scheduled_tasks"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"Failed to check/drop legacy scheduled_tasks table: {e}")

        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL,
                    description     TEXT,
                    cron_expression TEXT NOT NULL,
                    agent_prompt    TEXT NOT NULL,
                    project_id      TEXT NOT NULL DEFAULT 'default',
                    enabled         INTEGER NOT NULL DEFAULT 1,
                    last_run        TEXT,
                    next_run        TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                )
            """))
            conn.commit()
            logger.info("Scheduled tasks table initialized.")
        except Exception as e:
            logger.error(f"Error creating scheduled_tasks table: {e}")

    # ── Phase 3B: Extend documents table ────────────────────────────
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE documents ADD COLUMN file_hash TEXT"))
            conn.commit()
            logger.info("Database schema patched: added file_hash column to documents.")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text("ALTER TABLE documents ADD COLUMN missing INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
            logger.info("Database schema patched: added missing column to documents.")
        except Exception:
            pass  # Column already exists

    # ── Phase 3B: Startup zombie recovery ───────────────────────────
    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                UPDATE background_task_runs
                SET status = 'failed',
                    error = 'Server restarted during execution',
                    completed_at = datetime('now')
                WHERE status = 'running'
            """))
            if result.rowcount > 0:
                logger.warning(f"Recovered {result.rowcount} zombie task(s) from previous crash.")
            conn.commit()
        except Exception as e:
            logger.error(f"Error recovering zombie tasks: {e}")

    # 4. Ensure a 'default' project exists for the Main Chat
    from app.models.project import ProjectModel
    with Session(engine) as session:
        statement = select(ProjectModel).where(ProjectModel.id == "default")
        default_proj = session.exec(statement).first()
        if not default_proj:
            from datetime import datetime
            default_proj = ProjectModel(
                id="default",
                name="Main Chat",
                description="Your primary ASTRA workspace context.",
                project_type="general",
                history_json="[]",
                created_at=datetime.utcnow(),
                last_accessed_at=datetime.utcnow(),
            )
            session.add(default_proj)
            session.commit()
            logger.info("Main Chat context initialized.")


def get_session():
    with Session(engine) as session:
        yield session
