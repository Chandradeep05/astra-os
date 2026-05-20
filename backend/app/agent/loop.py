"""
ASTRA OS — Core Cognitive Loop (OTPAR)
=======================================
The brain of the autonomous agent. Implements:

  OBSERVE  → Gather context (memory, history, prior tool results)
  THINK    → Reason about the task and decide next action
  PLAN     → Decompose into steps (embedded in the Think phase for efficiency)
  ACT      → Execute a tool call via native Ollama tool calling
  REFLECT  → Evaluate the result, decide if done or need another iteration

Design principles:
  - Simple state machine, NOT a graph framework (saves RAM + complexity)
  - Native Ollama tool calling (structured JSON, not regex parsing)
  - Streaming: every phase emits events so the UI stays responsive
  - Max 5 iterations per task to prevent infinite loops
  - Model-agnostic: works with llama3.2:3b, qwen2.5:3b, or any Ollama model
"""

import json
import re
import time
import uuid
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional

from app.agent.schemas import (
    AgentState, AgentStep, AgentPhase, ToolCall, ToolResult,
    AgentStreamEvent, RiskLevel,
)
from app.agent.memory import agent_memory
from app.agent.approval import ApprovalGate, get_approval_gate
from app.core.tool_registry import tool_registry
from app.core.prompt_builder import build_system_prompt  # Phase 1: dynamic prompt
import app.tools  # noqa: F401 - explicitly import to trigger tool registration in all contexts
from app.services.ollama import OllamaService
from app.core.config import settings
from app.services.safety_service import safety_service
from app.services.audit_service import audit_service
from app.services.document_service import document_service  # ASTRA-FIX: hard doc routing

logger = logging.getLogger(__name__)

# Hard iteration cap — prevents infinite loops without relying on caller-supplied max_iterations
MAX_ITERATIONS = 8

# ──────────────────────────────────────────────
#  System Prompt for the Agent
# ──────────────────────────────────────────────

# AGENT_SYSTEM_PROMPT is now built dynamically from user_rules.json
# via app.core.prompt_builder.build_system_prompt().
# Do NOT hardcode the system prompt here — edit user_rules.json instead.



def _sanitize_output(text: str) -> str:
    """Strip any ::...:: or :::...::: custom tags that the model may output.
    Acts as a safety net — the prompt already forbids them."""
    text = re.sub(r':{2,3}[^:]*:{2,3}', '', text)
    return text.strip()


def _build_reflection_prompt(task: str, steps: List[AgentStep], latest_result: str) -> str:
    """Build a prompt asking the agent to reflect on the latest tool result."""
    step_summary = ""
    for s in steps:
        if s.tool_call:
            status = "OK" if (s.tool_result and s.tool_result.success) else "FAIL"
            result_text = s.tool_result.output[:200] if s.tool_result else 'no result'
            step_summary += f"  [{status}] {s.tool_call.name}({s.tool_call.arguments}) -> {result_text}\n"

    return f"""Task the user asked for: {task}

Tools called so far:
{step_summary}
Latest tool result:
{latest_result}

Answer these questions BY RESPONDING ONLY WITH VALID JSON matching this exact schema:
{{
  "evaluation": "Was the tool result useful? (1 sentence)",
  "is_complete": true or false,
  "final_answer": "If is_complete is true, provide the final answer to the user here. Otherwise null."
}}
DO NOT OUTPUT ANY TEXT OUTSIDE THE JSON OBJECT."""


# ──────────────────────────────────────────────
#  Agent Loop
# ──────────────────────────────────────────────

