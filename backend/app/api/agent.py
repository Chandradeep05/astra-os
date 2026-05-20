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
from app.agent.classifier import classify_query, QueryClass, split_intents
from app.services.audit_service import audit_service
from app.services.ollama import OllamaService
from app.services.document_service import document_service
from app.core.config import settings
import logging
import json
import re as _re

router = APIRouter()
logger = logging.getLogger(__name__)

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

from app.api.bypasses import (
    _direct_llm_stream,
    _math_bypass_stream,
    _memory_bypass_stream,
    _delete_all_documents_bypass_stream,
    _rag_bypass_stream,
    _web_search_bypass_stream,
    _WEB_SEARCH_QUERY_PATTERN,
    _WEB_SEARCH_ANTI_PATTERN,
)

async def _route_single_intent(
    request: AgentRequest, query_class: QueryClass, max_iters: int = 3
):
    """
    Route a single classified intent through the appropriate bypass or AgentLoop.
    Strips stream-termination events (type=done, [DONE]) so the caller can
    control when the overall SSE stream ends.
    """

    async def _dispatch():
        """Select and execute the handler for this query class."""

        if query_class == QueryClass.DIRECT_LLM:
            async for chunk in _direct_llm_stream(request):
                yield chunk
            return

        if query_class == QueryClass.MEMORY_OP:
            handled = False
            try:
                async for chunk in _memory_bypass_stream(request):
                    handled = True
                    yield chunk
            except Exception as e:
                logger.error(f"[MEMORY_BYPASS] error in sub-intent: {e}", exc_info=True)
                err_event = AgentStreamEvent(type="error", content=f"Memory operation failed: {str(e)}")
                yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                handled = True
            if handled:
                return

        if query_class == QueryClass.RAG_QUERY:
            async for chunk in _rag_bypass_stream(request):
                yield chunk
            return

        if query_class == QueryClass.META:
            async for chunk in _direct_llm_stream(request):
                yield chunk
            return

        if query_class == QueryClass.ACTION_REQUEST:
            _SUB_WRITING_RE = _re.compile(
                r'\b(write|compose|draft|create)\b.{0,20}'
                r'\b(email|letter|essay|story|message|report|proposal|application)\b',
                _re.IGNORECASE,
            )
            if _SUB_WRITING_RE.search(request.task):
                _WRITING_SYS = (
                    "You are ASTRA, a professional writing assistant. "
                    "Write exactly what the user asks for in proper format "
                    "with appropriate greeting, body, and sign-off. "
                    "Output ONLY the written content."
                )
                model = request.model or settings.DEFAULT_MODEL
                ollama = OllamaService(model_name=model)
                async for chunk in ollama.stream_invoke(
                    prompt=request.task,
                    history=[{"role": "system", "content": _WRITING_SYS}],
                ):
                    if chunk.get("type") == "content":
                        ev = AgentStreamEvent(type="answer", content=chunk["content"])
                        yield f"data: {json.dumps(ev.model_dump(exclude_none=True))}\n\n"
                yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
                return
            # Non-writing ACTION_REQUEST → unsupported as sub-intent
            ev = AgentStreamEvent(
                type="answer",
                content="\u26a0\ufe0f This action type isn't available yet as a sub-task."
            )
            yield f"data: {json.dumps(ev.model_dump(exclude_none=True))}\n\n"
            yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
            yield "data: [DONE]\n\n"
            return

        if query_class == QueryClass.TOOL_CALL:
            # Math bypass
            expr_clean = _re.sub(
                r'^(calculate[:\s]*|compute[:\s]*|what\s+is\s+|what\'?s\s+)',
                '', request.task, flags=_re.IGNORECASE
            ).strip().rstrip('?').strip()
            if _re.match(r'^[\d\s\(\)\.\+\-\*\/\%\^]+$', expr_clean):
                expr_clean = expr_clean.replace('^', '**')
                async for chunk in _math_bypass_stream(request):
                    yield chunk
                return

            _MATH_FUNC = _re.compile(
                r'^[\d\s\(\)\.\+\-\*\/\%\^\,]*'
                r'(sqrt|log|log10|log2|abs|pow|ceil|floor|round|sin|cos|tan|exp|pi)\b'
                r'[\d\s\(\)\.\+\-\*\/\%\^\,\w]*$',
                _re.IGNORECASE
            )
            if _MATH_FUNC.match(expr_clean):
                async for chunk in _math_bypass_stream(request):
                    yield chunk
                return

            # Web search bypass (simple queries only — no reasoning)
            if (
                _WEB_SEARCH_QUERY_PATTERN.search(request.task)
                and not _WEB_SEARCH_ANTI_PATTERN.search(request.task)
            ):
                async for chunk in _web_search_bypass_stream(request):
                    yield chunk
                return

        # Fallback: full AgentLoop with reduced iterations
        agent = AgentLoop(model_name=request.model, approval_mode="streaming")
        async for event in agent.run(
            task=request.task,
            project_id=request.project_id,
            max_iterations=max_iters,
            query_class=query_class.value,
        ):
            yield f"data: {json.dumps(event.model_dump(exclude_none=True))}\n\n"
        yield "data: [DONE]\n\n"

    # Filter out stream-termination events — the caller emits these once at the end
    async for chunk in _dispatch():
        stripped = chunk.strip()
        if stripped == "data: [DONE]":
            continue
        if stripped.startswith("data: "):
            try:
                payload = json.loads(stripped[6:])
                if isinstance(payload, dict) and payload.get("type") == "done":
                    continue
            except (json.JSONDecodeError, ValueError):
                pass
        yield chunk


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

            # ── MULTI-INTENT SPLIT ─────────────────────────────────
            sub_intents = split_intents(request.task)
            if len(sub_intents) > 1:
                import asyncio as _aio
                logger.info(f"[MULTI-INTENT] Split into {len(sub_intents)} intents: {sub_intents}")
                for i, sub_task in enumerate(sub_intents, 1):
                    sep_event = AgentStreamEvent(
                        type="thought",
                        content=f"Processing part {i}/{len(sub_intents)}: {sub_task.strip()}"
                    )
                    yield f"data: {json.dumps(sep_event.model_dump(exclude_none=True))}\n\n"

                    try:
                        sub_class = await _aio.wait_for(classify_query(sub_task), timeout=5.0)
                    except _aio.TimeoutError:
                        sub_class = QueryClass.DIRECT_LLM

                    logger.info(f"[MULTI-INTENT] Sub-intent {i}: [{sub_class.value}] {sub_task[:60]}")

                    sub_request = AgentRequest(
                        task=sub_task,
                        project_id=request.project_id,
                        model=request.model,
                    )

                    async for sse_chunk in _route_single_intent(
                        sub_request, sub_class,
                        max_iters=min(request.max_iterations, 3),
                    ):
                        yield sse_chunk

                yield f"data: {json.dumps(AgentStreamEvent(type='done').model_dump(exclude_none=True))}\n\n"
                yield "data: [DONE]\n\n"
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
                try:
                    async for sse_chunk in _memory_bypass_stream(request):
                        handled = True
                        yield sse_chunk
                except Exception as e:
                    logger.error(f"[MEMORY_BYPASS] error in route: {e}", exc_info=True)
                    err_event = AgentStreamEvent(type="error", content=f"Memory operation failed: {str(e)}")
                    yield f"data: {json.dumps(err_event.model_dump(exclude_none=True))}\n\n"
                    yield "data: [DONE]\n\n"
                    handled = True
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


