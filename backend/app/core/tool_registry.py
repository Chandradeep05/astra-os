"""
ASTRA OS — Tool Registry v3.0
================================
Central registry for all agent tools. Upgraded with:
  - Risk levels (safe, moderate, risky) for approval gating
  - Ollama-native tool format export for structured function calling
  - Backward-compatible with existing tool registrations
"""

from typing import Dict, Any, List, Callable, Optional
from pydantic import BaseModel
from app.agent.schemas import RiskLevel
import inspect
import logging

logger = logging.getLogger(__name__)


class Tool(BaseModel):
    """A registered tool that the agent can use."""
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable
    risk_level: RiskLevel = RiskLevel.SAFE  # Default to safe for backward compat


class ToolRegistry:
    """
    Central registry for all tools. Tools register themselves here
    and the agent loop queries the registry for available tools.
    """

    def __init__(self):
        self.tools: Dict[str, Tool] = {}

    def register_tool(self, tool: Tool):
        """Register a new tool. Overwrites existing tools with the same name."""
        self.tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} (risk: {tool.risk_level.value})")

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all tools as dicts (for display/listing)."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "risk_level": t.risk_level.value,
            }
            for t in self.tools.values()
        ]

    def get_tools_for_ollama(self) -> List[Dict[str, Any]]:
        """
        Export tools in Ollama's native function calling format.
        This allows Ollama to return structured tool calls instead of
        us having to parse regex from freeform text.

        Format spec: https://ollama.com/blog/tool-support

        Returns a list of tool definitions like:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "What it does",
                "parameters": { ... JSON Schema ... }
            }
        }
        """
        ollama_tools = []
        for tool in self.tools.values():
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return ollama_tools

    async def execute(self, name: str, **kwargs) -> Any:
        """
        Execute a tool by name with the given arguments.
        Handles both sync and async tool functions transparently.
        Async tools are wrapped in asyncio.wait_for(timeout=5s) as a
        defense-in-depth guard. Sync tools (e.g. python_executor) are
        unaffected — they have their own internal timeout mechanisms.
        """
        import asyncio

        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry")

        try:
            if inspect.iscoroutinefunction(tool.func):
                # 30s timeout — embedding + ChromaDB + cross-encoder can take 10-20s on CPU
                return await asyncio.wait_for(tool.func(**kwargs), timeout=30.0)
            return tool.func(**kwargs)
        except asyncio.TimeoutError:
            logger.warning(f"[TOOL_TIMEOUT] Tool '{name}' timed out after 30s")
            return "Unable to fetch real-time data right now."
        except TypeError as e:
            # Common error: wrong arguments passed by the LLM
            logger.error(f"Tool '{name}' argument error: {e}")
            return f"Error: Invalid arguments for tool '{name}': {str(e)}"


# Global registry instance
tool_registry = ToolRegistry()
