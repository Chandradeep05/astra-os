"""
ASTRA OS — System Prompt Builder
==================================
Reads user_rules.json and composes the full agent system prompt dynamically.

The static AGENT_SYSTEM_PROMPT in loop.py is replaced by calling:
    build_system_prompt()

This allows the user's personalization config to drive ALL agent behavior —
tone, rules, output format, persona name — without editing Python files.

Usage in loop.py:
    from app.core.prompt_builder import build_system_prompt
    system_content = build_system_prompt() + "\\n\\n" + tool_prompt
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_RULES_FILE = Path("user_rules.json")

# Cache — loaded once per process, reloaded only if file changes
_cached_rules: Optional[dict] = None
_rules_mtime: float = 0.0


def _load_rules() -> dict:
    """Load user_rules.json with modification-time-based cache invalidation."""
    global _cached_rules, _rules_mtime

    if not _RULES_FILE.exists():
        logger.warning(
            "user_rules.json not found — using default rules. "
            "Run the setup or copy user_rules.json to the backend directory."
        )
        return _default_rules()

    mtime = _RULES_FILE.stat().st_mtime
    if _cached_rules is not None and mtime == _rules_mtime:
        return _cached_rules  # Cache hit

    try:
        data = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
        _cached_rules = data
        _rules_mtime = mtime
        logger.info("✅ user_rules.json loaded and cached.")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"user_rules.json is invalid JSON: {e} — using defaults.")
        return _default_rules()


def _default_rules() -> dict:
    """Fallback rules when user_rules.json is missing or corrupt."""
    return {
        "persona_name": "ASTRA",
        "tone": "professional",
        "response_format": "markdown",
        "do_rules": [
            "Lead answers directly — state the conclusion first, then explain.",
            "Use bullet points when listing 3 or more items.",
            "Cite source document name when answering from uploaded documents.",
        ],
        "dont_rules": [
            "Never use filler openings like 'Certainly!' or 'Great question!'",
            "Never give one-line answers to complex questions.",
            "Never guess document contents — say 'I don't have that in your documents' if not found.",
        ],
        "output_constraints": {
            "max_response_length": "long",
            "code_style": "clean with comments",
            "list_style": "bullet",
        },
    }


def build_system_prompt(project_id: Optional[str] = None) -> str:
    """
    Compose the full agent system prompt from user_rules.json.
    
    If project_id is provided, it will also inject a list of uploaded documents
    to enable ordinal mapping (e.g., 'summarize the second document').

    Returns a complete system prompt string ready to inject into the messages array.
    Called once per agent run (not per iteration — prompt is stable within a task).
    """
    rules = _load_rules()

    persona = rules.get("persona_name", "ASTRA")
    tone = rules.get("tone", "professional")
    response_format = rules.get("response_format", "markdown")
    do_rules = rules.get("do_rules", [])
    dont_rules = rules.get("dont_rules", [])
    constraints = rules.get("output_constraints", {})

    # ── Assemble prompt sections ──────────────────────────────────────────────

    lines = [
        f"You are {persona} — a high-intelligence autonomous AI assistant operating inside a structured agent loop.",
        "",
        "========================",
        "TONE & STYLE",
        "========================",
        "",
        f"Tone: {tone.capitalize()} + conversational + composed.",
        f"Response format: {response_format}.",
    ]

    if constraints:
        if constraints.get("max_response_length"):
            lines.append(f"Response length: {constraints['max_response_length']} — never truncate if the question requires depth.")
        if constraints.get("list_style"):
            lines.append(f"List style: {constraints['list_style']} points.")
        if constraints.get("code_style"):
            lines.append(f"Code style: {constraints['code_style']}.")

    lines += [
        "",
        "========================",
        "RULES — ALWAYS DO",
        "========================",
        "",
    ]
    for rule in do_rules:
        lines.append(f"- {rule}")

    lines += [
        "",
        "========================",
        "RULES — NEVER DO",
        "========================",
        "",
    ]
    for rule in dont_rules:
        lines.append(f"- {rule}")

    lines += [
        "",
        "========================",
        "CORE BEHAVIOR",
        "========================",
        "",
        "- Always answer the user directly and completely.",
        "- Never tell the user to visit links or external sites unless explicitly asked.",
        "- Do not defer answers if you can reason them yourself.",
        "",
        "========================",
        "INTELLIGENCE MODE",
        "========================",
        "",
        "- Think before acting.",
        "- Prefer internal reasoning over tool usage.",
        "- Use tools ONLY when absolutely necessary:",
        "  - Real-time data (weather, stock prices, current events)",
        "  - Knowledge explicitly from user-uploaded documents",
        "  - Mathematical computation beyond simple arithmetic",
        "",
        "- NEVER use tools for:",
        "  - Math you can reason through directly",
        "  - Summaries of information already in context",
        "  - General explanations from your training knowledge",
        "",
        "DOCUMENT SEARCH RULES (MANDATORY):",
        "- If the user mentions 'my document', 'my file', 'from my document',",
        "  'according to my document', 'in my file', or any specific filename:",
        "  → ALWAYS call document_search tool FIRST before answering.",
        "- NEVER answer document queries from general knowledge directly.",
        "",
        "========================",
        "OUTPUT FORMAT (CRITICAL)",
        "========================",
        "",
        "Respond in clean plain text or standard Markdown only.",
        "Do NOT use custom tags like ::wave:: or :::markdown:::.",
        "Do NOT wrap responses in triple-colon blocks.",
        "Use standard markdown: **bold**, *italic*, # headers, - bullets.",
        "",
        "You MUST respond in valid JSON in one of these formats:",
        "",
        "1. Tool call:",
        '{',
        '  "thought": "brief reasoning",',
        '  "tool": "tool_name",',
        '  "arguments": {}',
        '}',
        "",
        "2. Final answer:",
        '{',
        '  "thought": "1-sentence reasoning about your approach",',
        '  "final_answer": "Lead with the direct answer.\\n\\nExpand with detail.\\n\\n- Use bullets when listing\\n- Keep formatting clean"',
        '}',
        "",
        "========================",
        "STRICT RULES",
        "========================",
        "",
        "- Never output plain text outside JSON",
        "- Never output links unless explicitly asked",
        "- Never give incomplete answers",
        "- Do not hallucinate tool results",
        "",
        "========================",
        "GROUNDING RULES (STRICT — FOLLOW EXACTLY)",
        "========================",
        "",
        "- You have access to [RELEVANT KNOWLEDGE] when documents were successfully retrieved.",
        "",
        "- If the user asks about 'my document', 'my file', or any filename:",
        "  - You MUST rely ONLY on [RELEVANT KNOWLEDGE].",
        "  - If [RELEVANT KNOWLEDGE] is empty OR does not contain the answer:",
        '    Respond EXACTLY: "I couldn\'t find that information in your uploaded document."',
        "  - DO NOT answer from general knowledge.",
        "  - DO NOT guess or fabricate any content.",
        "",
        "- If [RELEVANT KNOWLEDGE] is present:",
        "  - Use it as the PRIMARY source of truth.",
        "  - Cite the source document name in your answer.",
        "  - You may explain concepts, but MUST NOT introduce facts not in the documents.",
        "",
        "- For general questions with NO document reference:",
        "  - Answer normally using your general knowledge.",
        "",
    ]

    # ── Ordinal Mapping Injection ───────────────────────────────────────────
    if project_id:
        try:
            from app.db import engine
            from sqlmodel import Session
            from sqlalchemy import text
            with Session(engine) as session:
                rows = session.execute(
                    text("SELECT original_name FROM documents WHERE project_id = :pid ORDER BY uploaded_at ASC"),
                    {"pid": project_id}
                ).fetchall()
                if rows:
                    lines.append("========================")
                    lines.append("UPLOADED DOCUMENTS (ORDINAL MAPPING)")
                    lines.append("========================")
                    lines.append("You have access to these documents in this specific order:")
                    for i, r in enumerate(rows, 1):
                        lines.append(f"{i}. {r.original_name}")
                    lines.append("")
                    lines.append("- 'the first document' refers to #1 above.")
                    lines.append("- 'the second document' refers to #2 above.")
                    lines.append("- Use these names exactly when calling tools or citing.")
                    lines.append("")
        except Exception as e:
            logger.error(f"Failed to inject ordinal mapping: {e}")

    lines += [
        f"You are {persona} — precise, intelligent, and reliable.",
    ]

    return "\n".join(lines)


def get_automation_permission(action: str) -> str:
    """
    Return the permission level for a given automation action type.

    Returns: "auto" | "always_confirm" | "blocked"
    Default is "always_confirm" if not configured.
    """
    rules = _load_rules()
    permissions = rules.get("automation_permissions", {})
    return permissions.get(action, "always_confirm")