@router.get("/health")
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


@router.get("/stats")
async def get_system_stats():
    """Real-time system stats for Dashboard."""
    from app.db import engine
    from sqlmodel import Session
    from sqlalchemy import text
    import psutil

    try:
        with Session(engine) as session:
            doc_count = session.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 0
            episode_count = session.execute(text("SELECT COUNT(*) FROM episodic_memory")).scalar() or 0
    except Exception as e:
        logger.error(f"Error querying database stats: {e}")
        doc_count = 0
        episode_count = 0

    try:
        from app.services.ollama import ollama_service
        ollama_ok = await ollama_service.health_check()
    except Exception:
        ollama_ok = False

    try:
        ram_pct = psutil.virtual_memory().percent
        cpu_pct = psutil.cpu_percent(interval=0.1)
    except Exception:
        ram_pct = 0.0
        cpu_pct = 0.0

    return {
        "documents_indexed": doc_count,
        "episodic_memories": episode_count,
        "ollama_status": "connected" if ollama_ok else "disconnected",
        "model_name": settings.DEFAULT_MODEL,
        "ram_usage_percent": ram_pct,
        "cpu_percent": cpu_pct,
    }


@router.get("/settings")
async def get_settings():
    """Return user_rules.json contents."""
    import json
    import os
    rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "user_rules.json")
    if not os.path.exists(rules_path):
        with open(rules_path, "w") as f:
            json.dump({"rules": []}, f, indent=2)
    with open(rules_path, "r") as f:
        return json.load(f)


@router.put("/settings")
async def update_settings(rules: dict):
    """Update user_rules.json and clear prompt builder cache."""
    import json
    import os
    rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "user_rules.json")
    with open(rules_path, "w") as f:
        json.dump(rules, f, indent=2)
    try:
        import app.core.prompt_builder as pb
        pb._cached_rules = None
        pb._rules_mtime = 0.0
        logger.info("Prompt builder cache invalidated after settings update.")
    except Exception as e:
        logger.warning(f"Failed to invalidate prompt cache: {e}")
    return {"status": "saved"}


@router.get("/tasks")
async def get_background_tasks(project_id: str = "default"):
    """Fetch background task logs (audit logs) and registered workflows."""
    from app.db import engine
    from sqlmodel import Session, select
    from sqlalchemy import text
    from app.models.workflow import WorkflowModel

    # 1. Fetch recent audit logs relating to workflows, ingestion, and agent actions
    logs = []
    try:
        with Session(engine) as session:
            # Fetch latest 50 logs for the project
            rows = session.execute(
                text("""
                    SELECT id, project_id, action_type, details, created_at
                    FROM audit_logs
                    WHERE project_id = :pid
                    ORDER BY created_at DESC
                    LIMIT 50
                """),
                {"pid": project_id}
            ).fetchall()
            for r in rows:
                logs.append({
                    "id": r.id,
                    "project_id": r.project_id,
                    "action_type": r.action_type,
                    "details": r.details,
                    "created_at": str(r.created_at) if r.created_at else None
                })
    except Exception as e:
        logger.error(f"Error fetching task logs: {e}")

    # 2. Fetch registered workflows
    workflows = []
    try:
        with Session(engine) as session:
            db_wfs = session.exec(select(WorkflowModel).where(WorkflowModel.project_id == project_id)).all()
            for wf in db_wfs:
                workflows.append({
                    "id": wf.id,
                    "name": wf.name,
                    "description": wf.description,
                    "status": wf.status,
                    "last_run": wf.last_run.isoformat() if wf.last_run else None,
                    "created_at": wf.created_at.isoformat() if wf.created_at else None,
                })
    except Exception as e:
        logger.error(f"Error fetching workflows: {e}")

    return {
        "logs": logs,
        "workflows": workflows
    }

