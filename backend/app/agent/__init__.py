# ============================================
# ASTRA OS — Autonomous Agent Module
# ============================================
# This module implements the core cognitive loop:
# Observe → Think → Plan → Act → Reflect (OTPAR)
#
# Designed for:
#   - Local-first execution via Ollama
#   - Low RAM usage (single model loaded at a time)
#   - Human-in-the-loop for risky actions
#   - Easy model swapping (llama3.2:3b → qwen2.5:3b)
# ============================================
