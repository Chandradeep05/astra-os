import os
import sys
import logging
from datetime import datetime

# Add the backend root to sys.path so we can import app modules when running the script directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("migration-source-normalized")

from app.db import create_db_and_tables, engine
from app.services.vector_service import vector_service
from app.services.document_service import _normalize_filename
from sqlmodel import Session
from sqlalchemy import text

def run_migration():
    logger.info("Starting source_normalized migration...")
    
    # 1. Ensure database tables exist
    create_db_and_tables()

    # 2. Check if migration is already applied in SQLite schema_migrations
    migration_version = "migrate_source_normalized"
    try:
        with Session(engine) as session:
            row = session.execute(
                text("SELECT version FROM schema_migrations WHERE version = :ver"),
                {"ver": migration_version}
            ).first()
            if row:
                logger.info(f"Migration '{migration_version}' has already been applied. Skipping.")
                return
    except Exception as e:
        logger.error(f"Error checking schema_migrations table: {e}. Proceeding anyway...")

    # 3. Migrate ChromaDB Collections
    logger.info("Connecting to ChromaDB and listing collections...")
    try:
        collections = vector_service.client.list_collections()
        logger.info(f"Found {len(collections)} collections in vector database.")
    except Exception as e:
        logger.error(f"Failed to retrieve collections from ChromaDB: {e}")
        return

    migrated_total = 0

    for collection in collections:
        logger.info(f"Checking collection: {collection.name}")
        try:
            # Fetch all documents and metadata from the collection
            # To fetch everything, we pass empty dict (or fetch in batches if extremely large,
            # but standard workspaces are small enough to get in one go)
            result = collection.get()
            ids = result.get("ids", [])
            metadatas = result.get("metadatas", [])
            
            if not ids or not metadatas:
                logger.info(f"Collection '{collection.name}' is empty.")
                continue

            ids_to_update = []
            metadatas_to_update = []

            for doc_id, metadata in zip(ids, metadatas):
                if not metadata:
                    continue
                
                source = metadata.get("source")
                source_normalized = metadata.get("source_normalized")

                if source:
                    # Calculate correct normalized source filename
                    expected_normalized = _normalize_filename(source)
                    
                    # If field is missing OR mismatching, we migrate
                    if not source_normalized or source_normalized != expected_normalized:
                        updated_metadata = dict(metadata)
                        updated_metadata["source_normalized"] = expected_normalized
                        
                        ids_to_update.append(doc_id)
                        metadatas_to_update.append(updated_metadata)

            if ids_to_update:
                logger.info(f"Updating {len(ids_to_update)} chunk metadatas in collection '{collection.name}'...")
                collection.update(ids=ids_to_update, metadatas=metadatas_to_update)
                migrated_total += len(ids_to_update)
                logger.info(f"Successfully migrated collection '{collection.name}'.")
            else:
                logger.info(f"No pending metadata migrations for collection '{collection.name}'.")

        except Exception as e:
            logger.error(f"Error processing collection '{collection.name}': {e}")

    logger.info(f"ChromaDB migration completed. Total chunks updated: {migrated_total}")

    # 4. Record migration completion in SQLite schema_migrations
    try:
        with Session(engine) as session:
            session.execute(
                text("INSERT INTO schema_migrations (version, applied_at) VALUES (:ver, :applied)"),
                {"ver": migration_version, "applied": datetime.utcnow().isoformat()}
            )
            session.commit()
        logger.info(f"Successfully recorded migration version '{migration_version}' in database.")
    except Exception as e:
        logger.error(f"Failed to record migration version to schema_migrations: {e}")

if __name__ == "__main__":
    run_migration()
