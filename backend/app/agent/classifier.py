"""
ASTRA OS — Query Classifier
============================
Classifies every incoming query BEFORE it reaches AgentLoop,
document_service, or any tool. This is the primary latency fix.

Classification priority:
  1. Rule-based (regex + keywords) — handles ~90% of cases, zero latency
  2. LLM fallback — only when rule-based is uncertain (uses smallest model)

Classes:
  DIRECT_LLM      Greetings, casual chat, simple math, general knowledge
  RAG_QUERY       User explicitly references their documents / uploaded files
  TOOL_CALL       Complex math, weather, web search, real-time data
  ACTION_REQUEST  Automation tasks (send email, fill form, apply to job)
  MEMORY_OP       Remember / forget / what do you know about me
  META            Questions about Astra-OS itself

Hard routing rules (enforced in document_service and agent.py):
  DIRECT_LLM    → NEVER touches ChromaDB
  RAG_QUERY     → ONLY class that triggers ChromaDB retrieval
  TOOL_CALL     → Skips ChromaDB; LLM generates tool input normally
  ACTION_REQUEST→ Routes to approval gate stub
  MEMORY_OP     → Routes to memory handler stub
  META          → Answers from system prompt only
"""

import re
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Query Classes
# ──────────────────────────────────────────────

class QueryClass(str, Enum):
    DIRECT_LLM     = "DIRECT_LLM"
    RAG_QUERY      = "RAG_QUERY"
    TOOL_CALL      = "TOOL_CALL"
    ACTION_REQUEST = "ACTION_REQUEST"
    MEMORY_OP      = "MEMORY_OP"
    META           = "META"


# ──────────────────────────────────────────────
#  Rule-based patterns (compiled once at import)
# ──────────────────────────────────────────────

# RAG_QUERY — user explicitly references their content
_RAG_PATTERNS = re.compile(
    r"\b("
    r"my document|my file|my pdf|my upload|my report|my note"
    r"|this document|the document|that document|system document"
    r"|this file|the file|that file"
    r"|from my document|from my file|from the document|from this document"
    r"|in my document|in my file|in the file|in this document"
    r"|according to my|according to this|according to the"
    r"|based on my document|based on this document|based on the document"
    r"|what does my|what did my|summarize my|summarize the document|summarize document"
    r"|uploaded|from the upload|document i uploaded|the document i uploaded"
    r"|summarize it|explain it|explain that|what does it say|what does it mention"
    r"|the (first|second|third|last|next|previous) (document|file|pdf|upload)"
    r"|summarize this document|summarize this file|summarize this pdf"
    r"|\b(summarize|explain|describe|tell me about|what does|search)\s+[\w\-]{4,}\b"  # extensionless file ref
    r")\b"
    r"|[\w\-]+\.(?:docx|pdf|txt|xlsx|pptx|csv|md|json)",  # explicit filename reference
    re.IGNORECASE,
)

# TOOL_CALL — real-time data, complex computation
_TOOL_PATTERNS = re.compile(
    r"\b("
    r"weather|forecast|temperature|humidity|rain|snow|wind speed"
    r"|search the web|search online|look up|google|bing"
    r"|news|latest|right now|live"
    r"|current (price|rate|score|value|status|weather|temperature)"
    r"|today'?s (weather|price|rate|score|news|forecast)"
    r"|stock price|bitcoin|crypto|exchange rate"
    r"|calculate:|compute:|eval:|solve:"
    r"|delete\s+(all\s+)?(the\s+|my\s+)?(documents?|files?|uploads?)|purge workspace|clear all (the\s+|my\s+)?(files?|documents?)|remove all (the\s+|my\s+)?(uploads?|documents?|files?)"
    r")\b"
    r"|^\s*calculate\b"          # starts with 'calculate'
    r"|[+\-*/^%]\s*\d",          # arithmetic operator followed by digit (complex expr)
    re.IGNORECASE,
)

