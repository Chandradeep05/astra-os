"""Benchmark: how long does a tool call take with 1 tool vs 12 tools."""
import httpx
import time
import json

BASE = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"

# Minimal — 1 tool
one_tool = [{"type": "function", "function": {
    "name": "system_info",
    "description": "Get current time and date",
    "parameters": {"type": "object", "properties": {"info_type": {"type": "string"}}, "required": ["info_type"]}
}}]

print("=" * 50)
print("Benchmark: Ollama tool calling speed")
print("=" * 50)

# Test 1: With 1 tool
print("\nTest 1: 1 tool definition...")
start = time.time()
r = httpx.post(BASE, json={
    "model": MODEL,
    "messages": [{"role": "user", "content": "What time is it?"}],
    "tools": one_tool,
    "stream": False,
    "keep_alive": "30m",
    "options": {"num_predict": 256, "num_ctx": 4096},
}, timeout=600)
elapsed = time.time() - start
msg = r.json().get("message", {})
print(f"  Time: {elapsed:.1f}s")
print(f"  Tool calls: {msg.get('tool_calls', 'none')}")
print(f"  Content: {msg.get('content', '')[:100]}")

# Test 2: With no tools (baseline)
print("\nTest 2: No tools (baseline)...")
start = time.time()
r = httpx.post(BASE, json={
    "model": MODEL,
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "stream": False,
    "keep_alive": "30m",
    "options": {"num_predict": 50, "num_ctx": 4096},
}, timeout=600)
elapsed = time.time() - start
msg = r.json().get("message", {})
print(f"  Time: {elapsed:.1f}s")
print(f"  Content: {msg.get('content', '')[:100]}")

print("\nDone!")
