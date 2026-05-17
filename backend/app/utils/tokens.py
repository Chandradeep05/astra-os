import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# 1 token ≈ 4 characters
CHARS_PER_TOKEN = 4

def calculate_budget(text: str) -> int:
    """Lightweight heuristic for token count estimation."""
    return len(text) // CHARS_PER_TOKEN

def enforce_budget(
    system_prompt: str,
    history: List[Dict[str, str]],
    rag_chunks: List[Dict[str, Any]],
    max_window: int = 8192
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """
    Enforces a strict token budget to prevent context overflows.
    Max budget is 85% of max_window.
    If exceeded:
    1. Drop oldest conversation turns first.
    2. Then drop lowest-ranked RAG chunks.
    Never touches the system prompt.
    """
    # Use 85% of window as hard limit
    max_tokens = int(max_window * 0.85)
    
    # Base cost: System prompt
    system_tokens = calculate_budget(system_prompt)
    
    # Cost: History (approximate string format)
    def _hist_tokens(h_list: List[Dict[str, str]]) -> int:
        return sum(calculate_budget(msg.get("content", "")) for msg in h_list)

    # Cost: RAG chunks
    def _rag_tokens(r_list: List[Dict[str, Any]]) -> int:
        return sum(calculate_budget(chunk.get("content", "")) for chunk in r_list)

    current_history = history.copy()
    current_chunks = rag_chunks.copy()

    total_tokens = system_tokens + _hist_tokens(current_history) + _rag_tokens(current_chunks)
    
    if total_tokens <= max_tokens:
        return current_history, current_chunks

    logger.warning(f"[TOKEN-BUDGET] Exceeded ({total_tokens} > {max_tokens}). Pruning...")

    # Step 1: Drop oldest history first (keep at least the most recent 2 messages if possible)
    while total_tokens > max_tokens and len(current_history) > 2:
        dropped_msg = current_history.pop(0)
        total_tokens -= calculate_budget(dropped_msg.get("content", ""))
        logger.debug("[TOKEN-BUDGET] Dropped old history message.")

    # Step 2: Drop lowest-ranked RAG chunks (from the end of the sorted list)
    while total_tokens > max_tokens and len(current_chunks) > 0:
        dropped_chunk = current_chunks.pop(-1)
        total_tokens -= calculate_budget(dropped_chunk.get("content", ""))
        logger.debug("[TOKEN-BUDGET] Dropped lowest-ranked RAG chunk.")

    logger.info(f"[TOKEN-BUDGET] Pruned to {total_tokens} tokens. "
                f"History size: {len(history)}->{len(current_history)}, "
                f"RAG chunks: {len(rag_chunks)}->{len(current_chunks)}.")

    return current_history, current_chunks
