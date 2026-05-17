"""
ASTRA OS — Memory Recall Tool
================================
Retrieves stored facts from long-term memory (ChromaDB).
This is the READ side — memorize is the WRITE side.
"""

from app.agent.memory import agent_memory
import logging

logger = logging.getLogger(__name__)


class MemoryRecallTool:
    """Retrieve previously memorized facts about the user or past context."""

    def __init__(self):
        self.name = "recall_memory"
        self.description = (
            "Search your long-term memory for previously stored facts about the user, "
            "their preferences, past conversations, or any information you memorized earlier. "
            "Use this when the user asks 'what do you remember', 'do you know my name', "
            "or any question about previously shared personal information."
        )

    async def execute(self, query: str, project_id: str = "default") -> str:
        """Search long-term memory for facts matching the query."""
        try:
            context = await agent_memory.long_term.recall(
                query=query, project_id=project_id, limit=5
            )
            if context:
                return f"Retrieved from memory:\n{context}"
            return "No relevant memories found. Nothing has been memorized about this topic yet."
        except Exception as e:
            logger.error(f"MemoryRecallTool error: {e}")
            return f"Error recalling memory: {str(e)}"
