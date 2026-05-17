"""
ASTRA OS — DuckDuckGo Web Search Tool
=======================================
Free web search with zero API keys. Uses the `ddgs` package.

No rate limits, no billing, fully local-first compatible.
The interface is generic so swapping to Serper/Google/Bing later
requires only registering a new tool instance.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DuckDuckGoSearchTool:
    """Free web search via DuckDuckGo. No API key required."""

    def __init__(self):
        self.name = "web_search"
        self.description = (
            "Search the web for current information, news, facts, and real-time data. "
            "Use this when you need up-to-date information that you don't have in your training data. "
            "Returns the top 5 results with titles, snippets, and links."
        )

    async def execute(self, query: str, max_results: int = 5) -> str:
        """
        Search DuckDuckGo and return formatted results.
        Runs in an executor to avoid blocking the async event loop.
        Hard timeout: 5 seconds. One attempt, no retries.
        """
        if not query or not query.strip():
            return "Error: Empty search query."

        try:
            import asyncio
            loop = asyncio.get_running_loop()
            # FIX-5: Single-provider, single-attempt, 10-second hard timeout.
            # asyncio.wait_for cancels the Future if the executor call exceeds 10s.
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._sync_search, query, max_results),
                timeout=10.0,
            )
            return result

        except asyncio.TimeoutError:
            logger.warning(f"[WEB_SEARCH] Timeout after 10s for query: {query[:80]}")
            return "Unable to fetch real-time data right now."
        except ImportError:
            return (
                "Error: ddgs not installed. "
                "Run: pip install ddgs"
            )
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return "Unable to fetch real-time data right now."


    def _sync_search(self, query: str, max_results: int) -> str:
        """Synchronous DuckDuckGo search (runs in thread pool)."""
        try:
            from ddgs import DDGS

            results = DDGS().text(query, max_results=max_results)

            if not results:
                return f"No results found for '{query}'."

            output = f"WEB SEARCH RESULTS for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                title = r.get("title", "No Title")
                body = r.get("body", "No description available.")
                href = r.get("href", "#")
                output += f"{i}. {title}\n   {body}\n   Link: {href}\n\n"

            return output

        except Exception as e:
            raise RuntimeError(f"DuckDuckGo search failed: {str(e)}")
