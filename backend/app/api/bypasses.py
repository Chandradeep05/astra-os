"""
ASTRA OS — Agent API Bypass Handlers
=====================================
Contains all direct deterministic bypass paths to optimize performance and reliability on local models.
"""

import json
import logging
import re as _re
import os as _os
import uuid as _uuid
from typing import Dict, Any

from app.agent.schemas import AgentRequest, AgentStreamEvent, RiskLevel
from app.services.ollama import OllamaService
from app.services.document_service import document_service
from app.services.vector_service import vector_service
from app.core.config import settings
from app.agent.approval import StreamingApprovalGate, approval_registry
from app.agent.memory import agent_memory
from app.tools.duckduckgo_search import DuckDuckGoSearchTool
from app.utils.tokens import enforce_budget
from app.db import engine
from sqlmodel import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Minimal system prompt used for DIRECT_LLM bypass.
_DIRECT_SYSTEM_PROMPT = (
    "You are ASTRA, an advanced personal AI operating system running locally on the user's machine. "
    "You are intelligent, concise, and always helpful. "
    "Respond clearly using plain text or standard Markdown (bold, italic, headers, bullets). "
    "Do not use custom tags or structured JSON wrappers. "
    "When asked who you are, explain you are ASTRA OS — a local-first AI assistant with memory, "
    "document intelligence, code execution, and web search capabilities."
)

async def _direct_llm_stream(request: AgentRequest):
    """
    DIRECT_LLM fast path — completely bypasses AgentLoop.
    """
    model = request.model or settings.DEFAULT_MODEL
    ollama = OllamaService(model_name=model)

    try:
        # Auto-wake if model is sleeping
        if not OllamaService._model_loaded:
            wake_event = AgentStreamEvent(type="thought", content="Waking up ASTRA...")
            yield f"data: {json.dumps(wake_event.model_dump(exclude_none=True))}\n\n"
            await ollama.warmup_model()

        async for chunk in ollama.stream_invoke(
            prompt=request.task,
            history=[{"role": "system", "content": _DIRECT_SYSTEM_PROMPT}],
        ):
            if chunk.get("type") == "content":
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


# ── MATH_BYPASS ─────────────────────────────────────────────────────────────
_MATH_QUERY_PATTERN = _re.compile(
    r'^(calculate[:\s]*|compute[:\s]*)?'
    r'([\d\s\(\)\.\+\-\*\/\%\^]+)$',
    _re.IGNORECASE,
)

async def _math_bypass_stream(request: AgentRequest):
    """Direct math execution using a safe eval context."""
    import math as _math

    expr = _re.sub(r'^(calculate[:\s]*|compute[:\s]*|what\s+is\s+|what\'?s\s+)', '', request.task, flags=_re.IGNORECASE).strip()
    expr = expr.rstrip('?').strip()

    math_safe_expr = expr
    for fn in ['sqrt', 'log', 'log10', 'log2', 'sin', 'cos', 'tan', 
               'ceil', 'floor', 'round', 'abs', 'pow', 'exp']:
        math_safe_expr = _re.sub(
            rf'\b{fn}\b', f'math.{fn}', math_safe_expr, flags=_re.IGNORECASE
        )
    math_safe_expr = math_safe_expr.replace('^', '**')

    try:
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


# ── MEMORY_BYPASS ───────────────────────────────────────────────────────────
_MEMORY_STORE_PATTERN = _re.compile(
    r'\b(remember that|don\'?t forget|keep in mind|store this|'
    r'my name is|i am |i\'?m |my favorite|i prefer|i hate|i love|i like|'
    r'i use |i switched|i work|i live|i study|i play|i enjoy|'
    r'i\'?m building|i\'?m using|i\'?m working|i\'?m pursuing|'
    r'my .+ is|i have a|remember my|remember this|please remember )\b',
    _re.IGNORECASE,
)

_MEMORY_RECALL_PATTERN = _re.compile(
    r'\b(what do you (know|remember|recall) about me|'
    r'what have you (remembered|memorized|stored)|'
    r'tell me about myself|what is my |what\'?s my |'
    r'do you (remember|know) my |'
    r'summarize what you know|what you know about me|'
    r'who am i|what are my )\b',
    _re.IGNORECASE,
)

_MEMORY_SENSITIVE_GUARD = _re.compile(
    r'\b(password|passwd|passphrase|secret|api.?key|access.?token'
    r'|private.?key|ssh.?key|credit.?card|social.?security|ssn'
    r'|pin.?code|\batm\b|\bpin\b|bank.?account|routing.?number|cvv|cvc)\b',
    _re.IGNORECASE,
)

_MEMORY_DELETE_PATTERN = _re.compile(
    r'\b(forget|delete|remove|erase|wipe|clear)\s+(.+?)\s*(from\s+(your\s+)?memory)?\s*$',
    _re.IGNORECASE,
)