# Exclude simple arithmetic that DIRECT_LLM can handle: "2+2", "5*6", "10/2"
_SIMPLE_MATH_PATTERN = re.compile(
    r"^\s*[\d\s\(\)\.\+\-\*\/\%\^]+\s*[=?]?\s*$"
)


def _is_complex_math(expr: str) -> bool:
    """Check if a math expression is too complex for LLM to answer correctly.
    Only expressions with MIXED operator types need python_executor.
    Same-operator chains (2*3*4*3) are trivially simple — no order-of-operations."""
    clean = re.sub(r'^(calculate|compute|what\s+is|what\'?s)\s*', '', expr, flags=re.IGNORECASE).strip()
    clean = clean.rstrip('?').strip()
    ops = re.findall(r'[+\-*/^%]', clean)
    if not ops:
        return False
    distinct_ops = set(ops)
    # Same-operator chains are simple regardless of count
    if len(distinct_ops) <= 1:
        return False
    # Mixed operations with >2 total operators — order of operations matters
    if len(ops) > 2 and len(distinct_ops) > 1:
        return True
    # Mixed mul/div with add/sub — always complex
    has_mul_div = bool(distinct_ops & {'*', '/', '^'})
    has_add_sub = bool(distinct_ops & {'+', '-'})
    if has_mul_div and has_add_sub and len(ops) > 1:
        return True
    return False

# ACTION_REQUEST — automation tasks
_ACTION_PATTERNS = re.compile(
    r"\b("
    r"send email|send an email|email to|compose email"
    r"|apply to job|apply for job|fill form|fill out form"
    r"|submit form|book appointment|schedule meeting"
    r"|post to|upload to|download from|automate"
    r")\b",
    re.IGNORECASE,
)

# MEMORY_OP — memory management
_MEMORY_PATTERNS = re.compile(
    r"\b("
    r"remember that|don'?t forget|store this|keep in mind"
    r"|forget (that|about|this|my )|delete memory|clear memory"
    r"|delete\s+.+\s+from\s+(your\s+)?memory|remove\s+.+\s+from\s+(your\s+)?memory"
    r"|erase\s+.+\s+from\s+(your\s+)?memory|wipe\s+(your\s+)?memory"
    r"|what do you know about me|what have you remembered"
    r"|recall|my preferences|my name is"
    r"|my favorite|i prefer|i hate|i love|i like|i use|i switched"
    r"|summarize what you know|what you know about me"
    r"|i'm building|i'm using|i'm working (on|with)"
    r"|am i using|am i building|am i working|am i running"
    r"|do i (use|prefer|like|build|work)"
    r"|what do you remember|what do you recall|tell me about myself"
    r"|who am i|what is my |what's my |what are my "
    r"|do you (remember|know) my"
    r"|i am |i'm |i study|i play|i enjoy|i live|i work"
    r"|i'm pursuing|i have a|remember my|remember this|please remember|my .+ is"
    r")\b",
    re.IGNORECASE,
)

# Fix #8: Anti-pattern — queries that match MEMORY_OP keywords but are really technical questions
# "Am I using recursion correctly?" is asking for advice, not recalling a stored fact
_MEMORY_ANTI_PATTERN = re.compile(
    r'\b(correctly|properly|right|wrong|well|badly|efficiently|effectively|too much|too many|the right|the correct)\b',
    re.IGNORECASE,
)

# META — questions about Astra-OS
_META_PATTERNS = re.compile(
    r"\b("
    r"astra.?os|about you|who are you|what are you"
    r"|your capabilities|what can you do|your features"
    r"|how do you work|your settings|your version"
    r"|astra version|system info about astra"
    r")\b",
    re.IGNORECASE,
)

# RAG_QUERY — "what do the notes mention about X" (notes = documents)
_NOTES_PATTERN = re.compile(
    r"\b(notes?|the notes?|my notes?)\b.*(mention|say|contain|about)",
    re.IGNORECASE,
)

# META blocklist — queries that CONTAIN meta keywords but are NOT meta queries
# e.g. "I'm building Astra-OS using FastAPI" is a statement, not a question about Astra-OS
_META_STATEMENT_PATTERN = re.compile(
    r"^(i'?m |i am |i |we |my |our )",
    re.IGNORECASE,
)

