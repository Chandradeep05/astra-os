from typing import List, Dict, Any
from app.services.document_service import document_service
import logging

logger = logging.getLogger(__name__)  # ASTRA-FIX

class DocumentSearchTool:
    def __init__(self):
        self.name = "document_search"
        self.description = "Search through the user's uploaded documents, PDFs, and workspace files for relevant information."

    async def execute(self, query: str, project_id: str = None, file_id: str = None) -> str:  # ASTRA-FIX: added file_id, project_id optional
        try:
            # ASTRA-FIX: pass both optional filters; search_similar returns a dict
            search_response = await document_service.search_similar(
                query=query,
                project_id=project_id,
                file_id=file_id,  # ASTRA-FIX
                limit=3,
            )

            confidence_level = search_response.get("confidence_level", "none")  # ASTRA-FIX
            results          = search_response.get("results", [])               # ASTRA-FIX

            if confidence_level == "none" or not results:                        # ASTRA-FIX
                return (
                    "No relevant information found in workspace documents. "
                    "The document may not be ingested, or the query may need rephrasing."
                )  # ASTRA-FIX


            output = f"Information found in Workspace Documents for '{query}':\n"
            if confidence_level == "low":                                        # ASTRA-FIX
                output += "[Low confidence — results may be weakly related]\n"
            output += "\n"

            for res in results:
                source     = res.get("metadata", {}).get("source", "Unknown")
                content    = res.get("content", "")
                similarity = res.get("similarity", 0.0)                         # ASTRA-FIX
                confidence = res.get("confidence", "unknown")                   # ASTRA-FIX
                output += f"--- Source: {source} | similarity={similarity:.3f} | confidence={confidence} ---\n{content}\n\n"  # ASTRA-FIX

            return output
        except Exception as e:
            logger.error(f"DocumentSearchTool error: {e}")                       # ASTRA-FIX
            return f"Error searching documents: {str(e)}"

