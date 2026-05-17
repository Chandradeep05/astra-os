import chromadb
from chromadb.config import Settings
import os
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class VectorService:
    def __init__(self, persist_directory: str = "chroma_db"):
        self.persist_directory = persist_directory
        if not os.path.exists(persist_directory):
            os.makedirs(persist_directory)
            
        self.client = chromadb.PersistentClient(path=persist_directory)

    def get_collection(self, name: str):
        return self.client.get_or_create_collection(name=name)

    def add_documents(
        self, 
        collection_name: str, 
        documents: List[str], 
        ids: List[str], 
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None
    ):
        try:
            collection = self.get_collection(collection_name)
            kwargs = {
                "documents": documents,
                "ids": ids,
                "metadatas": metadatas
            }
            if embeddings is not None:
                kwargs["embeddings"] = embeddings
                
            collection.add(**kwargs)
            return True
        except Exception as e:
            logger.error(f"Error adding to vector store: {e}")
            return False

    def query(
        self,
        collection_name: str,
        query_text: Optional[str] = None,
        query_embeddings: Optional[List[float]] = None,
        n_results: int = 3,
        where: Optional[Dict[str, Any]] = None,  # ASTRA-FIX: accept metadata filter
    ):
        try:
            collection = self.get_collection(collection_name)
            kwargs = {"n_results": n_results}
            if query_embeddings is not None:
                kwargs["query_embeddings"] = [query_embeddings]
            elif query_text is not None:
                kwargs["query_texts"] = [query_text]
            else:
                return None

            if where is not None:                  # ASTRA-FIX: forward where to ChromaDB
                kwargs["where"] = where            # ASTRA-FIX

            results = collection.query(**kwargs)
            return results
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            return None

vector_service = VectorService()