async def _memory_bypass_stream(request: AgentRequest):
    """Memory operations → direct memorize/recall, bypassing unreliable LLM tool calling."""
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
                model = request.model or settings.DEFAULT_MODEL
                ollama = OllamaService(model_name=model)

                augmented = (
                    f"The user asked: {query}\n\n"
                    f"Here is what you remember about the user from your long-term memory:\n"
                    f"{recalled}\n\n"
                    f"Summarize these memories naturally as a direct response to the user. "
                    f"Be specific — mention each fact you recall."
                )

                # Auto-wake if model is sleeping
                if not OllamaService._model_loaded:
                    wake_event = AgentStreamEvent(type="thought", content="Waking up ASTRA...")
                    yield f"data: {json.dumps(wake_event.model_dump(exclude_none=True))}\n\n"
                    await ollama.warmup_model()

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

            fact = _re.sub(
                r'^(remember that|don\'?t forget that|keep in mind that|store this[:\s]*|please )',
                '', query, flags=_re.IGNORECASE
            ).strip()

            if not fact:
                fact = query

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

            topic_clean = _re.sub(
                r'^(my\s+|the\s+|about\s+|all\s+)', '', raw_topic,
                flags=_re.IGNORECASE
            ).strip()

            if not topic_clean:
                topic_clean = raw_topic

            deleted_count = await agent_memory.forget_fact(
                topic=topic_clean, project_id=project_id
            )

            if deleted_count > 0:
                event = AgentStreamEvent(
                    type="answer",
                    content=f"🗑️ Memory updated! I have forgotten {deleted_count} fact(s) matching **{topic_clean}**."
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

    except Exception as e:
        logger.error(f"[MEMORY_BYPASS] error: {e}", exc_info=True)
        err_event = AgentStreamEvent(type="error", content=f"Memory operation failed: {str(e)}")
        yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"


# ── DELETE_DOCS_BYPASS ──────────────────────────────────────────────────────
async def _delete_all_documents_bypass_stream(request: AgentRequest):
    """Deterministic deletion bypass that forces user confirmation via the approval gate."""
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

    # 3. Perform the database + filesystem + vector wipe
    try:
        yield f"data: {json.dumps(AgentStreamEvent(type='thought', content='Clearing files and vector chunks...').model_dump(exclude_none=True))}\n\n"

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
            file_path = _os.path.join("uploads", filename)
            if _os.path.exists(file_path):
                try:
                    _os.remove(file_path)
                except Exception:
                    pass
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


# ── RAG_BYPASS ──────────────────────────────────────────────────────────────
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
        from app.services.document_service import _extract_filename_from_query
        detected_file = _extract_filename_from_query(request.task)
        if detected_file:
            from app.api.documents import _ingestion_status
            
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

        best_sim = max((r.get("similarity", 0.0) for r in chunks), default=0.0)
        if confidence == "low" and best_sim < 0.01:
            logger.warning(f"[RAG_BYPASS] Best sim={best_sim:.4f} too weak — falling back to DIRECT_LLM")
            async for sse_chunk in _direct_llm_stream(request):
                yield sse_chunk
            return

        # Use 8192 for the token budget here too for consistency
        _, pruned_chunks = enforce_budget(
            system_prompt=_RAG_SYSTEM_PROMPT,
            history=[],
            rag_chunks=chunks,
            max_window=8192
        )

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

        # Auto-wake if model is sleeping
        if not OllamaService._model_loaded:
            wake_event = AgentStreamEvent(type="thought", content="Waking up ASTRA...")
            yield f"data: {json.dumps(wake_event.model_dump(exclude_none=True))}\n\n"
            await ollama.warmup_model()

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


# ── WEB_SEARCH_BYPASS ────────────────────────────────────────────────────────
_WEB_SEARCH_QUERY_PATTERN = _re.compile(
    r"\b("
    r"weather|forecast|temperature today|humidity today|rain today"
    r"|latest news|breaking news|headlines|news on|news about|news update"
    r"|latest.{1,30}updates|recent.{1,30}updates|current.{1,30}updates"
    r"|latest.{1,30}release|new.{1,30}release|what'?s new in"
    r"|stock price|share price|bitcoin price|crypto price|exchange rate"
    r"|market update|market trend"
    r"|score|match result|game result"
    r"|search the web|search online|google for"
    r")\b",
    _re.IGNORECASE,
)

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
    """
    search_tool = DuckDuckGoSearchTool()

    try:
        search_results = await search_tool.execute(query=request.task, max_results=3)

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

        if len(search_results) > 3000:
            search_results = search_results[:3000] + "\n\n[Results truncated for speed]"

        augmented_prompt = (
            f"[WEB SEARCH RESULTS]\n{search_results}\n\n"
            f"[USER QUESTION]\n{request.task}\n\n"
            "Answer the user's question concisely using the search results above. "
            "Keep your response under 300 words."
        )

        model = request.model or settings.DEFAULT_MODEL
        ollama = OllamaService(model_name=model)

        # Auto-wake if model is sleeping
        if not OllamaService._model_loaded:
            wake_event = AgentStreamEvent(type="thought", content="Waking up ASTRA...")
            yield f"data: {json.dumps(wake_event.model_dump(exclude_none=True))}\n\n"
            await ollama.warmup_model()

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
