"""
ASTRA OS — Legacy LLM Router (DEPRECATED)
============================================
⚠️  THIS MODULE IS DEPRECATED. Do not add features here.

The /api/v1/chat endpoint that used this router has been retired (HTTP 410).
This module is ONLY kept alive because workflows.py still imports llm_router
for background workflow execution. In Phase 1, migrate workflows to use the
new agent loop and then delete this file entirely.

New code should use: app.agent.loop.AgentLoop
"""

from app.services.ollama import OllamaService
from app.core.config import settings
from app.services.safety_service import safety_service
from app.services.audit_service import audit_service
from app.core.agent_factory import agent_factory
from app.core.tool_registry import tool_registry
from typing import Tuple, Dict, Any, List
import re
import json
import logging

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes prompts to the optimal local model engine.
    All models are served by Ollama — 100% local, zero cloud dependency.
    """

    def __init__(self):
        # Map engine types to actual locally-available model names
        self.engines = {
            "fast": settings.DEFAULT_MODEL,         # qwen2.5:3b — fastest
            "pro": settings.DEFAULT_MODEL,          # qwen2.5:3b — best quality
            "code": settings.DEFAULT_MODEL,         # qwen2.5:3b for code tasks
        }
        # Cache OllamaService instances so we don't recreate on every request
        self._services: Dict[str, OllamaService] = {}

    def _get_service(self, model_name: str) -> OllamaService:
        """Get or create a cached OllamaService for a given model."""
        if model_name not in self._services:
            self._services[model_name] = OllamaService(model_name=model_name)
        return self._services[model_name]

    async def route_and_stream(self, prompt: str, history: List[Dict[str, str]], project_id: str = "default"):
        """
        Core streaming pipeline:
        1. Select the right engine + agent persona
        2. Stream tokens directly from Ollama
        3. Optionally detect and execute tool calls (ReAct loop)
        """
        # Apply Safety/PII Redaction Layer
        safe_prompt = safety_service.check_and_redact(prompt)
        
        # Audit Log User Submission
        audit_service.log_action(
            action_type="CHAT", 
            details=f"Prompt Length: {len(safe_prompt)} chars", 
            project_id=project_id
        )

        engine_type, agent_name = self.select_route(safe_prompt)
        model_name = self.engines.get(engine_type, settings.DEFAULT_MODEL)

        # Emit meta chunk so the UI can display which agent is active
        yield {"type": "meta", "engine": f"{agent_name.upper()} AGENT", "model": model_name}

        service = self._get_service(model_name)

        try:
            # For simple queries, just stream directly — no ReAct overhead
            if agent_name == "default":
                async for chunk in service.stream_invoke(safe_prompt, history):
                    yield chunk
                return

            # For specialized agents, run the ReAct loop with structured persona
            current_context = safe_prompt

            # Build agent persona prompt with tool descriptions
            persona = agent_factory.get_persona(agent_name)
            tools_desc = "\n".join(
                f"- {t['name']}: {t['description']}" for t in tool_registry.get_all_tools()
            )
            system_context = persona.get_system_prompt(tools_desc)

            for iteration in range(3):
                full_response = ""

                agent_prompt = (
                    f"{system_context}\n\n"
                    f"USER REQUEST:\n{current_context}\n\n"
                    "If you need to use a tool, output EXACTLY ONE tool call in the format:\n"
                    "ACTION: tool_name(key='value', key2='value2')\n"
                    "Otherwise, answer the user directly."
                )

                async for chunk in service.stream_invoke(
                    agent_prompt, history if iteration == 0 else []
                ):
                    if chunk["type"] == "content":
                        full_response += chunk["content"]
                        yield chunk
                    elif chunk["type"] == "error":
                        yield chunk
                        return

                # Check for tool action
                action_match = re.search(r"ACTION:\s+(\w+)\((.+?)\)", full_response, re.DOTALL)
                if action_match:
                    tool_name = action_match.group(1)
                    args_str = action_match.group(2)

                    audit_service.log_action("TOOL_EXECUTION", f"Execute: {tool_name}({args_str})", project_id)

                    yield {"type": "thought", "content": f"Executing {tool_name}..."}

                    try:
                        kwargs = {}
                        # Extract all keyword arguments in the format key='value' or key="value"
                        arg_matches = re.finditer(r"(\w+)\s*=\s*['\"](.*?)['\"]", args_str)
                        for match in arg_matches:
                            kwargs[match.group(1)] = match.group(2)

                        observation = await tool_registry.execute(tool_name, **kwargs)
                        
                        # Expose the generated artifact directly to the user UI
                        obs_str_val = str(observation)
                        if "Successfully generated" in obs_str_val:
                            filename = obs_str_val.split(":")[-1].strip()
                            yield {"type": "artifact", "url": f"/api/v1/documents/download/{filename}"}

                        obs_str = f"\nOBSERVATION: {json.dumps(observation)}"
                        current_context += f"\n{full_response}\n{obs_str}"
                        yield {"type": "thought", "content": f"Execution complete: {tool_name}"}
                        continue
                    except Exception as te:
                        logger.error(f"Tool execution failed: {te}")
                        yield {"type": "thought", "content": f"⚠️ Tool {tool_name} failed. Using internal knowledge."}
                        break

                # No tool call — we're done
                break

        except Exception as e:
            logger.error(f"Router streaming error for {model_name}: {e}")
            yield {"type": "error", "content": f"Engine failure: {str(e)}"}

    def select_route(self, prompt: str) -> Tuple[str, str]:
        """
        Determines both the model engine and the agent persona.
        Returns: (engine_type, agent_type)
        """
        prompt_lower = prompt.lower()
        words = prompt_lower.split()

        # Simple greetings & very short exchanges → fast engine, no ReAct overhead
        if len(words) <= 5 and any(w in prompt_lower for w in
            ["hello", "hi", "hey", "thanks", "thank you", "bye", "ok", "yes", "no", "good", "great"]):
            return "fast", "default"

        # Coding & analysis tasks → pro engine
        if any(w in prompt_lower for w in ["code", "python", "script", "dataframe", "csv", "calculate", "debug", "function"]):
            return "pro", "analyst"

        # Everything else → researcher agent with tool access
        return "pro", "researcher"


# Global singleton
llm_router = LLMRouter()
