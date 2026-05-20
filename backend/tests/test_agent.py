"""Test the fixed agent with qwen2.5:3b and prompt-based tool calling."""
import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

async def test():
    from app.agent.loop import AgentLoop
    import app.tools

    agent = AgentLoop(approval_mode="auto")  # Auto-approve everything for testing

    tests = [
        "What is the current date and time?",
        "Remember that my name is Chandradeep and I am building ASTRA OS",
    ]

    for task in tests:
        print(f"\n{'='*60}")
        print(f"TASK: {task}")
        print(f"{'='*60}")

        async for event in agent.run(task=task):
            if event.type == "phase_change":
                print(f"  [{event.phase}]")
            elif event.type == "thought":
                print(f"  [THINK]  {(event.content or '')[:150]}")
            elif event.type == "tool_call":
                data = event.data or {}
                print(f"  [TOOL]   {data.get('tool', '?')}({data.get('arguments', {})})")
            elif event.type == "tool_result":
                content = (event.content or "")[:200]
                print(f"  [RESULT] {content}")
            elif event.type == "reflection":
                print(f"  [REFLECT] {(event.content or '')[:200]}")
            elif event.type == "answer":
                print(f"  [ANSWER] {event.content}")
            elif event.type == "error":
                print(f"  [ERROR]  {event.content}")

    print(f"\n{'='*60}")
    print("ALL TESTS COMPLETE")
    print(f"{'='*60}")

if __name__ == "__main__":
    asyncio.run(test())
