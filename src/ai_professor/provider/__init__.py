"""Swappable ``LLMProvider`` adapter and backends.

One interface; multiple backends behind it with automatic fallback (DESIGN.md runtime model
posture): the OAuth Codex route first, then litellm-backed fallbacks (Anthropic / OpenAI /
Ollama-local). Switching among implemented backends is a config flip, not a rearchitecture.
"""
