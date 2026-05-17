"""
ASTRA OS — Human-in-the-Loop Approval Gate
============================================
Modular approval system that pauses agent execution for risky actions.

Phase 1: CLI-based (stdin/stdout prompt, blocks until user responds)
Future:  WebSocket-based (sends approval request to frontend, async wait)

The approval logic is abstracted behind the ApprovalGate interface so
swapping implementations requires zero changes to the agent loop.
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from app.agent.schemas import RiskLevel

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Abstract Approval Interface
# ──────────────────────────────────────────────

class ApprovalGate(ABC):
    """
    Base class for approval mechanisms.
    Implement `request_approval()` for different UIs (CLI, WebSocket, etc.)
    """

    @abstractmethod
    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        description: str,
        task_id: str = "default",
    ) -> bool:
        """
        Request human approval for a risky action.
        Returns True if approved, False if rejected.
        """
        ...

    def should_require_approval(self, risk_level: RiskLevel) -> bool:
        """Check if this risk level requires human approval."""
        return risk_level == RiskLevel.RISKY


# ──────────────────────────────────────────────
#  CLI Approval Gate (Phase 1)
# ──────────────────────────────────────────────

class CLIApprovalGate(ApprovalGate):
    """
    Simple terminal-based approval. Prints the action details and waits
    for y/n input. Blocks the agent loop until the user responds.
    """

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        description: str,
        task_id: str = "default",
    ) -> bool:
        # Format the approval request for the terminal
        separator = "=" * 60
        print(f"\n{separator}")
        print(f"⚠️  APPROVAL REQUIRED — {risk_level.value.upper()} ACTION")
        print(separator)
        print(f"Tool:        {tool_name}")
        print(f"Description: {description}")
        print(f"Arguments:")
        for key, value in arguments.items():
            # Truncate long values for readability
            val_str = str(value)
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            print(f"  {key}: {val_str}")
        print(separator)

        # Use asyncio-compatible input (run blocking input in executor)
        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: input("Approve? (y/n): ").strip().lower()),
                timeout=120.0,  # 2 minute timeout
            )
        except asyncio.TimeoutError:
            print("⏰ Approval timed out (2 min). Action DENIED.")
            logger.warning(f"Approval timeout for {tool_name}")
            return False

        approved = response in ("y", "yes")
        status = "✅ APPROVED" if approved else "❌ DENIED"
        print(f"{status}\n")
        logger.info(f"Approval for {tool_name}: {status}")
        return approved


# ──────────────────────────────────────────────
#  Auto-Approve Gate (for testing / safe tools)
# ──────────────────────────────────────────────

class AutoApprovalGate(ApprovalGate):
    """
    Automatically approves all actions. Use ONLY for testing
    or when running tools that are already classified as safe.
    """

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        description: str,
        task_id: str = "default",
    ) -> bool:
        logger.info(f"Auto-approved: {tool_name} (risk: {risk_level.value})")
        return True


# ──────────────────────────────────────────────
#  Streaming Approval Gate (for API / WebSocket)
# ──────────────────────────────────────────────

# Global registry for active streaming gates (allows lookup by task_id)
# task_id -> StreamingApprovalGate instance
approval_registry: Dict[str, 'StreamingApprovalGate'] = {}

class StreamingApprovalGate(ApprovalGate):
    """
    Used when the agent is running via the HTTP API.
    Instead of blocking on stdin, it stores the pending approval
    and waits for an external signal (e.g., from a WebSocket or
    a follow-up API call).

    Phase 1: This auto-approves safe/moderate and rejects risky
             (the API endpoint can't do interactive CLI prompts).
    Phase 5: Upgrade to WebSocket-based approval with frontend dialog.
    """

    def __init__(self):
        # Pending approvals: task_id -> asyncio.Event
        self._pending: Dict[str, asyncio.Event] = {}
        self._decisions: Dict[str, bool] = {}

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_level: RiskLevel,
        description: str,
        task_id: str = "default",  # Added task_id for tracking
    ) -> bool:
        if risk_level != RiskLevel.RISKY:
            # Safe and moderate actions are auto-approved via API
            return True

        # Register this gate for the task_id so the API can find it
        approval_registry[task_id] = self

        # For risky actions, create an event and wait for submit_decision
        logger.info(f"🛑 PAUSING for user approval: {tool_name} (Task: {task_id})")
        
        event = asyncio.Event()
        self._pending[task_id] = event
        
        try:
            # Wait up to 5 minutes for approval
            await asyncio.wait_for(event.wait(), timeout=300.0)
            approved = self._decisions.get(task_id, False)
            status = "APPROVED" if approved else "DENIED"
            logger.info(f"👤 User decision received for {task_id}: {status}")
            return approved
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Approval timeout for {task_id}. Action DENIED.")
            return False
        finally:
            self._pending.pop(task_id, None)
            self._decisions.pop(task_id, None)
            approval_registry.pop(task_id, None)  # Cleanup registry here, not in submit_decision

    async def submit_decision(self, task_id: str, approved: bool):
        """Called externally (future WebSocket/API) to submit a decision."""
        self._decisions[task_id] = approved
        event = self._pending.get(task_id)
        if event:
            event.set()
        # Registry cleanup is handled by request_approval's finally block


# ──────────────────────────────────────────────
#  Factory
# ──────────────────────────────────────────────

def get_approval_gate(mode: str = "cli") -> ApprovalGate:
    """
    Factory function to get the right approval gate.
    Modes: 'cli', 'auto', 'streaming'
    """
    gates = {
        "cli": CLIApprovalGate,
        "auto": AutoApprovalGate,
        "streaming": StreamingApprovalGate,
    }
    gate_class = gates.get(mode, CLIApprovalGate)
    return gate_class()
