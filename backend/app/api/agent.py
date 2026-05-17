"""
ASTRA OS — Agent API Endpoint
================================
New /api/v1/agent endpoint that runs the autonomous OTPAR loop.
Coexists with the legacy /api/v1/chat endpoint — no breaking changes.

Streams the agent's cognitive process as Server-Sent Events:
  - Phase changes (observe, think, plan, act, reflect)
  - Thoughts and reasoning
  - Tool calls and results
  - Approval requests (for risky actions)
  - Final answers

The frontend can render these events to show the user what the agent
is thinking and doing in real-time (great for the 3D avatar animations).
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.agent.schemas import AgentRequest, AgentStreamEvent
from app.agent.loop import AgentLoop
from app.agent.classifier import classify_query, QueryClass
from app.services.audit_service import audit_service
from app.services.ollama import OllamaService
from app.services.document_service import document_service
from app.core.config import settings
import logging
import json
import re as _re

router = APIRouter()
logger = logging.getLogger(__name__)

# Minimal system prompt used for DIRECT_LLM bypass.
# No tool list, no JSON format constraint, no agent rules overhead.
_DIRECT_SYSTEM_PROMPT = (
    "You are ASTRA, an advanced personal AI operating system running locally on the user's machine. "
    "You are intelligent, concise, and always helpful. "
    "Respond clearly using plain text or standard Markdown (bold, italic, headers, bullets). "
    "Do not use custom tags or structured JSON wrappers. "
    "When asked who you are, explain you are ASTRA OS — a local-first AI assistant with memory, "
    "document intelligence, code execution, and web search capabilities."
)

# Pattern for detecting "list all documents" queries
_LIST_DOCS_PATTERN = _re.compile(
    r'\b(list|show|what|which).{0,20}(documents?|files?|uploads?|pdfs?)\b',
    _re.IGNORECASE
)

# Pattern for detecting identity/capability queries (META bypass)
_IDENTITY_CAPABILITY_PATTERN = _re.compile(
    r'\b(who are you|what can you do|what are your capabilities|what are your functions|how can you help|tell me about yourself)\b',
    _re.IGNORECASE
)


async def _direct_llm_stream(request: AgentRequest):
    """
    DIRECT_LLM fast path — completely bypasses AgentLoop.

    Makes exactly ONE Ollama call using stream_invoke() (token streaming).
    No embeddings, no tool prompt, no format=json, no ChromaDB.

    Each token is yielded immediately as an SSE answer event so the
    frontend renders the first word in ~300ms instead of waiting for
    the full response to finish generating.
    """
    model = request.model or settings.DEFAULT_MODEL
    ollama = OllamaService(model_name=model)

    try:
        async for chunk in ollama.stream_invoke(
            prompt=request.task,
            history=[{"role": "system", "content": _DIRECT_SYSTEM_PROMPT}],
        ):
            if chunk.get("type") == "content":
                # Yield each token immediately — don't buffer
                token_event = AgentStreamEvent(type="answer", content=chunk["content"])
                yield f"data: {json.dumps(token_event.model_dump(exclude_none=True))}\n\n"
            elif chunk.get("type") == "error":
                err_event = AgentStreamEvent(type="error", content=chunk["content"])
                yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                return

        done_event = AgentStreamEvent(type="done")
        yield f"data: {json.dumps(done_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[DIRECT_LLM] stream error: {e}", exc_info=True)
        err_event = AgentStreamEvent(type="error", content=f"Direct response failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"


# ── MATH_BYPASS: Complex math → direct python_executor ──────────────────────
# qwen2.5:3b doesn't reliably call python_executor from the agent loop.
# For math queries classified as TOOL_CALL, we bypass the loop entirely
# and execute the expression directly. Guaranteed correct answer in <1s.

_MATH_QUERY_PATTERN = _re.compile(
    r'^(calculate[:\s]*|compute[:\s]*)?'
    r'([\d\s\(\)\.\+\-\*\/\%\^]+)$',
    _re.IGNORECASE,
)

async def _math_bypass_stream(request: AgentRequest):
    """Direct math execution using a safe eval context — avoids RestrictedPython import blocks."""
    import math as _math

    # Strip 'calculate:' prefix, keep the expression
    expr = _re.sub(r'^(calculate[:\s]*|compute[:\s]*|what\s+is\s+|what\'?s\s+)', '', request.task, flags=_re.IGNORECASE).strip()
    expr = expr.rstrip('?').strip()

    # Inject math functions into the expression by replacing function names
    # with their math module equivalents using a safe pre-substitution
    math_safe_expr = expr
    for fn in ['sqrt', 'log', 'log10', 'log2', 'sin', 'cos', 'tan', 
               'ceil', 'floor', 'round', 'abs', 'pow', 'exp']:
        math_safe_expr = _re.sub(
            rf'\b{fn}\b', f'math.{fn}', math_safe_expr, flags=_re.IGNORECASE
        )
    # Replace ^ with ** for exponentiation
    math_safe_expr = math_safe_expr.replace('^', '**')

    try:
        # Execute with math module available as a variable (no import needed)
        # Direct eval with math — bypasses RestrictedPython for pure math
        result = eval(math_safe_expr, {"__builtins__": {}}, {
            "math": _math,
            "sqrt": _math.sqrt, "log": _math.log, "log10": _math.log10,
            "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
            "ceil": _math.ceil, "floor": _math.floor,
            "abs": abs, "pow": pow, "round": round, "pi": _math.pi, "e": _math.e,
        })
        
        event = AgentStreamEvent(type="answer", content=f"Result: {result}")
        yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"[MATH_BYPASS] error: {e}")
        err_event = AgentStreamEvent(type="error", content=f"Calculation failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"

# ── MEMORY_BYPASS: Memory ops → direct memorize/recall, skip agent loop ──────
# CRITICAL: qwen2.5:3b does NOT reliably call memorize/recall_memory tools
# through the agent loop. It generates direct text answers instead, meaning:
#   - "Remember my password is 123456" → LLM says "saved!" but NEVER calls tool
#   - "My favorite language is Rust" → LLM says "noted!" but nothing stored
#   - "What do you know about me?" → LLM says "I don't know" without recalling
#
# This bypass handles memory operations with deterministic code paths.

import re as _re_mem

# Patterns that indicate the user wants to STORE a fact
_MEMORY_STORE_PATTERN = _re_mem.compile(
    r'\b(remember that|don\'?t forget|keep in mind|store this|'
    r'my name is|i am |i\'?m |my favorite|i prefer|i hate|i love|i like|'
    r'i use |i switched|i work|i live|i study|i play|i enjoy|'
    r'i\'?m building|i\'?m using|i\'?m working|i\'?m pursuing|'
    r'my .+ is|i have a|remember my|remember this|please remember )\b',
    _re_mem.IGNORECASE,
)

# Patterns that indicate the user wants to RECALL facts
_MEMORY_RECALL_PATTERN = _re_mem.compile(
    r'\b(what do you (know|remember|recall) about me|'
    r'what have you (remembered|memorized|stored)|'
    r'tell me about myself|what is my |what\'?s my |'
    r'do you (remember|know) my |'
    r'summarize what you know|what you know about me|'
    r'who am i|what are my )\b',
    _re_mem.IGNORECASE,
)

# Sensitive data guard — block at bypass level before anything reaches memory
_MEMORY_SENSITIVE_GUARD = _re_mem.compile(
    r'\b(password|passwd|passphrase|secret|api.?key|access.?token'
    r'|private.?key|ssh.?key|credit.?card|social.?security|ssn'
    r'|pin.?code|\batm\b|\bpin\b|bank.?account|routing.?number|cvv|cvc)\b',
    _re_mem.IGNORECASE,
)

# Patterns that indicate the user wants to DELETE/FORGET a fact
_MEMORY_DELETE_PATTERN = _re_mem.compile(
    r'\b(forget|delete|remove|erase|wipe|clear)\s+(.+?)\s*(from\s+(your\s+)?memory)?\s*$',
    _re_mem.IGNORECASE,
)

async def _memory_bypass_stream(request: AgentRequest):
    """Memory operations → direct memorize/recall, bypassing unreliable LLM tool calling."""
    from app.agent.memory import agent_memory

    try:
        query = request.task.strip()
        project_id = request.project_id or "default"

        # ── RECALL path ──
        if _MEMORY_RECALL_PATTERN.search(query):
            logger.info(f"[MEMORY_BYPASS] RECALL path for: {query[:60]}")

            recalled = await agent_memory.long_term.recall(
                query=query,
                project_id=project_id,
                limit=5,
            )

            if recalled and recalled.strip():
                # Stream the recalled facts through an LLM for natural formatting
                model = request.model or settings.DEFAULT_MODEL
                ollama = OllamaService(model_name=model)

                augmented = (
                    f"The user asked: {query}\n\n"
                    f"Here is what you remember about the user from your long-term memory:\n"
                    f"{recalled}\n\n"
                    f"Summarize these memories naturally as a direct response to the user. "
                    f"Be specific — mention each fact you recall."
                )

                async for chunk in ollama.stream_invoke(
                    prompt=augmented,
                    history=[{"role": "system", "content": "You are ASTRA, a personal AI assistant. Answer using ONLY the memory facts provided. Do not make up information."}],
                ):
                    if chunk.get("type") == "content":
                        yield f"data: {json.dumps(AgentStreamEvent(type='answer', content=chunk['content']).model_dump(exclude_none=True))}\n\n"
                    elif chunk.get("type") == "error":
                        yield f"data: {json.dumps(AgentStreamEvent(type='error', content=chunk['content']).model_dump(exclude_none=True))}\n\n"
                        yield "data: [DONE]\n\n"
                        return
            else:
                event = AgentStreamEvent(
                    type="answer",
                    content="I don't have any stored memories about you yet. You can tell me things like \"My name is X\" or \"I prefer Python\" and I'll remember them for future conversations."
                )
                yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"

            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        # ── STORE path ──
        if _MEMORY_STORE_PATTERN.search(query):
            logger.info(f"[MEMORY_BYPASS] STORE path for: {query[:60]}")

            # Sensitive data guard
            if _MEMORY_SENSITIVE_GUARD.search(query):
                logger.warning(f"[MEMORY-GUARD] Rejected at bypass level: {query[:40]}")
                event = AgentStreamEvent(
                    type="answer",
                    content="🔒 I cannot store sensitive information like passwords, API keys, or financial data. Please use a secure password manager for that."
                )
                yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
                yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Extract the fact — strip command prefixes, keep the content
            fact = _re_mem.sub(
                r'^(remember that|don\'?t forget that|keep in mind that|store this[:\s]*|please )',
                '', query, flags=_re_mem.IGNORECASE
            ).strip()

            if not fact:
                fact = query  # Fallback to full query if stripping removed everything

            success = await agent_memory.memorize_fact(fact=fact, project_id=project_id)

            if success:
                event = AgentStreamEvent(
                    type="answer",
                    content=f"✅ Got it! I'll remember that: **{fact}**"
                )
            else:
                event = AgentStreamEvent(
                    type="answer",
                    content="⚠️ I wasn't able to save that to memory. Please try again."
                )

            yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        # ── DELETE/FORGET path ──
        delete_match = _MEMORY_DELETE_PATTERN.search(query)
        if delete_match:
            logger.info(f"[MEMORY_BYPASS] DELETE path for: {query[:60]}")
            raw_topic = delete_match.group(2).strip()

            # Remove common helper words like "my", "the", "about"
            topic_clean = _re_mem.sub(
                r'^(my\s+|the\s+|about\s+|all\s+)', '', raw_topic,
                flags=_re_mem.IGNORECASE
            ).strip()

            if not topic_clean:
                topic_clean = raw_topic  # Fallback

            deleted_count = await agent_memory.forget_fact(
                topic=topic_clean, project_id=project_id
            )

            if deleted_count > 0:
                event = AgentStreamEvent(
                    type="answer",
                    content=f"\U0001f5d1\ufe0f Memory updated! I have forgotten {deleted_count} fact(s) matching **{topic_clean}**."
                )
            else:
                event = AgentStreamEvent(
                    type="answer",
                    content=f"I couldn't find any memories matching **{topic_clean}** in my long-term memory."
                )

            yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        # ── Fallback: neither clear store nor recall nor delete — let agent loop handle ──
        logger.info(f"[MEMORY_BYPASS] Ambiguous memory query, falling back to agent loop: {query[:60]}")
        # Yield nothing — caller will fall through to agent loop

    except Exception as e:
        logger.error(f"[MEMORY_BYPASS] error: {e}", exc_info=True)
        err_event = AgentStreamEvent(type="error", content=f"Memory operation failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"


# ── DELETE_DOCS_BYPASS: Deterministic doc deletion with approval gate ────────
# qwen2.5:3b can't reliably call deletion tools from the agent loop.
# This bypass: regex match → approval gate → DB + filesystem + vector purge.

_DELETE_DOCS_PATTERN_FUNC = _re.compile(
    r'\b(delete|remove|purge|clear|wipe)\s+(all\s+)?(the\s+|my\s+)?(documents?|files?|uploads?|workspace)\b',
    _re.IGNORECASE,
)

async def _delete_all_documents_bypass_stream(request: AgentRequest):
    """Deterministic deletion bypass that forces user confirmation via the approval gate."""
    import uuid as _uuid
    import os as _os
    from app.agent.approval import StreamingApprovalGate, approval_registry
    from app.agent.schemas import RiskLevel

    gate = StreamingApprovalGate()
    task_id = f"del_{_uuid.uuid4().hex[:8]}"

    # 1. Emit the approval_required event to trigger the frontend modal
    approval_event = AgentStreamEvent(
        type="approval_required",
        content="Delete ALL documents and clear vector database index?",
        data={
            "tool": "workspace.delete_all_documents",
            "arguments": {"project_id": request.project_id or "default"},
            "task_id": task_id,
        },
    )
    yield f"data: {json.dumps(approval_event.model_dump(exclude_none=True))}\n\n"

    # 2. Block until the user submits a decision via POST /approve/{task_id}
    approved = await gate.request_approval(
        tool_name="workspace.delete_all_documents",
        arguments={"project_id": request.project_id or "default"},
        risk_level=RiskLevel.RISKY,
        description="Delete all uploaded documents and clear vector index chunks.",
        task_id=task_id,
    )

    if not approved:
        event = AgentStreamEvent(type="answer", content="❌ Deletion aborted by user.")
        yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"
        return

    # 3. Perform the deterministic database + filesystem + vector wipe
    try:
        yield f"data: {json.dumps(AgentStreamEvent(type='thought', content='Clearing files and vector chunks...').model_dump(exclude_none=True))}\n\n"

        from app.db import engine
        from sqlmodel import Session
        from sqlalchemy import text
        from app.services.vector_service import vector_service
        import os

        project_id = request.project_id or "default"

        # Fetch all documents for the project
        with Session(engine) as session:
            rows = session.execute(
                text("SELECT file_id, filename, original_name FROM documents WHERE project_id = :pid"),
                {"pid": project_id},
            ).fetchall()

        deleted_count = 0
        deleted_names = []
        for row in rows:
            fid = row.file_id
            filename = row.filename
            # Remove physical file
            file_path = os.path.join("uploads", filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            # Purge chunks from ChromaDB
            try:
                collection = vector_service.get_collection(f"project_{project_id}")
                if collection:
                    collection.delete(where={"file_id": {"$eq": fid}})
            except Exception:
                pass
            deleted_count += 1
            deleted_names.append(row.original_name)

        # Clear all documents from SQLite
        with Session(engine) as session:
            session.execute(
                text("DELETE FROM documents WHERE project_id = :pid"),
                {"pid": project_id},
            )
            session.commit()

        if deleted_count > 0:
            names_str = ", ".join(deleted_names[:5])
            if len(deleted_names) > 5:
                names_str += f" and {len(deleted_names) - 5} more"
            answer = f"🗑️ Success! Deleted {deleted_count} document(s): {names_str}.\nWorkspace vector indices have been cleared."
        else:
            answer = "No documents found in the workspace to delete."

        yield f"data: {json.dumps(AgentStreamEvent(type='answer', content=answer).model_dump(exclude_none=True))}\n\n"

    except Exception as e:
        logger.error(f"[DELETE_BYPASS] error: {e}", exc_info=True)
        yield f"data: {json.dumps(AgentStreamEvent(type='error', content=f'Deletion failed: {str(e)}').model_dump(exclude_none=True))}\n\n"

    yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
    yield "data: [DONE]\n\n"


# ── RAG_BYPASS: Document queries → search + direct LLM with context ─────────
# The agent loop with format="json" and tool prompt overhead causes qwen2.5:3b
# to describe retrieval metadata instead of answering from document content.
# This bypass: searches ChromaDB → prepends chunks → streams plain LLM answer.

_RAG_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Answer the user's question using ONLY "
    "the document context provided. "
    "You MUST append citations to every claim using the format [Source: filename]. "
    "If you cannot cite a source from the context provided, do not state the claim. "
    "If the context doesn't contain the answer, say so honestly."
)

async def _rag_bypass_stream(request: AgentRequest):
    """RAG queries → search docs then stream LLM answer with context."""
    try:
        # Fix #9: Check if the queried document is still being indexed
        from app.services.document_service import _extract_filename_from_query
        detected_file = _extract_filename_from_query(request.task)
        if detected_file:
            from app.api.documents import _ingestion_status
            from app.db import engine
            from sqlmodel import Session
            from sqlalchemy import text
            
            with Session(engine) as session:
                row = session.execute(
                    text("SELECT file_id FROM documents WHERE LOWER(original_name) = :fname"),
                    {"fname": detected_file.lower()}
                ).first()
                
                if row:
                    fid = row.file_id
                    status = _ingestion_status.get(fid, {})
                    if status.get("status") in ("pending", "processing"):
                        event = AgentStreamEvent(
                            type="answer",
                            content=f"⏳ **{detected_file}** is still being indexed. Please wait a moment and try again."
                        )
                        yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
                        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                        yield "data: [DONE]\n\n"
                        return

        search_response = await document_service.search_similar(
            query=request.task,
            project_id=request.project_id,
            limit=5,
            query_class="RAG_QUERY",
        )

        chunks = search_response.get("results", [])
        confidence = search_response.get("confidence_level", "none")

        # Hallucination Guard (Step 1)
        # If the chunks were below the similarity threshold, or no chunks were found.
        guard_triggered = search_response.get("guard_triggered", False)

        if guard_triggered or confidence == "none" or not chunks:
            logger.info("[RAG_BYPASS] Hallucination guard triggered — bypassing LLM.")
            event = AgentStreamEvent(
                type="answer",
                content="I don't have this in your documents."
            )
            yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Soft fail: "low" confidence with very weak similarity (< 0.01)
        # These chunks are essentially noise — sending them causes hallucination.
        # Fall back to direct LLM which will at least answer honestly.
        best_sim = max((r.get("similarity", 0.0) for r in chunks), default=0.0)
        if confidence == "low" and best_sim < 0.01:
            logger.warning(f"[RAG_BYPASS] Best sim={best_sim:.4f} too weak — falling back to DIRECT_LLM")
            async for sse_chunk in _direct_llm_stream(request):
                yield sse_chunk
            return

        # Token Budget Enforcement (Step 4)
        from app.utils.tokens import enforce_budget
        # RAG Bypass has no conversation history, so we pass an empty list
        _, pruned_chunks = enforce_budget(
            system_prompt=_RAG_SYSTEM_PROMPT,
            history=[],
            rag_chunks=chunks,
            max_window=8192
        )

        # Build context from chunks — guard against empty content
        doc_context_parts = []
        for idx, r in enumerate(pruned_chunks):
            content = r.get("content", "").strip()
            if content:
                source = r.get("metadata", {}).get("source", "Unknown Document")
                doc_context_parts.append(f"[Source: {source} | Chunk: {idx}]\n{content}")
                
        doc_context = "\n\n".join(doc_context_parts)
        
        if not doc_context.strip():
            logger.warning("[RAG_BYPASS] All chunks had empty content — falling back to DIRECT_LLM")
            async for sse_chunk in _direct_llm_stream(request):
                yield sse_chunk
            return

        augmented_prompt = (
            f"[DOCUMENT CONTEXT]\n{doc_context}\n\n"
            f"[USER QUESTION]\n{request.task}\n\n"
            "Answer the question using the document context above."
        )

        model = request.model or settings.DEFAULT_MODEL
        ollama = OllamaService(model_name=model)

        async for chunk in ollama.stream_invoke(
            prompt=augmented_prompt,
            history=[{"role": "system", "content": _RAG_SYSTEM_PROMPT}],
        ):
            if chunk.get("type") == "content":
                token_event = AgentStreamEvent(type="answer", content=chunk["content"])
                yield f"data: {json.dumps(token_event.model_dump(exclude_none=True))}\n\n"
            elif chunk.get("type") == "error":
                err_event = AgentStreamEvent(type="error", content=chunk["content"])
                yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                return

        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[RAG_BYPASS] error: {e}", exc_info=True)
        err_event = AgentStreamEvent(type="error", content=f"Document search failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"


# ── WEB_SEARCH_BYPASS: Real-time queries → direct DDG + LLM stream ──────────
# On CPU, the full agent loop does THINK(~6min) → ACT(5s) → REFLECT(~6min)
# per iteration. Weather/news/market queries take 3+ iterations = 30+ minutes.
# This bypass: 1 DDG search + 1 streaming LLM call = ~7 min total.
#
# IMPORTANT: Keep this pattern NARROW. Only simple real-time data lookups.
# Queries that need reasoning (compare, research, analyze) must go to AgentLoop.

# ── ALLOWLIST: Simple real-time data lookups only ──
_WEB_SEARCH_QUERY_PATTERN = _re.compile(
    r"\b("
    # Weather (most common real-time query)
    r"weather|forecast|temperature today|humidity today|rain today"
    # News & headlines (simple lookups, not research)
    r"|latest news|breaking news|headlines|news on|news about|news update"
    # "Latest/recent/current X updates" — real-time info requests
    r"|latest.{1,30}updates|recent.{1,30}updates|current.{1,30}updates"
    r"|latest.{1,30}release|new.{1,30}release|what'?s new in"
    # Financial data (price checks, not analysis)
    r"|stock price|share price|bitcoin price|crypto price|exchange rate"
    r"|market update|market trend"
    # Sports (scores, not analysis)
    r"|score|match result|game result"
    # Explicit search intent
    r"|search the web|search online|google for"
    r")\b",
    _re.IGNORECASE,
)

# ── BLOCKLIST: Queries that LOOK like search but need reasoning ──
# If ANY of these match, the bypass is skipped → goes to full AgentLoop.
_WEB_SEARCH_ANTI_PATTERN = _re.compile(
    r"\b("
    r"compare|comparison|versus|vs\.?"
    r"|research|analyze|analysis|evaluate|assess"
    r"|recommend|suggest|best|top \d+|pros and cons"
    r"|plan|strategy|roadmap|architecture|design"
    r"|explain|how does|how do|how to|why does|why do"
    r"|step.by.step|tutorial|guide|walkthrough"
    r"|summarize|summary|review|critique"
    r"|build|create|develop|implement|code|write"
    r"|difference between|advantages|disadvantages"
    r")\b",
    _re.IGNORECASE,
)

_WEB_SEARCH_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Answer the user's question using ONLY "
    "the web search results provided below. Be specific, cite facts from "
    "the results, and use clear Markdown formatting. If the search results "
    "don't contain the answer, say so honestly. Do NOT make up information."
)


async def _web_search_bypass_stream(request: AgentRequest):
    """
    Web search bypass — direct DDG search + single LLM stream.
    Eliminates multi-iteration agent loop for real-time queries.
    """
    from app.tools.duckduckgo_search import DuckDuckGoSearchTool

    search_tool = DuckDuckGoSearchTool()

    try:
        # Step 1: Direct web search — only top 3 results to minimize context
        # Each extra result adds ~200-500 tokens of context, which on CPU
        # means 30-60s more inference time. 3 results is the sweet spot.
        search_results = await search_tool.execute(query=request.task, max_results=3)

        # Step 2: If search failed or timed out, tell the user directly
        if not search_results or search_results == "Unable to fetch real-time data right now.":
            event = AgentStreamEvent(
                type="answer",
                content="I wasn't able to fetch real-time data right now. "
                        "Please check your internet connection or try again in a moment.",
            )
            yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Step 3: Hard-cap context to 3000 chars — prevents bloated prompts
        # that cause qwen2.5:3b to take 8+ minutes generating a response.
        # 3000 chars ≈ 750 tokens — well within the model's efficient range.
        if len(search_results) > 3000:
            search_results = search_results[:3000] + "\n\n[Results truncated for speed]"

        # Step 4: Feed capped search results into a single LLM stream
        augmented_prompt = (
            f"[WEB SEARCH RESULTS]\n{search_results}\n\n"
            f"[USER QUESTION]\n{request.task}\n\n"
            "Answer the user's question concisely using the search results above. "
            "Keep your response under 300 words."
        )

        model = request.model or settings.DEFAULT_MODEL
        ollama = OllamaService(model_name=model)

        async for chunk in ollama.stream_invoke(
            prompt=augmented_prompt,
            history=[{"role": "system", "content": _WEB_SEARCH_SYSTEM_PROMPT}],
        ):
            if chunk.get("type") == "content":
                token_event = AgentStreamEvent(type="answer", content=chunk["content"])
                yield f"data: {json.dumps(token_event.model_dump(exclude_none=True))}\n\n"
            elif chunk.get("type") == "error":
                err_event = AgentStreamEvent(type="error", content=chunk["content"])
                yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                return

        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"[WEB_SEARCH_BYPASS] error: {e}", exc_info=True)
        err_event = AgentStreamEvent(type="error", content=f"Web search failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"


@router.post("/run")
async def agent_endpoint(request: AgentRequest):
    """
    ASTRA OS Autonomous Agent SSE Endpoint.
    """
    # Proactive log to verify the request reached the backend
    logger.info(f"📥 [AGENT-REQUEST] Task: {request.task[:100]}")

    async def stream_generator():
        try:
            if not request.task or not request.task.strip():
                yield f"data: {json.dumps({'type': 'error', 'content': 'Empty task.'})}\n\n"
                return

            # ── FIX-1: Classify BEFORE anything else executes ──────────────
            import asyncio
            try:
                # Rule-based is fast, but LLM fallback could hang. Limit to 5s.
                query_class = await asyncio.wait_for(classify_query(request.task), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"[CLASSIFIER] Timeout for task: {request.task[:40]}, defaulting to DIRECT_LLM")
                query_class = QueryClass.DIRECT_LLM
            except Exception as e:
                logger.error(f"[CLASSIFIER] Unexpected error: {e}, defaulting to DIRECT_LLM")
                query_class = QueryClass.DIRECT_LLM

            logger.info(f"[CLASSIFIER] -> {query_class.value} | task: {request.task[:80]}")

            # ── DIRECT_LLM bypass — skip AgentLoop entirely ────────────────
            # Eliminates: embedding call in build_context(), nomic-embed-text
            # for long-term memory, 5KB tool prompt construction, format=json
            # overhead. Net result: "hello" goes from 20-40s → <3s.
            if query_class == QueryClass.DIRECT_LLM:
                logger.info(f"[META_BYPASS] Match: {request.task[:40]} — using DIRECT_LLM")
                async for sse_chunk in _direct_llm_stream(request):
                    yield sse_chunk
                return

            # ── MEMORY_BYPASS — direct memorize/recall, no agent loop ───────
            # qwen2.5:3b doesn't reliably call memorize/recall tools.
            # Handle store/recall deterministically. Ambiguous queries fall through.
            if query_class == QueryClass.MEMORY_OP:
                handled = False
                async for sse_chunk in _memory_bypass_stream(request):
                    handled = True
                    yield sse_chunk
                if handled:
                    return
                # If _memory_bypass_stream yielded nothing, it's ambiguous → fall through to agent loop
                logger.info("[MEMORY_BYPASS] Fell through to agent loop")

            # ── ACTION_REQUEST → handle writing tasks and destructive actions ──
            if query_class == QueryClass.ACTION_REQUEST:
                # Detect destructive workspace actions — route to agent loop for approval gate
                _DESTRUCTIVE_PATTERN = _re.compile(
                    r'\b(delete|remove|purge|clear|wipe)\b.{0,30}\b(document|file|upload|workspace)\b',
                    _re.IGNORECASE,
                )
                if _DESTRUCTIVE_PATTERN.search(request.task):
                    logger.info("[ACTION_REQUEST] Destructive action → routing to AgentLoop with approval gate")
                    query_class = QueryClass.TOOL_CALL
                    # Fall through to agent loop below
                else:
                    # Writing tasks (email, letter, essay, story) — direct LLM with writing prompt
                    _WRITING_PATTERN = _re.compile(
                        r'\b(write|compose|draft|create)\b.{0,20}\b(email|letter|essay|story|message|report|proposal|application)\b',
                        _re.IGNORECASE,
                    )
                    if _WRITING_PATTERN.search(request.task):
                        logger.info("[ACTION_REQUEST] Writing task → direct LLM stream")
                        _WRITING_SYSTEM = (
                            "You are ASTRA, a professional writing assistant. "
                            "Write exactly what the user asks for (email, letter, essay, etc.) "
                            "in proper format with appropriate greeting, body, and sign-off. "
                            "Use the details provided by the user. Output ONLY the written content."
                        )
                        model = request.model or settings.DEFAULT_MODEL
                        ollama = OllamaService(model_name=model)
                        async for chunk in ollama.stream_invoke(
                            prompt=request.task,
                            history=[{"role": "system", "content": _WRITING_SYSTEM}],
                        ):
                            if chunk.get("type") == "content":
                                yield f"data: {json.dumps(AgentStreamEvent(type='answer', content=chunk['content']).model_dump(exclude_none=True))}\n\n"
                            elif chunk.get("type") == "error":
                                yield f"data: {json.dumps(AgentStreamEvent(type='error', content=chunk['content']).model_dump(exclude_none=True))}\n\n"
                                yield "data: [DONE]\n\n"
                                return
                        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    else:
                        # Unsupported action type — graceful message
                        logger.info(f"[ACTION_REQUEST] Unsupported action: {request.task[:60]}")
                        event = AgentStreamEvent(
                            type="answer",
                            content="⚠️ This action type isn't available yet. I can currently help with:\n"
                                    "• **Writing**: emails, letters, essays, reports\n"
                                    "• **Documents**: search, summarize, delete\n"
                                    "• **Memory**: remember facts, recall preferences\n"
                                    "• **Search**: web lookups, weather, news\n"
                                    "• **Code**: run Python calculations\n\n"
                                    "What would you like me to do instead?"
                        )
                        yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
                        yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                        yield "data: [DONE]\n\n"
                        return

            # ── DELETE_DOCS_BYPASS — deterministic document deletion with approval ──
            # qwen2.5:3b can't reliably call deletion tools from the agent loop.
            # This bypass: regex match → approval gate → DB+filesystem+vector purge.
            _DELETE_DOCS_PATTERN = _re.compile(
                r'\b(delete|remove|purge|clear|wipe)\s+(all\s+)?(the\s+|my\s+)?(documents?|files?|uploads?|workspace)\b',
                _re.IGNORECASE,
            )
            if query_class == QueryClass.TOOL_CALL and _DELETE_DOCS_PATTERN.search(request.task):
                logger.info("[DELETE_BYPASS] Deletion request → deterministic bypass with approval gate")
                async for sse_chunk in _delete_all_documents_bypass_stream(request):
                    yield sse_chunk
                return

            # ── MATH_BYPASS — complex math directly to python_executor ─────
            # qwen2.5:3b doesn't reliably call tools from the agent loop.
            # For math expressions, we execute directly — guaranteed correct.
            if query_class == QueryClass.TOOL_CALL:
                expr_clean = _re.sub(r'^(calculate[:\s]*|compute[:\s]*|what\s+is\s+|what\'?s\s+)', '', request.task, flags=_re.IGNORECASE).strip()
                expr_clean = expr_clean.rstrip('?').strip()
                if _re.match(r'^[\d\s\(\)\.\+\-\*\/\%\^]+$', expr_clean):
                    expr_clean = expr_clean.replace('^', '**')
                    logger.info(f"[MATH_BYPASS] Executing directly: {expr_clean[:60]}")
                    async for sse_chunk in _math_bypass_stream(request):
                        yield sse_chunk
                    return

                _MATH_FUNC_PATTERN = _re.compile(
                    r'^[\d\s\(\)\.\+\-\*\/\%\^\,]*'
                    r'(sqrt|log|log10|log2|abs|pow|ceil|floor|round|sin|cos|tan|exp|pi)\b'
                    r'[\d\s\(\)\.\+\-\*\/\%\^\,\w]*$',
                    _re.IGNORECASE
                )
                if _MATH_FUNC_PATTERN.match(expr_clean):
                    logger.info(f"[MATH_BYPASS] Math function: {expr_clean[:60]}")
                    async for sse_chunk in _math_bypass_stream(request):
                        yield sse_chunk
                    return

            # ── WEB_SEARCH_BYPASS — search queries directly to DDG + LLM ───
            # On CPU, the agent loop does THINK(6min) → ACT(5s) → REFLECT(6min)
            # per iteration. With 3+ iterations, that's 30+ minutes for a
            # simple weather query. This bypass: 1 search + 1 LLM call = ~7min.
            # GUARD: Skip bypass if query needs reasoning (compare, research, etc.)
            if query_class == QueryClass.TOOL_CALL:
                if (
                    _WEB_SEARCH_QUERY_PATTERN.search(request.task)
                    and not _WEB_SEARCH_ANTI_PATTERN.search(request.task)
                ):
                    logger.info("[WEB_SEARCH_BYPASS] Direct search + LLM stream")
                    async for sse_chunk in _web_search_bypass_stream(request):
                        yield sse_chunk
                    return
                elif _WEB_SEARCH_QUERY_PATTERN.search(request.task):
                    logger.info("[WEB_SEARCH_BYPASS] SKIPPED — query needs reasoning (anti-pattern match)")

            # ── RAG_BYPASS — document queries with direct LLM streaming ────
            # Bypasses format=json and tool prompt that confuse the LLM.
            if query_class == QueryClass.RAG_QUERY:
                logger.info("[RAG_BYPASS] Streaming document-grounded answer")
                async for sse_chunk in _rag_bypass_stream(request):
                    yield sse_chunk
                return

            # ── MEMORY_OP / META / remaining TOOL_CALL → full agent loop ───
            if query_class == QueryClass.META:
                # Bypass: Deterministic document list
                if _LIST_DOCS_PATTERN.search(request.task):
                    from app.db import engine
                    from sqlmodel import Session
                    from sqlalchemy import text
                    
                    project_id = request.project_id or "default"
                    with Session(engine) as session:
                        rows = session.execute(
                            text("SELECT original_name FROM documents WHERE project_id = :pid"),
                            {"pid": project_id}
                        ).fetchall()
                        
                        if not rows:
                            answer = "You haven't uploaded any documents yet."
                        else:
                            names = "\n".join(f"- {r.original_name}" for r in rows)
                            answer = f"Documents in your workspace:\n{names}"
                        
                    yield f"data: {json.dumps(AgentStreamEvent(type='answer', content=answer).model_dump(exclude_none=True))}\n\n"
                    yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                
                # Bypass: Identity/Capability — use ASTRA persona prompt
                if _IDENTITY_CAPABILITY_PATTERN.search(request.task):
                    logger.info("[META_BYPASS] Identity/Capability detected — using ASTRA persona")
                    async for sse_chunk in _direct_llm_stream(request):
                        yield sse_chunk
                    return

            agent = AgentLoop(
                model_name=request.model,
                approval_mode="streaming",
            )

            async for event in agent.run(
                task=request.task,
                project_id=request.project_id,
                max_iterations=request.max_iterations,
                query_class=query_class.value,
            ):
                yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Agent endpoint error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': f'Agent error: {str(e)}'})}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/health")
async def agent_health():
    """Quick check that the agent system is operational."""
    from app.core.tool_registry import tool_registry
    from app.services.ollama import ollama_service

    ollama_ok = await ollama_service.health_check()
    tools = tool_registry.get_all_tools()

    return {
        "status": "healthy" if ollama_ok else "degraded",
        "ollama": "connected" if ollama_ok else "disconnected",
        "tools_registered": len(tools),
        "tool_names": [t["name"] for t in tools],
        "agent_version": "3.0",
    }


@router.post("/approve/{task_id}")
async def approve_task(task_id: str, approved: bool = Query(..., description="Whether the action is approved")):
    """Submit a decision for a pending approval request."""
    from app.agent.approval import approval_registry
    
    gate = approval_registry.get(task_id)
    if not gate:
        logger.warning(f"Approval request not found or expired: {task_id}")
        raise HTTPException(status_code=404, detail="Approval request not found or expired.")
    
    await gate.submit_decision(task_id, approved)
    return {"status": "ok", "message": "Decision submitted"}
