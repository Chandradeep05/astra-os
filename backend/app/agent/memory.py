"""
ASTRA OS — Unified Agent Memory
================================
Combines four memory types into one clean interface:

1. SHORT-TERM:  Sliding window of recent conversation messages
2. WORKING:     Current task's observations and tool results (lives in AgentState)
3. LONG-TERM:   ChromaDB semantic search for relevant past knowledge
4. EPISODIC:    SQLite log of past task attempts with success/failure

This design keeps memory lightweight for 8-16GB RAM machines while still
giving the agent meaningful context about what it knows and what it's tried.
"""

import logging
import uuid
import json
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from app.services.vector_service import vector_service
from app.services.document_service import document_service

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Episodic Memory Store (SQLite-backed)
# ──────────────────────────────────────────────
# Phase 2: Full SQLite persistence. All history retained indefinitely.
# Retrieval: fetch recent → rank by keyword overlap → return top N.
# Access frequency tracked for future LRU-aware retrieval.

class EpisodicMemory:
    """
    Stores task execution episodes in SQLite: what was attempted, which tools
    were used, and whether the task succeeded. Helps the agent avoid repeating
    mistakes and learn from past successes.

    Phase 2: Migrated from in-memory list to persistent SQLite storage.
    All history is retained indefinitely — retrieval is constrained by
    recency and relevance, not storage limits.
    """

    def record_episode(
        self,
        task: str,
        tools_used: List[str],
        success: bool,
        summary: str,
        project_id: str = "default",
    ):
        """Record a completed task episode to SQLite."""
        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text

        episode_id = uuid.uuid4().hex[:12]
        try:
            with Session(engine) as session:
                session.execute(
                    text("""
                        INSERT INTO episodic_memory
                            (id, task, tools_used, success, summary, project_id, created_at)
                        VALUES
                            (:id, :task, :tools_used, :success, :summary, :project_id, :created_at)
                    """),
                    {
                        "id": episode_id,
                        "task": task[:200],
                        "tools_used": json.dumps(tools_used),
                        "success": 1 if success else 0,
                        "summary": summary[:500],
                        "project_id": project_id,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )
                session.commit()
            logger.info(f"Recorded episode: {'✅' if success else '❌'} {task[:50]}...")
        except Exception as e:
            logger.error(f"Failed to record episode: {e}")

    def get_relevant_episodes(
        self, task: str, limit: int = 3, project_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant past episodes using recency + keyword matching.

        Strategy (per approved spec):
        1. Fetch last 100 episodes from SQLite (ordered by recency)
        2. Score by keyword overlap in Python
        3. Return top `limit` results
        4. Update access_count on returned episodes
        """
        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text

        try:
            with Session(engine) as session:
                rows = session.execute(
                    text("""
                        SELECT id, task, tools_used, success, summary, project_id, created_at
                        FROM episodic_memory
                        WHERE project_id = :pid
                        ORDER BY created_at DESC
                        LIMIT 100
                    """),
                    {"pid": project_id}
                ).fetchall()

            if not rows:
                return []

            # Convert rows to dicts
            episodes = []
            for row in rows:
                ep = dict(row._mapping)
                ep["tools_used"] = json.loads(ep["tools_used"]) if isinstance(ep["tools_used"], str) else ep["tools_used"]
                ep["success"] = bool(ep["success"])
                episodes.append(ep)

            # Score by keyword overlap (same proven logic from Phase 1)
            task_words = set(task.lower().split())
            scored = []
            for ep in episodes:
                ep_words = set(ep["task"].lower().split())
                overlap = len(task_words & ep_words)
                if overlap > 0:
                    scored.append((overlap, ep))

            # Sort by relevance (most keyword overlap first)
            scored.sort(key=lambda x: x[0], reverse=True)

            # Extract top results and update their access counts
            result_episodes = [ep for _, ep in scored[:limit]]
            if result_episodes:
                self._update_access_count(result_episodes)

            return result_episodes

        except Exception as e:
            logger.error(f"Failed to retrieve episodes: {e}")
            return []

    def _update_access_count(self, episodes: List[Dict[str, Any]]):
        """Increment access_count and update last_accessed for retrieved episodes."""
        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text

        try:
            with Session(engine) as session:
                for ep in episodes:
                    session.execute(
                        text("""
                            UPDATE episodic_memory
                            SET access_count = access_count + 1,
                                last_accessed = :now
                            WHERE id = :id
                        """),
                        {"id": ep["id"], "now": datetime.utcnow().isoformat()}
                    )
                session.commit()
        except Exception as e:
            logger.error(f"Failed to update access counts: {e}")

    def get_all_episodes(
        self, project_id: str = "default", limit: int = 50, offset: int = 0
    ) -> Dict[str, Any]:
        """Paginated retrieval for the Memory Browser UI."""
        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text

        try:
            with Session(engine) as session:
                # Get total count
                count_row = session.execute(
                    text("SELECT COUNT(*) as cnt FROM episodic_memory WHERE project_id = :pid"),
                    {"pid": project_id}
                ).first()
                total = count_row.cnt if count_row else 0

                # Get paginated rows
                rows = session.execute(
                    text("""
                        SELECT * FROM episodic_memory
                        WHERE project_id = :pid
                        ORDER BY created_at DESC
                        LIMIT :lim OFFSET :off
                    """),
                    {"pid": project_id, "lim": limit, "off": offset}
                ).fetchall()

                episodes = []
                for row in rows:
                    ep = dict(row._mapping)
                    ep["tools_used"] = json.loads(ep["tools_used"]) if isinstance(ep["tools_used"], str) else ep["tools_used"]
                    ep["success"] = bool(ep["success"])
                    episodes.append(ep)

                return {"episodes": episodes, "total": total}
        except Exception as e:
            logger.error(f"Failed to get all episodes: {e}")
            return {"episodes": [], "total": 0}

    def delete_episode(self, episode_id: str) -> bool:
        """Delete a specific episode by ID."""
        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text

        try:
            with Session(engine) as session:
                result = session.execute(
                    text("DELETE FROM episodic_memory WHERE id = :id"),
                    {"id": episode_id}
                )
                session.commit()
                deleted = result.rowcount > 0
                if deleted:
                    logger.info(f"Deleted episode: {episode_id}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete episode: {e}")
            return False

    def format_episodes(self, episodes: List[Dict[str, Any]]) -> str:
        """Format episodes into context for the LLM."""
        if not episodes:
            return ""

        lines = ["PAST TASK EXPERIENCES:"]
        for ep in episodes:
            status = "✅ Succeeded" if ep["success"] else "❌ Failed"
            tools = ", ".join(ep["tools_used"]) if ep["tools_used"] else "none"
            lines.append(
                f"- [{status}] Task: {ep['task']}\n"
                f"  Tools used: {tools}\n"
                f"  Result: {ep['summary']}"
            )
        return "\n".join(lines)


# ──────────────────────────────────────────────
#  Long-Term Memory (ChromaDB-backed)
# ──────────────────────────────────────────────

class LongTermMemory:
    """
    Semantic memory using ChromaDB. Stores knowledge facts that persist
    across sessions. Uses ChromaDB's built-in embeddings (all-MiniLM-L6-v2).

    Future upgrade: switch to Ollama embeddings via nomic-embed-text
    to avoid loading a separate embedding model.
    """

    COLLECTION_NAME = "astra_agent_memory"

    # Fix #5: Sensitive data blocklist — reject passwords, keys, SSNs, etc.
    _SENSITIVE_PATTERNS = re.compile(
        r'\b('
        r'password is|passwd is|secret is|api.?key is|access.?token is'
        r'|private.?key is|ssh.?key is|credit.?card.*(is|number)'
        r'|social.?security.*(is|number)|ssn is|pin.?code is'
        r'|bank.?account.*(is|number)|routing.?number is'
        r'|my password|my secret|my api.?key|my token|my pin|my ssn|my credit.?card'
        r')\b',
        re.IGNORECASE,
    )

    async def memorize(self, fact: str, project_id: str = "default") -> bool:
        """Store a fact in long-term vector memory."""
        # Fix #5: Reject sensitive data before storing
        if self._SENSITIVE_PATTERNS.search(fact):
            logger.warning(f"[MEMORY-GUARD] Rejected sensitive data: {fact[:40]}...")
            return False

        try:
            doc_id = uuid.uuid4().hex
            embedding = await document_service.get_embedding(fact)
            success = vector_service.add_documents(
                collection_name=self.COLLECTION_NAME,
                documents=[fact],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[{"project_id": project_id, "stored_at": datetime.utcnow().isoformat()}],
            )
            if success:
                logger.info(f"Memorized: {fact[:60]}...")
            return success
        except Exception as e:
            logger.error(f"Failed to memorize: {e}")
            return False

    async def recall(self, query: str, project_id: str = "default", limit: int = 5) -> str:
        """Retrieve semantically relevant facts for a given query."""
        try:
            query_embedding = await document_service.get_embedding(query)
            collection = vector_service.get_collection(self.COLLECTION_NAME)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where={"project_id": project_id},
            )
            facts = results["documents"][0] if results.get("documents") and results["documents"] else []

            if not facts:
                return ""

            context = "LONG-TERM MEMORY (relevant knowledge):\n"
            context += "\n".join(f"- {fact}" for fact in facts)
            return context

        except Exception as e:
            logger.error(f"Memory recall failed: {e}")
            return ""

    async def forget(self, topic: str, project_id: str = "default") -> int:
        """Delete memories containing a specific topic/keyword from long-term memory.
        Returns the number of forgotten facts."""
        try:
            collection = vector_service.get_collection(self.COLLECTION_NAME)
            # Fetch ALL memories for the project (typically a small set)
            results = collection.get(where={"project_id": project_id})
            if not results or not results.get("ids"):
                return 0

            ids_to_delete = []
            deleted_facts = []

            # Simple keyword search — robust and fast for small fact stores
            clean_topic = topic.lower().strip()
            for doc_id, doc_text in zip(results["ids"], results["documents"]):
                if clean_topic in doc_text.lower():
                    ids_to_delete.append(doc_id)
                    deleted_facts.append(doc_text)

            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(f"[LTM] Forgot {len(ids_to_delete)} fact(s): {deleted_facts}")

            return len(ids_to_delete)
        except Exception as e:
            logger.error(f"Memory forget failed: {e}")
            return 0


# ──────────────────────────────────────────────
#  Unified Memory Interface
# ──────────────────────────────────────────────

class AgentMemory:
    """
    Single entry point for all memory operations.
    The agent calls this — it doesn't need to know about ChromaDB vs SQLite.
    """

    def __init__(self):
        self.long_term = LongTermMemory()
        self.episodic = EpisodicMemory()

    async def build_context(
        self,
        task: str,
        conversation_history: List[Dict[str, str]],
        working_memory: str = "",
        project_id: str = "default",
        query_class: str = None,  # FIX-3: from classifier — skip ChromaDB unless RAG_QUERY
    ) -> str:
        """Retrieval-aware context assembly with token budgeting (~1500 tokens)."""
        parts = []

        # 1. [RELEVANT KNOWLEDGE] - Document Search (Semantic) — ASTRA-FIX: unpack dict response
        try:
            search_response = await document_service.search_similar(
                task,
                project_id=project_id,
                limit=3,
                query_class=query_class,  # FIX-3: short-circuit if not RAG_QUERY
            )  # ASTRA-FIX
            confidence_level = search_response.get("confidence_level", "none")   # ASTRA-FIX
            doc_results      = search_response.get("results", [])                # ASTRA-FIX

            if confidence_level == "none" or not doc_results:                    # ASTRA-FIX
                pass  # no knowledge block added
            else:
                doc_text = "[RELEVANT KNOWLEDGE]"                                # ASTRA-FIX
                if confidence_level == "low":                                    # ASTRA-FIX
                    doc_text += "\n[Low confidence retrieval — treat with caution]"  # ASTRA-FIX
                    doc_results = doc_results[:min(2, len(doc_results))]         # ASTRA-FIX: cap low results
                doc_text += "\n"
                for res in doc_results:
                    content = res.get("content", "").replace("\n", " ").strip()[:400]
                    doc_text += f"* {content}\n"
                parts.append(doc_text.strip())
        except Exception as e:
            logger.error(f"Doc search context failed: {e}")


        # 2. [MEMORY] - Semantic Long-Term and Episodic
        mem_parts = []
        # Skip the embedding-based LTM recall unless semantics are needed.
        # long_term.recall() calls document_service.get_embedding() → Ollama nomic-embed-text.
        # For TOOL_CALL and META this is pure overhead; skip it.
        _needs_ltm = query_class in (None, "RAG_QUERY", "MEMORY_OP")
        try:
            ltm_raw = await self.long_term.recall(task, project_id, limit=3) if _needs_ltm else ""
        except Exception as e:
            logger.error(f"LTM recall in build_context failed: {e}")
            ltm_raw = ""
        if ltm_raw:
            # Cleanly strip the old prefix from long_term.recall mapping it to the new bullet style
            for line in ltm_raw.split("\n"):
                if line.startswith("- "):
                    mem_parts.append(f"* {line[2:]}")

        episodes = self.episodic.get_relevant_episodes(task, limit=2, project_id=project_id)
        for ep in episodes:
            status = "Success" if ep["success"] else "Failure"
            mem_parts.append(f"* Past {status}: {ep['task'][:100]} -> {ep['summary'][:150]}")

        if mem_parts:
            parts.append("[MEMORY]\n" + "\n".join(mem_parts))


        # 3. [RECENT CONTEXT] - Short-term & Working State
        recent_lines = []
        if conversation_history:
            for msg in conversation_history[-5:]: # Last 5 messages max
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")[:300]
                recent_lines.append(f"{role}: {content}")
        if working_memory:
            recent_lines.append(f"WORKING STATE: {working_memory[:500]}")
            
        if recent_lines:
            parts.append("[RECENT CONTEXT]\n" + "\n".join(recent_lines))

        # 4. [CURRENT GOAL] - Must not be truncated
        goal_part = f"[CURRENT GOAL]\n{task[:500]}"
        
        # Combine earlier parts
        history_parts = "\n\n".join(parts)
        
        # Final Token Budgeting: ~1500 tokens approx ~6000 chars
        max_history_len = 5900 - len(goal_part)
        
        if len(history_parts) > max_history_len:
            # Safe line-by-line truncation to preserve structure
            lines = history_parts.split("\n")
            truncated_history = ""
            for line in lines:
                if len(truncated_history) + len(line) < max_history_len:
                    truncated_history += line + "\n"
                else:
                    truncated_history += "...[Truncated for token limits]\n"
                    break
            history_parts = truncated_history.strip()

        final_context = history_parts + "\n\n" + goal_part
        return final_context

    def record_task_completion(
        self,
        task: str,
        tools_used: List[str],
        success: bool,
        summary: str,
        project_id: str = "default",
    ):
        """Record a task in episodic memory after completion."""
        self.episodic.record_episode(task, tools_used, success, summary, project_id)

    async def memorize_fact(self, fact: str, project_id: str = "default") -> bool:
        """Store a fact in long-term memory."""
        return await self.long_term.memorize(fact, project_id)

    async def forget_fact(self, topic: str, project_id: str = "default") -> int:
        """Delete facts matching a topic from long-term memory."""
        return await self.long_term.forget(topic, project_id)


# Global singleton — shared across agent invocations
agent_memory = AgentMemory()
