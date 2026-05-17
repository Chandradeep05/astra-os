import httpx  # type: ignore
import json
import logging
from app.core.config import settings  # type: ignore
from typing import List, Dict, Optional, AsyncGenerator

logger = logging.getLogger(__name__)

# Connection pool — reused across all requests for maximum speed
_http_client: Optional[httpx.AsyncClient] = None

def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(connect=30.0, read=None, write=30.0, pool=None),
        )
    return _http_client


class OllamaService:
    """Direct Ollama HTTP streaming — no LangChain overhead."""

    def __init__(self, model_name: str = settings.DEFAULT_MODEL):
        self.model_name = model_name
        self.api_base = settings.OLLAMA_BASE_URL

    async def stream_invoke(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        Streams tokens directly from the Ollama /api/chat endpoint.
        Uses the raw HTTP API — 5-10x faster than LangChain wrappers.

        If the caller provides a system message as the first element of
        ``history``, it is used as-is (no hardcoded prompt prepended).
        This allows _direct_llm_stream to pass its own minimal prompt.
        """
        # Check if caller already supplied a system message
        has_system = (
            history
            and len(history) > 0
            and history[0].get("role") == "system"
        )

        if has_system:
            # Use caller's system message — don't override it
            messages = list(history)
        else:
            # Default ASTRA OS system prompt (used by legacy /chat endpoint)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are ASTRA OS, a personalized elite AI assistant. "
                        "The current year is 2026. NEVER provide outdated information. "
                        "You have advanced Multi-Modal capabilities: You can see images (via vision_ocr) and hear audio (via audio_transcription). "
                        "If a user provides a file path or mentions an upload, use the appropriate tool to analyze it. "
                        "If asked for current data (like exchanges, news, or weather), ALWAYS use the web_search tool. "
                        "Be frankly honest, highly competent, professional, but slightly casual like a dependable colleague. "
                        "Format outputs with clear structure (Markdown). "
                        "Keep responses concise and helpful."
                    ),
                }
            ]
            # Add conversation history (last 12 messages to preserve user intent)
            if history:
                start_idx = max(0, len(history) - 12)
                messages.extend(history[start_idx:])

        # Current prompt
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": "5m",  # Unload after 5 min idle — saves VRAM when using multiple models
            "options": {
                "temperature": 0.7,
                "repeat_penalty": 1.1,
                "num_ctx": 4096,      # 4K context — good balance of speed vs capability
                "num_predict": 1024,  # Allow full paragraph responses
            },
        }

        client = _get_client()

        try:
            async with client.stream(
                "POST", "/api/chat", json=payload
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    error_msg = body.decode(errors="replace")
                    logger.error(f"Ollama HTTP {response.status_code}: {error_msg}")
                    yield {
                        "type": "error",
                        "content": f"Ollama returned HTTP {response.status_code}. Is the model '{self.model_name}' pulled?",
                    }
                    return

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield {"type": "content", "content": token}
                    except json.JSONDecodeError:
                        continue

        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama — is it running?")
            yield {
                "type": "error",
                "content": "⚠️ Cannot connect to Ollama. Run `ollama serve` in a terminal first.",
            }
        except httpx.ReadTimeout:
            logger.error("Ollama read timeout — model may be loading")
            yield {
                "type": "error",
                "content": "⚠️ Ollama timed out. The model may still be loading — try again in a moment.",
            }
        except Exception as e:
            logger.error(f"OllamaService streaming error: {e}")
            yield {"type": "error", "content": f"Streaming failure: {str(e)}"}

    async def invoke_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        format: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Non-streaming Ollama call WITH native tool support.
        
        Uses Ollama's /api/chat endpoint with the 'tools' parameter.
        The model returns structured tool_calls in the response instead
        of us having to parse "ACTION: tool_name(...)" from freeform text.
        
        This is the core method used by the agent loop for THINK+ACT phases.
        
        Args:
            messages: Chat messages in OpenAI format
            tools: Tool definitions in Ollama function-calling format (optional)
            format: Set to "json" to restrict model output to valid JSON (highly recommended for agents)
            
        Returns:
            The full response dict from Ollama, or None on failure.
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,  # Non-streaming for tool calling
            "keep_alive": "30m",  # Keep model loaded 30 min — avoids cold restarts on slow hardware
            "options": {
                "temperature": 0.3,       # Lower temp for more reliable tool calling
                "repeat_penalty": 1.1,
                "num_ctx": 4096,           # 4K context — balanced for low RAM
                "num_predict": 1024,
            },
        }

        if format:
            payload["format"] = format
        
        # Only include tools if provided (Ollama ignores empty tools array
        # but some model adapters choke on it)
        if tools:
            payload["tools"] = tools
        
        client = _get_client()
        
        try:
            response = await client.post(
                "/api/chat",
                json=payload,
                timeout=httpx.Timeout(connect=30.0, read=900.0, write=30.0, pool=None),
            )
            
            if response.status_code != 200:
                error_msg = response.text[:500]
                logger.error(f"Ollama tool call HTTP {response.status_code}: {error_msg}")
                return None
            
            result = response.json()

            # Ollama's built-in loop detection: model generates repetitive tokens
            # and Ollama flags it as an error inside a 200 response.
            # Example: {"error": "model output error: Your output is flagged for looping content..."}
            if result.get("error"):
                logger.warning(f"[OLLAMA] Model error in response: {result['error'][:200]}")
                return None

            return result
            
        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama for tool call — is it running?")
            return None
        except httpx.ReadTimeout:
            logger.error("Ollama tool call timed out — model may be loading")
            return None
        except Exception as e:
            logger.error(f"Ollama invoke_with_tools error: {e}")
            return None

    async def health_check(self) -> bool:
        """Quick check: is Ollama alive and does the model exist?"""
        try:
            client = _get_client()
            resp = await client.get("/api/tags")
            if resp.status_code == 200:
                tags = resp.json()
                models = [m["name"] for m in tags.get("models", [])]
                # Check if our model (or a prefix thereof) is available
                return any(self.model_name in m for m in models)
            return False
        except Exception:
            return False


# Pre-built singleton for the default model
ollama_service = OllamaService()