# Document listing — user wants a list of their files, not content retrieval
_DOC_LIST_PATTERN = re.compile(
    r"\b(list|name|show|what are) (all )?(my |the )?(documents?|files?|uploads?)\b"
    r"|\bhow many (documents?|files?) (do i|have i|did i)"
    r"|\bwhat (documents?|files?) (do i|have i|did i)",
    re.IGNORECASE,
)

# DIRECT_LLM — greetings and trivial queries
_GREETING_PATTERNS = re.compile(
    r"^("
    r"hi|hello|hey|howdy|yo|sup|greetings|good morning|good afternoon|good evening"
    r"|how are you|how'?s it going|what'?s up|how do you do"
    r"|thanks|thank you|thx|ty|bye|goodbye|see you|later|ok|okay|sure|cool"
    r")\b[\s!?.]*$",
    re.IGNORECASE,
)

# DIRECT_LLM — general knowledge questions (no real-time data, no doc reference)
# Prevents 30-char+ knowledge queries from falling to the 4s LLM fallback
_KNOWLEDGE_PATTERNS = re.compile(
    r"^("
    r"what is|what are|what was|what were|what'?s"
    r"|who is|who are|who was|who were|who'?s"
    r"|where is|where are|where was|where were"
    r"|when is|when are|when was|when did|when were"
    r"|why is|why are|why was|why did|why does|why do"
    r"|how is|how are|how was|how does|how do|how did|how can"
    r"|explain|describe|tell me about|give me|define|what does|help me understand"
    r"|can you explain|could you explain|i need to understand"
    r"|write|code|implement|create a|build a|make a|generate"
    r"|summarize our|recap our|what have we"
    r")",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────
#  Rule-based classifier
# ──────────────────────────────────────────────

def _classify_rule_based(query: str) -> Optional[QueryClass]:
    """
    Fast rule-based classification. Returns None if uncertain.
    Runs in microseconds — no I/O, no model calls.
    """
    q = query.strip()

    # 1. Empty / whitespace
    if not q:
        return QueryClass.DIRECT_LLM

    # 2. MEMORY_OP — memory management (BEFORE META so "I'm building Astra-OS" stores a fact)
    if _MEMORY_PATTERNS.search(q):
        # Fix #8: Guard against technical questions like "Am I using recursion correctly?"
        if not _MEMORY_ANTI_PATTERN.search(q):
            return QueryClass.MEMORY_OP

    # 3. META — about Astra-OS itself
    #    Guard: skip META on long mixed queries (>40 chars) and statements ("I'm ...")
    if _META_PATTERNS.search(q):
        is_short_enough = len(q) < 40
        is_not_statement = not _META_STATEMENT_PATTERN.match(q)
        if is_short_enough and is_not_statement:
            return QueryClass.META

    # 4. ACTION_REQUEST — automation / form / email
    if _ACTION_PATTERNS.search(q):
        return QueryClass.ACTION_REQUEST

    # 4a. Document listing — "name all the documents I uploaded" → META (not RAG)
    if _DOC_LIST_PATTERN.search(q):
        return QueryClass.META

    # 5. RAG_QUERY — explicit document reference (highest priority over tool/direct)
    if _RAG_PATTERNS.search(q):
        return QueryClass.RAG_QUERY

    # 5a. RAG_QUERY — "notes" treated as documents
    if _NOTES_PATTERN.search(q):
        return QueryClass.RAG_QUERY

    # 6. TOOL_CALL — real-time data or computation
    #    Simple arithmetic ("2+2", "5*6") stays DIRECT_LLM
    #    Complex expressions (>2 operators, mixed ops) go to TOOL_CALL for python_executor
    if _TOOL_PATTERNS.search(q):
        if _SIMPLE_MATH_PATTERN.match(q):
            if _is_complex_math(q):
                return QueryClass.TOOL_CALL
            return QueryClass.DIRECT_LLM
        # "what is 2*2" / "what's 10/5" — math question, not a tool call
        if re.match(
            r"^(what\s+is|what'?s)\s+[\d\s\(\)\.\+\-\*\/\%\^\?]+$",
            q, re.IGNORECASE
        ):
            if _is_complex_math(q):
                return QueryClass.TOOL_CALL
            return QueryClass.DIRECT_LLM
        return QueryClass.TOOL_CALL

    # 7. Simple math expression (no letters except possibly 'x')
    if _SIMPLE_MATH_PATTERN.match(q):
        if _is_complex_math(q):
            return QueryClass.TOOL_CALL
        return QueryClass.DIRECT_LLM

    # 8. Greeting / trivial
    if _GREETING_PATTERNS.match(q):
        return QueryClass.DIRECT_LLM

    # 9. General knowledge question — classify as DIRECT_LLM before length fallback
    #    Catches "Explain how transformers work", "What is the capital of France?", etc.
    if _KNOWLEDGE_PATTERNS.match(q):
        return QueryClass.DIRECT_LLM

    # Short queries with no special signals → probably DIRECT_LLM
    if len(q) < 30:
        return QueryClass.DIRECT_LLM

    # Uncertain — caller should use LLM fallback
    return None


# ──────────────────────────────────────────────
#  LLM fallback classifier
# ──────────────────────────────────────────────

async def _classify_llm_fallback(query: str) -> QueryClass:
    """
    LLM-based classification for ambiguous queries.
    Uses the smallest/fastest available Ollama model.
    Total latency budget: <500ms including network.
    """
    try:
        import asyncio
        from app.services.ollama import OllamaService
        from app.core.config import settings

        # Use the fastest available model for classification
        fast_model = getattr(settings, "CLASSIFIER_MODEL", None) or settings.DEFAULT_MODEL

        ollama = OllamaService(model_name=fast_model)

        prompt = f"""Classify this user query into exactly one category. Reply with ONLY the category name, nothing else.

Categories:
- DIRECT_LLM: greetings, casual chat, simple math, general knowledge questions
- RAG_QUERY: user explicitly references their documents, files, or uploaded content
- TOOL_CALL: weather, web search, complex math, real-time data requests
- ACTION_REQUEST: send email, apply to job, fill forms, automation tasks
- MEMORY_OP: "remember that", "forget", "what do you know about me"
- META: questions about Astra-OS itself, capabilities, settings

Query: {query[:300]}

Category:"""

        response = await asyncio.wait_for(
            ollama.invoke_with_tools(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                format=None,  # plain text response
            ),
            timeout=4.0,  # strict 4s budget, leaving 1s headroom in the 5s SSE cycle
        )

        if response:
            content = response.get("message", {}).get("content", "").strip().upper()
            # Extract just the class name even if model adds extra text
            for cls in QueryClass:
                if cls.value in content:
                    logger.info(f"[CLASSIFIER] LLM fallback → {cls.value} for: {query[:60]}")
                    return cls

    except Exception as e:
        logger.warning(
            f"[CLASSIFIER] LLM fallback failed ({type(e).__name__}: {e!r}), defaulting to DIRECT_LLM"
        )

    return QueryClass.DIRECT_LLM


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────

async def classify_query(query: str) -> QueryClass:
    """
    Classify a user query. Rule-based first, LLM fallback only if uncertain.

    Args:
        query: Raw user query string

    Returns:
        QueryClass — one of DIRECT_LLM, RAG_QUERY, TOOL_CALL,
                     ACTION_REQUEST, MEMORY_OP, META

    Latency contract:
        Rule-based path: <1ms
        LLM fallback path: <500ms total
    """
    result = _classify_rule_based(query)
    if result is not None:
        logger.info(f"[CLASSIFIER] Rule-based → {result.value} | query: {query[:60]}")
        return result

    # Rule-based was uncertain — use LLM fallback
    logger.info(f"[CLASSIFIER] Uncertain, using LLM fallback | query: {query[:60]}")
    return await _classify_llm_fallback(query)
