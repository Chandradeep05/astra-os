"""
ASTRA OS — CLI Agent Interface
================================
Interactive terminal interface for testing the autonomous agent.
Uses CLI-based human-in-the-loop approval for risky actions.

Usage:
    cd backend
    python -m app.agent.cli

Commands:
    Type any task and press Enter to run the agent.
    Type 'quit' or 'exit' to stop.
    Type 'tools' to list available tools.
    Type 'memory' to show episodic memory.
"""

import asyncio
import sys
import os
import logging

# Fix Windows terminal encoding — cp1252 can't render emoji/unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    # Enable ANSI escape codes on Windows 10+
    os.system("")

# Add backend directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.agent.loop import AgentLoop
from app.agent.memory import agent_memory
from app.core.tool_registry import tool_registry

# Import tools to trigger registration
import app.tools  # noqa: F401

logging.basicConfig(
    level=logging.WARNING,  # Keep quiet for CLI — only show errors
    format="%(levelname)s | %(message)s",
)


# ANSI color codes for terminal output
class Colors:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


BANNER = f"""
{Colors.CYAN}{Colors.BOLD}
    ╔══════════════════════════════════════════════════╗
    ║          🌟 ASTRA OS — Agent CLI v3.0           ║
    ║      Observe → Think → Plan → Act → Reflect     ║
    ╚══════════════════════════════════════════════════╝
{Colors.RESET}
{Colors.DIM}  Model: {{model}} | Tools: {{tool_count}} registered
  Type a task, 'tools' to list tools, 'quit' to exit.{Colors.RESET}
"""

PHASE_ICONS = {
    "observe": f"{Colors.BLUE}👁  OBSERVE{Colors.RESET}",
    "think": f"{Colors.MAGENTA}🧠 THINK{Colors.RESET}",
    "plan": f"{Colors.YELLOW}📋 PLAN{Colors.RESET}",
    "act": f"{Colors.GREEN}⚡ ACT{Colors.RESET}",
    "reflect": f"{Colors.CYAN}🪞 REFLECT{Colors.RESET}",
}


async def run_cli():
    """Main CLI loop."""
    from app.core.config import settings

    agent = AgentLoop(approval_mode="cli")
    tool_count = len(tool_registry.get_all_tools())

    print(BANNER.format(model=settings.DEFAULT_MODEL, tool_count=tool_count))

    while True:
        try:
            # Prompt
            task = input(f"\n{Colors.BOLD}{Colors.GREEN}ASTRA >{Colors.RESET} ").strip()

            if not task:
                continue

            if task.lower() in ("quit", "exit", "q"):
                print(f"\n{Colors.DIM}Goodbye! 👋{Colors.RESET}")
                break

            if task.lower() == "tools":
                tools = tool_registry.get_all_tools()
                print(f"\n{Colors.BOLD}Registered Tools ({len(tools)}):{Colors.RESET}")
                for t in tools:
                    risk = getattr(tool_registry.get_tool(t["name"]), "risk_level", "safe")
                    risk_icon = {"safe": "🟢", "moderate": "🟡", "risky": "🔴"}.get(str(risk), "⚪")
                    print(f"  {risk_icon} {t['name']}: {t['description'][:80]}")
                continue

            if task.lower() == "memory":
                result = agent_memory.episodic.get_all_episodes(project_id="default", limit=10)
                episodes = result.get("episodes", [])
                total = result.get("total", 0)
                if not episodes:
                    print(f"\n{Colors.DIM}No episodic memories yet.{Colors.RESET}")
                else:
                    print(f"\n{Colors.BOLD}Episodic Memory ({total} total, showing last {len(episodes)}):{Colors.RESET}")
                    for ep in episodes:
                        icon = "✅" if ep["success"] else "❌"
                        print(f"  {icon} {ep['task'][:60]} — {ep['summary'][:80]}")
                continue

            # Run the agent
            print(f"\n{Colors.DIM}{'─' * 50}{Colors.RESET}")

            try:
                async for event in agent.run(task=task):
                    event_type = event.type

                    if event_type == "phase_change":
                        phase = event.phase or ""
                        icon = PHASE_ICONS.get(phase, f"  {phase.upper()}")
                        if event.content:
                            print(f"\n{icon} {Colors.DIM}{event.content}{Colors.RESET}")
                        else:
                            print(f"\n{icon}")

                    elif event_type == "thought":
                        # Print thinking text in magenta
                        print(f"  {Colors.MAGENTA}{event.content}{Colors.RESET}")

                    elif event_type == "tool_call":
                        data = event.data or {}
                        args = data.get("arguments", {})
                        args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
                        print(f"  {Colors.GREEN}🔧 {event.content}({args_str}){Colors.RESET}")

                    elif event_type == "tool_result":
                        data = event.data or {}
                        success = data.get("success", True)
                        icon = "✅" if success else "❌"
                        time_ms = data.get("time_ms", 0)
                        content = event.content or ""
                        # Truncate long results
                        if len(content) > 300:
                            content = content[:300] + "..."
                        print(f"  {icon} Result ({time_ms:.0f}ms): {Colors.DIM}{content}{Colors.RESET}")

                    elif event_type == "approval_required":
                        # The approval prompt itself is handled by CLIApprovalGate
                        pass

                    elif event_type == "reflection":
                        print(f"  {Colors.CYAN}{event.content}{Colors.RESET}")

                    elif event_type == "answer":
                        print(f"\n{Colors.BOLD}{Colors.GREEN}{'━' * 50}")
                        print(f"📍 ANSWER:{Colors.RESET}")
                        print(f"{event.content}")
                        print(f"{Colors.GREEN}{'━' * 50}{Colors.RESET}")

                    elif event_type == "error":
                        print(f"  {Colors.RED}❌ {event.content}{Colors.RESET}")

                    elif event_type == "done":
                        pass  # Handled by answer

            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}⚡ Task cancelled.{Colors.RESET}")
                continue

        except KeyboardInterrupt:
            print(f"\n\n{Colors.DIM}Interrupted. Type 'quit' to exit.{Colors.RESET}")
        except EOFError:
            break


def main():
    """Entry point."""
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
