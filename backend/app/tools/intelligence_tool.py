import json  # ASTRA-FIX
import re
from app.agent.memory import agent_memory
import logging

logger = logging.getLogger(__name__)

class LongTermMemoryTool:
    def __init__(self):
        self.name = "memorize"
        self.description = (
            "PERMANENTLY SAVE a fact to long-term memory. Use this ONLY when the user "
            "explicitly asks you to remember something, like 'remember that my name is X' "
            "or 'save this for later'. The fact parameter should be the EXACT information "
            "to store, e.g., 'User name is Chandradeep'. Do NOT use this for retrieving "
            "memories — use recall_memory instead."
        )

    # Sensitive data blocklist — reject at tool level BEFORE LLM can echo it back
    _SENSITIVE_GUARD = re.compile(
        r'\b('
        r'password|passwd|passphrase|secret|api.?key|access.?token'
        r'|private.?key|ssh.?key|credit.?card|social.?security|ssn'
        r'|pin.?code|bank.?account|routing.?number|cvv|cvc'
        r')\b.*\b(is|=|:|was|are|equals|set to)\b'
        r'|\b(my password|my secret|my api.?key|my token|my pin|my ssn|my credit.?card)\b',
        re.IGNORECASE,
    )

    async def execute(self, fact: str, project_id: str = "default") -> str:
        """
        Action: memorize
        Saves the fact to ChromaDB.
        """
        # ASTRA-FIX: Guard against empty fact before hitting ChromaDB
        if not fact or not fact.strip():  # ASTRA-FIX
            return "Cannot memorize an empty fact."  # ASTRA-FIX

        # Memory poisoning guard — reject sensitive data at tool level
        if self._SENSITIVE_GUARD.search(fact):
            logger.warning(f"[MEMORY-GUARD] Rejected sensitive data at tool level: {fact[:40]}...")
            return (
                "I cannot store sensitive information like passwords, API keys, or financial data. "
                "This is for your security. Please store sensitive data in a secure password manager."
            )

        try:
            success = await agent_memory.memorize_fact(fact=fact, project_id=project_id)
            if success:
                return f"Successfully memorized fact: '{fact}'"
            return "Failed to memorize fact due to database error."
        except Exception as e:
            logger.error(f"LongTermMemoryTool error: {e}")
            return f"Error executing memorize: {str(e)}"

