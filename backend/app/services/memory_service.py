import logging
import uuid
from typing import List
from app.services.vector_service import vector_service

logger = logging.getLogger(__name__)

class MemoryService:
    """Service to handle permanent Long Term Memory (Jarvis-like)."""
    
    def __init__(self):
        self.collection_name = "astra_longterm_memory"

    def memorize(self, fact: str, project_id: str = "default") -> bool:
        """Saves a fact into the local vector DB for long-term retention."""
        try:
            doc_id = uuid.uuid4().hex
            success = vector_service.add_documents(
                collection_name=self.collection_name,
                documents=[fact],
                ids=[doc_id],
                metadatas=[{"project_id": project_id}]
            )
            if success:
                logger.info(f"Memorized fact: {fact[:50]}...")
            return success
        except Exception as e:
            logger.error(f"Failed to memorize fact: {e}")
            return False

    def retrieve_context(self, query: str = "", project_id: str = "default", limit: int = 5) -> str:
        """Retrieves semantically relevant memorized facts for the current query."""
        try:
            collection = vector_service.get_collection(self.collection_name)
            
            if query:
                # Use semantic search to find facts relevant to the current query
                results = collection.query(
                    query_texts=[query],
                    n_results=limit,
                    where={"project_id": project_id}
                )
                facts = results["documents"][0] if results.get("documents") and results["documents"] else []
            else:
                # Fallback: return recent facts if no query provided
                results = collection.get(
                    where={"project_id": project_id},
                    limit=limit
                )
                facts = results.get("documents", [])
            
            if not facts:
                return ""
            context = "USER PREFERENCES & LONG-TERM MEMORY:\n"
            context += "\n".join(f"- {fact}" for fact in facts)
            return context
        except Exception as e:
            logger.error(f"Error retrieving memory: {e}")
            return ""

memory_service = MemoryService()