class AgentLoop:
    """
    The core autonomous agent. Runs the OTPAR loop with native Ollama
    tool calling and human-in-the-loop approval for risky actions.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        approval_mode: str = "cli",
    ):
        self.model_name = model_name or settings.DEFAULT_MODEL
        self.ollama = OllamaService(model_name=self.model_name)
        self.approval_gate: ApprovalGate = get_approval_gate(approval_mode)

    async def run(
        self,
        task: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        project_id: str = "default",
        max_iterations: int = 5,
        query_class: str = None,  # None = full retrieval as safe fallback; set by classifier in agent.py
    ) -> AsyncGenerator[AgentStreamEvent, None]:
        """
        Execute the full OTPAR cognitive loop for a given task.
        Yields AgentStreamEvent objects as the agent progresses.
        """
        # Initialize state
        state = AgentState(
            task_id=uuid.uuid4().hex[:12],
            original_task=task,
            max_iterations=min(max_iterations, 8),  # Hard cap at 8 per PRD Phase 0
        )

        # Circuit breaker: track (tool_name, serialized_args) → call_count
        # If same tool called with same args ≥3 times → break loop
        _tool_call_counts: Dict[str, int] = {}

        # Apply safety redaction
        safe_task = safety_service.check_and_redact(task)
        await asyncio.to_thread(audit_service.log_action, "AGENT_TASK", f"Task: {safe_task[:100]}", project_id)

        history = conversation_history or []

        # Build tool list for the prompt (faster than native tool calling on CPU)
        tool_prompt = self._build_tool_prompt()

        yield AgentStreamEvent(
            type="phase_change", phase="observe",
            content=f"Starting task: {safe_task[:100]}..."
        )

        # ─── Compute context ONCE before the loop ───
        # Documents, memory, and conversation history are stable for the
        # duration of a task. Re-running build_context() each iteration
        # wastes 1 embedding call + 2 ChromaDB queries per iteration for an
        # identical result. working_memory="" is correct here: tool results
        # accumulate in state.working_memory and are already injected into
        # the user message on iterations 1+ via the progress block.
        cached_context = await agent_memory.build_context(
            task=safe_task,
            conversation_history=history,
            working_memory="",
            project_id=project_id,
            query_class=query_class,  # FIX-3: skip ChromaDB unless RAG_QUERY
        )

        # ASTRA-FIX: Hard routing for document queries
        DOC_TRIGGER_PHRASES = [
            "my document", "my file", "from my document",
            "according to my document", "in my document",
            "from my file", "in my file", "summarize my",
        ]

        normalized_query = safe_task.lower()
        forced_doc_context = ""

        # Detect explicit filename references (e.g., "circuit_system_solutions.docx")
        import re as _re
        _fn_match = _re.search(r'([\w\-]+\.(?:docx|pdf|txt|xlsx|pptx|csv|md|json))', safe_task, _re.IGNORECASE)
        detected_filename = _fn_match.group(1) if _fn_match else None

        # Trigger on EITHER doc-trigger phrases OR explicit filename
        # Trigger on EITHER doc-trigger phrases OR explicit filename
        # Multi-intent check: if query contains "and", "weather", "search", or math ops, 
        # do NOT early-exit. Let the agent loop handle decomposition.
        _MULTI_INTENT_PATTERN = _re.compile(r'\b(and|also|weather|search|google|calculate)\b', _re.IGNORECASE)
        is_multi_intent = bool(_MULTI_INTENT_PATTERN.search(safe_task))

        should_force_doc = query_class == "RAG_QUERY" and (
            any(kw in normalized_query for kw in DOC_TRIGGER_PHRASES)
            or detected_filename is not None
        )

        chunks = []
        if should_force_doc:
            logger.info(f"[ASTRA-ROUTING] Retrieving documents (filename={detected_filename})")
            
            search_kwargs = {
                "query": safe_task,
                "project_id": project_id,
                "limit": 5,
                "query_class": query_class,
            }

            search_response = await document_service.search_similar(**search_kwargs)
            confidence = search_response.get("confidence_level", "none")
            chunks = search_response.get("results", [])

            # Only early-exit if it's NOT multi-intent and we have a definitive answer/failure
            if not is_multi_intent:
                if confidence == "none" or not chunks:
                    yield AgentStreamEvent(
                        type="answer",
                        content="I couldn't find that information in your uploaded documents.",
                    )
                    yield AgentStreamEvent(type="done")
                    return
                
                # If high confidence and simple query, we COULD exit here, but 
                # for now let's just prep the context and let the loop run for 
                # better reasoning, unless it's a pure summary.
                if "summarize" in normalized_query and confidence == "high":
                    pass # Continue to loop for better summary formatting
            
        # Token Budget Enforcement (MAX_CONTEXT_WINDOW = 4096)
        from app.utils.tokens import enforce_budget
        real_system_prompt = build_system_prompt(project_id) + "\n\n" + self._build_tool_prompt()
        history, pruned_chunks = enforce_budget(
            system_prompt=real_system_prompt,
            history=history,
            rag_chunks=chunks,
            max_window=4096
        )
        if should_force_doc:
            forced_doc_context = "\n\n".join(r["content"] for r in pruned_chunks)

        # ─── Main cognitive loop ───
        while state.current_iteration < state.max_iterations and not state.is_complete:
            # ── Explicit iteration cap guard (MAX_ITERATIONS = 8) ──
            if state.current_iteration >= MAX_ITERATIONS:
                partial = state.get_working_context() or "No result generated."
                logger.warning(
                    f"[OTPAR] Max iterations ({MAX_ITERATIONS}) reached. "
                    f"Query: {safe_task[:80]}"
                )
                yield AgentStreamEvent(
                    type="answer",
                    content=_sanitize_output(
                        f"⚠ Agent reached step limit. Showing partial result.\n\n{partial}"
                    ),
                )
                yield AgentStreamEvent(type="done")
                return

            step = AgentStep(iteration=state.current_iteration)

            try:
                # ════════════════════════════════════
                # PHASE 1: OBSERVE — assign cached context
                # ════════════════════════════════════
                step.phase = AgentPhase.OBSERVE
                yield AgentStreamEvent(type="phase_change", phase="observe")

                context = cached_context
                step.observation = context if context else "No prior context available."

                # ════════════════════════════════════
                # PHASE 2+3: THINK & PLAN — reason about the task
                # ════════════════════════════════════
                step.phase = AgentPhase.THINK
                yield AgentStreamEvent(type="phase_change", phase="think")

                # Build the messages for Ollama
                # build_system_prompt() reads user_rules.json (cached, invalidated on file change)
                system_content = build_system_prompt(project_id) + "\n\n" + tool_prompt
                messages = [{"role": "system", "content": system_content}]

                # Add the task — context is prepended INTO the user message, NOT as a
                # second system message. qwen2.5:3b (and most small SLMs) reliably
                # attend to only the first system message. A second system message is
                # effectively ignored, causing all retrieved documents and memory to be
                # silently discarded before the model reasons about the task.
                if state.current_iteration == 0:
                    # ASTRA-FIX: Prepend forced doc context when hard-routing triggered
                    if forced_doc_context:                                         # ASTRA-FIX
                        context = f"[RELEVANT KNOWLEDGE]\n{forced_doc_context}\n\n" + context  # ASTRA-FIX
                    user_content = f"{context}\n\n{safe_task}" if context else safe_task
                    messages.append({"role": "user", "content": user_content})
                else:
                    # On subsequent iterations, include what we've learned so far.
                    # Cap to prevent token overflow when tool outputs are verbose.
                    _PROGRESS_MAX_CHARS = 1500
                    progress = state.get_working_context()
                    if len(progress) > _PROGRESS_MAX_CHARS:
                        progress = "...[earlier steps truncated]\n\n" + progress[-_PROGRESS_MAX_CHARS:]
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Original task: {safe_task}\n\n"
                            f"Progress so far:\n{progress}\n\n"
                            "Continue working on the task. Use a tool if needed, "
                            "or provide your FINAL ANSWER if you have enough information."
                        ),
                    })

                # ════════════════════════════════════
                # Call Ollama (tools embedded in prompt — faster on CPU)
                # ════════════════════════════════════
                response = await self.ollama.invoke_with_tools(
                    messages=messages,
                    tools=None,  # Don't use native tool calling (40x slower on CPU)
                    format="json", # Force JSON to prevent hallucinated narrative
                )

                if response is None:
                    yield AgentStreamEvent(type="error", content="Ollama returned no response")
                    state.error = "No response from Ollama"
                    break

                # Extract the response content and any tool calls
                message = response.get("message", {})
                content = message.get("content", "")
                tool_calls = message.get("tool_calls", [])

                # ════════════════════════════════════
                # FALLBACK: Parse tool calls from text
                # ════════════════════════════════════
                # Some models (llama3.2:3b) output tool calls as raw JSON
                # text instead of structured tool_calls. Parse it out.
                if not tool_calls and content:
                    parsed = self._try_parse_tool_from_text(content)
                    if parsed:
                        tool_calls = [parsed]
                        content = ""  # Clear — it was a tool call, not text

                step.thought = content
                if content:
                    yield AgentStreamEvent(type="thought", content=content)

                # ════════════════════════════════════
                # Check if the agent wants to give a FINAL ANSWER
                # (no tool calls = direct answer)
                # ════════════════════════════════════
                if not tool_calls:
                    # ─── FIX: Extract final_answer from JSON payload ───
                    clean_content = content.strip()
                    md_match = re.search(r'```(?:json)?\s*(.*?)\s*```', clean_content, re.DOTALL | re.IGNORECASE)
                    if md_match:
                        clean_content = md_match.group(1).strip()
                    else:
                        clean_content = re.sub(r'^```(?:json)?\s*', '', clean_content, flags=re.IGNORECASE)
                        clean_content = re.sub(r'\s*```$', '', clean_content)
                    
                    is_missed_tool = False
                    try:
                        data = json.loads(clean_content)
                        if "tool" in data or "function" in data:
                            # Model meant to call a tool, but it bypassed _try_parse_tool_from_text
                            is_missed_tool = True
                            fname = data.get("tool", data.get("function", {}).get("name", ""))
                            fargs = data.get("arguments", data.get("parameters", data.get("function", {}).get("arguments", {})))
                            if fname:
                                tool_calls = [{"function": {"name": fname, "arguments": fargs}}]
                        else:
                            # Try multiple common key names models use for the answer.
                            # Falls back to raw content only as last resort.
                            final_ans = (
                                data.get("final_answer")
                                or data.get("answer")
                                or data.get("response")
                                or data.get("text")
                                or data.get("message")
                                or content
                            )
                    except json.JSONDecodeError:
                        final_ans = content

                    if not is_missed_tool:
                        final_ans = _sanitize_output(str(final_ans))
                        state.final_answer = final_ans
                        state.is_complete = True
                        state.current_phase = AgentPhase.COMPLETE

                        yield AgentStreamEvent(type="answer", content=final_ans)
                        yield AgentStreamEvent(type="done")

                        # Record success in episodic memory
                        agent_memory.record_task_completion(
                            task=safe_task,
                            tools_used=[s.tool_call.name for s in state.steps if s.tool_call],
                            success=True,
                            summary=str(final_ans)[:200],
                            project_id=project_id,
                        )
                        break

                # ════════════════════════════════════
                # PHASE 4: ACT — execute the tool call
                # ════════════════════════════════════
                step.phase = AgentPhase.ACT

                # Process the first tool call (one at a time for safety)
                tc = tool_calls[0]
                func_name = tc.get("function", {}).get("name", "")
                func_args = tc.get("function", {}).get("arguments", {})

                # Parse arguments if they're a string
                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args)
                    except json.JSONDecodeError:
                        func_args = {}

                # Force project_id context to secure isolation
                if func_name in ["document_search", "long_term_memory", "memory_recall"]:
                    if "project_id" in func_args and func_args["project_id"] != project_id:
                        logger.warning(f"Overriding mismatched project_id in {func_name}")
                    func_args["project_id"] = project_id

                step.tool_call = ToolCall(name=func_name, arguments=func_args)

                yield AgentStreamEvent(
                    type="tool_call",
                    content=f"Calling: {func_name}",
                    data={"tool": func_name, "arguments": func_args},
                )

                # ─── Approval check ───
                tool_def = tool_registry.get_tool(func_name)
                if tool_def is None:
                    result = ToolResult(
                        tool_name=func_name, success=False,
                        output=f"Unknown tool: {func_name}", error="Tool not found",
                    )
                    step.tool_result = result
                    state.add_observation(f"Tool '{func_name}' not found")
                    state.steps.append(step)
                    state.current_iteration += 1
                    continue

                # ─── Circuit breaker: same tool + same args ≥3 times ───
                # Prevents infinite retry loops on failing or wrong tool calls.
                # Key = tool_name + JSON-serialized sorted args
                try:
                    _args_key = f"{func_name}::{json.dumps(func_args, sort_keys=True)}"
                except (TypeError, ValueError):
                    _args_key = f"{func_name}::unserializable"

                _tool_call_counts[_args_key] = _tool_call_counts.get(_args_key, 0) + 1

                if _tool_call_counts[_args_key] >= 3:
                    _circuit_msg = (
                        f"Tool '{func_name}' was called with the same arguments "
                        f"{_tool_call_counts[_args_key]} times without success. "
                        "Stopping to avoid an infinite loop. "
                        f"Here is what I gathered so far:\n\n{state.get_working_context()}"
                    )
                    logger.warning(
                        f"[CIRCUIT BREAKER] {func_name} called {_tool_call_counts[_args_key]}x "
                        f"with same args. Breaking loop. Task: {safe_task[:80]}"
                    )
                    state.final_answer = _circuit_msg
                    state.is_complete = True
                    yield AgentStreamEvent(type="answer", content=_circuit_msg)
                    yield AgentStreamEvent(type="done")
                    return

                risk = getattr(tool_def, "risk_level", RiskLevel.SAFE)

                if self.approval_gate.should_require_approval(risk):
                    yield AgentStreamEvent(
                        type="approval_required",
                        content=f"⚠️ Risky action requires approval: {func_name}",
                        data={"tool": func_name, "arguments": func_args, "risk": risk.value},
                    )

                    approved = await self.approval_gate.request_approval(
                        tool_name=func_name,
                        arguments=func_args,
                        risk_level=risk,
                        description=tool_def.description,
                    )

                    if not approved:
                        result = ToolResult(
                            tool_name=func_name, success=False,
                            output="Action rejected by user", approved=False,
                        )
                        step.tool_result = result
                        state.add_observation(f"User REJECTED action: {func_name}")
                        yield AgentStreamEvent(
                            type="tool_result",
                            content="❌ Action rejected by user",
                            data={"tool": func_name, "approved": False},
                        )
                        state.steps.append(step)
                        state.current_iteration += 1
                        continue

                # ─── Execute the tool ───
                start_time = time.time()
                try:
                    await asyncio.to_thread(
                        audit_service.log_action,
                        "AGENT_TOOL", f"Execute: {func_name}({func_args})", project_id,
                    )
                    output = await tool_registry.execute(func_name, **func_args)
                    elapsed = (time.time() - start_time) * 1000

                    result = ToolResult(
                        tool_name=func_name, success=True,
                        output=str(output)[:2000],  # Cap output to save context window
                        execution_time_ms=elapsed,
                    )
                except Exception as e:
                    elapsed = (time.time() - start_time) * 1000
                    logger.error(f"Tool {func_name} failed: {e}")
                    result = ToolResult(
                        tool_name=func_name, success=False,
                        output="", error=str(e), execution_time_ms=elapsed,
                    )

                step.tool_result = result

                # ─── Tool failure handler ───
                # On failure: inject a structured TOOL_FAILED observation into
                # working_memory so the reflection step explicitly sees the error
                # and is forced to try a different approach next iteration.
                if not result.success:
                    _fail_key = f"__fail_{func_name}"
                    _tool_call_counts[_fail_key] = _tool_call_counts.get(_fail_key, 0) + 1
                    _fail_count = _tool_call_counts[_fail_key]

                    _fail_note = (
                        f"[TOOL_FAILED] Tool '{func_name}' raised an error: {result.error}. "
                        f"This is failure #{_fail_count} for this tool. "
                    )
                    if _fail_count >= 2:
                        _fail_note += (
                            f"DO NOT call '{func_name}' again. "
                            "Switch to a completely different approach or answer from available information."
                        )
                    state.add_observation(_fail_note)
                    logger.warning(
                        f"[TOOL_FAILURE #{_fail_count}] {func_name}: {result.error}"
                    )
                else:
                    state.add_observation(
                        f"Tool {func_name}: ✅ {result.output[:300]}"
                    )

                yield AgentStreamEvent(
                    type="tool_result",
                    content=result.output[:500] if result.success else f"Error: {result.error}",
                    data={
                        "tool": func_name, "success": result.success,
                        "time_ms": result.execution_time_ms,
                    },
                )

                # ════════════════════════════════════
                # PHASE 5: REFLECT — self-evaluate tool result
                # ════════════════════════════════════
                # Ask the model: was this result useful? Is the task done?
                # If yes → emit final answer immediately (saves 1+ iterations).
                # If no  → continue loop with explicit awareness of what failed.
                step.phase = AgentPhase.REFLECT
                yield AgentStreamEvent(type="phase_change", phase="reflect")

                reflection_prompt = _build_reflection_prompt(
                    task=safe_task,
                    steps=state.steps + [step],
                    latest_result=result.output[:1000],
                )
                reflection_response = await self.ollama.invoke_with_tools(
                    messages=[{"role": "user", "content": reflection_prompt}],
                    format="json",
                )
                if reflection_response:
                    ref_content = reflection_response.get("message", {}).get("content", "")
                    try:
                        ref_data = json.loads(ref_content)
                        step.reflection = ref_data.get("evaluation", "")
                        if step.reflection:
                            yield AgentStreamEvent(type="reflection", content=step.reflection)

                        if ref_data.get("is_complete") is True:
                            final_ans = ref_data.get("final_answer") or ""
                            if final_ans:
                                final_ans = _sanitize_output(final_ans)
                                state.final_answer = final_ans
                                state.is_complete = True
                                state.current_phase = AgentPhase.COMPLETE
                                yield AgentStreamEvent(type="answer", content=final_ans)
                                yield AgentStreamEvent(type="done")
                                agent_memory.record_task_completion(
                                    task=safe_task,
                                    tools_used=[
                                        s.tool_call.name for s in state.steps if s.tool_call
                                    ] + [func_name],
                                    success=True,
                                    summary=str(final_ans)[:200],
                                    project_id=project_id,
                                )
                    except json.JSONDecodeError:
                        pass  # Reflection parse failed — continue loop normally

            except Exception as e:
                logger.error(f"Agent loop error at iteration {state.current_iteration}: {e}", exc_info=True)
                step.phase = AgentPhase.ERROR
                yield AgentStreamEvent(type="error", content=f"Agent error: {str(e)}")
                state.error = str(e)
                break

            finally:
                state.steps.append(step)
                state.current_iteration += 1

        # ─── Loop exhausted without completion ───
        if not state.is_complete:
            if state.error:
                msg = f"Agent encountered an error: {state.error}"
            else:
                # Compile what we learned into a best-effort answer
                observations = state.get_working_context()
                msg = (
                    f"I reached the maximum of {state.max_iterations} iterations. "
                    f"Here's what I found:\n\n{observations}"
                )

            msg = _sanitize_output(msg)
            state.final_answer = msg
            yield AgentStreamEvent(type="answer", content=msg)
            yield AgentStreamEvent(type="done")

            agent_memory.record_task_completion(
                task=safe_task,
                tools_used=[s.tool_call.name for s in state.steps if s.tool_call],
                success=False,
                summary=msg[:200],
                project_id=project_id,
            )

    def _build_tool_prompt(self) -> str:
        """Build a tool list as text for the system prompt."""
        tools = tool_registry.get_all_tools()
        if not tools:
            return ""

        lines = ["## AVAILABLE TOOLS\n"]
        lines.append("To call a tool, you MUST respond with ONLY a JSON object matching this exact structure:")
        lines.append('```json')
        lines.append('{')
        lines.append('  "tool": "the_tool_name_here",')
        lines.append('  "arguments": {')
        lines.append('    "param_name": "param_value"')
        lines.append('  }')
        lines.append('}')
        lines.append('```')
        lines.append("Do NOT just output the arguments. You MUST include the \"tool\" and \"arguments\" keys.")
        lines.append("Do NOT add any text before or after the JSON when calling a tool.\n")
        lines.append("Tools:")

        for t in tools:
            params = t.get("parameters", {}).get("properties", {})
            required = t.get("parameters", {}).get("required", [])
            param_strs = []
            for pname, pdef in params.items():
                req = "*" if pname in required else ""
                desc = pdef.get("description", "")
                param_strs.append(f"    - {pname}{req}: {desc}")

            lines.append(f"\n**{t['name']}**: {t['description']}")
            if param_strs:
                lines.append("  Parameters:")
                lines.extend(param_strs)

        return "\n".join(lines)

    def _try_parse_tool_from_text(self, text: str) -> Optional[Dict]:
        """Try to extract a tool call from freeform text output.
        
        Models like llama3.2:3b output tool calls as raw JSON text
        instead of structured tool_calls. This parses common patterns:
          1. {"tool": "name", "arguments": {...}}
          2. {"name": "tool_name", "parameters": {...}}
          3. Tool call in a markdown code block
        """
        if not text:
            return None

        # Get known tool names for validation
        known_tools = {t["name"] for t in tool_registry.get_all_tools()}

        # Strip markdown code block wrappers wherever they exist
        clean = text.strip()
        md_match = re.search(r'```(?:json)?\s*(.*?)\s*```', clean, re.DOTALL | re.IGNORECASE)
        if md_match:
            clean = md_match.group(1).strip()
        else:
            clean = re.sub(r'^```(?:json)?\s*', '', clean, flags=re.IGNORECASE)
            clean = re.sub(r'\s*```$', '', clean)
        clean = clean.strip()

        # Try to find JSON in the text (specifically look for curly braces containing tool keys)
        json_patterns = [
            r'(\{\s*(?:"tool"|"name"|"thought"|"function").*?\})',
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, clean, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)

                    # Pattern 1: {"tool": "name", "arguments": {...}}
                    if "tool" in data and data["tool"] in known_tools:
                        return {
                            "function": {
                                "name": data["tool"],
                                "arguments": data.get("arguments", data.get("params", {})),
                            }
                        }

                    # Pattern 2: {"name": "name", "parameters": {...}}
                    if "name" in data and data["name"] in known_tools:
                        return {
                            "function": {
                                "name": data["name"],
                                "arguments": data.get("parameters", data.get("arguments", {})),
                            }
                        }

                    # Pattern 3: {"function": {"name": "...", "arguments": {...}}}
                    if "function" in data and isinstance(data["function"], dict):
                        fname = data["function"].get("name", "")
                        if fname in known_tools:
                            return data

                except (json.JSONDecodeError, TypeError):
                    continue

        return None
