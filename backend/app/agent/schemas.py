"""
ASTRA OS — Agent Schemas
========================
Pydantic models that define the data structures flowing through the cognitive loop.
Strict typing prevents the runtime surprises that plague AI agent systems.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from enum import Enum
from datetime import datetime


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class AgentPhase(str, Enum):
    """Which step of the OTPAR loop the agent is currently in."""
    OBSERVE = "observe"
    THINK = "think"
    PLAN = "plan"
    ACT = "act"
    REFLECT = "reflect"
    COMPLETE = "complete"
    ERROR = "error"
    AWAITING_APPROVAL = "awaiting_approval"


class RiskLevel(str, Enum):
    """How dangerous a tool action is. Determines approval requirements."""
    SAFE = "safe"            # Auto-execute (search, read, memory recall)
    MODERATE = "moderate"    # Execute with detailed logging (code execution)
    RISKY = "risky"          # Requires explicit human approval (file writes, emails)


# ──────────────────────────────────────────────
#  Tool-Related Models
# ──────────────────────────────────────────────

class ToolCall(BaseModel):
    """A single tool invocation decided by the agent."""
    name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass")


class ToolResult(BaseModel):
    """The result of executing a tool."""
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    approved: bool = True  # False if the user rejected the action


# ──────────────────────────────────────────────
#  Agent Step (one iteration of the loop)
# ──────────────────────────────────────────────

class AgentStep(BaseModel):
    """One complete iteration of the cognitive loop."""
    iteration: int = 0
    phase: AgentPhase = AgentPhase.OBSERVE
    observation: str = ""         # What the agent sees (context, memories, prior results)
    thought: str = ""             # The agent's reasoning about what to do
    plan: List[str] = Field(default_factory=list)  # Ordered steps the agent plans to take
    tool_call: Optional[ToolCall] = None           # The tool action for this step
    tool_result: Optional[ToolResult] = None       # Result of the tool action
    reflection: str = ""          # Agent's evaluation of the result
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ──────────────────────────────────────────────
#  Agent State (full context for a task)
# ──────────────────────────────────────────────

class AgentState(BaseModel):
    """
    Complete state of the agent for a single task execution.
    This is the "brain" that persists across loop iterations.
    """
    task_id: str = ""
    original_task: str = ""                  # The user's original request
    current_phase: AgentPhase = AgentPhase.OBSERVE
    steps: List[AgentStep] = Field(default_factory=list)
    max_iterations: int = 5                  # Safety cap to prevent infinite loops
    current_iteration: int = 0
    is_complete: bool = False
    final_answer: str = ""
    error: Optional[str] = None

    # Working memory: accumulated context during this task
    working_memory: List[str] = Field(default_factory=list)

    def add_observation(self, obs: str):
        """Append to working memory for context accumulation."""
        self.working_memory.append(obs)

    def get_working_context(self) -> str:
        """Compile all working memory into a single context string."""
        if not self.working_memory:
            return ""
        return "\n".join(f"[Step {i+1}] {m}" for i, m in enumerate(self.working_memory))


# ──────────────────────────────────────────────
#  API Request/Response Models
# ──────────────────────────────────────────────

class AgentRequest(BaseModel):
    """Incoming request to the /agent endpoint."""
    task: str = Field(..., description="The task for the agent to perform")
    project_id: str = "default"
    max_iterations: int = Field(default=5, ge=1, le=10)
    model: Optional[str] = None  # Override default model for this task


class ApprovalRequest(BaseModel):
    """Sent to the user when a risky action needs approval."""
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    risk_level: str
    description: str  # Human-readable explanation of what will happen


class ApprovalResponse(BaseModel):
    """The user's response to an approval request."""
    task_id: str
    approved: bool
    reason: Optional[str] = None  # Optional explanation for rejection


class AgentStreamEvent(BaseModel):
    """SSE event sent to the frontend during agent execution."""
    type: Literal[
        "phase_change",      # Agent moved to a new OTPAR phase
        "thought",           # Agent's reasoning text
        "plan",              # Agent's planned steps
        "tool_call",         # Agent is calling a tool
        "tool_result",       # Tool execution result
        "approval_required", # Waiting for human approval
        "reflection",        # Agent's self-evaluation
        "answer",            # Final answer
        "error",             # Something went wrong
        "done",              # Task complete
    ]
    phase: Optional[str] = None
    content: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
