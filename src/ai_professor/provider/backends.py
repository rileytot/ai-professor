"""Fallback backends and the default Codex-first provider wiring.

litellm gives one client for the fallback routes (Anthropic / OpenAI-standard / Ollama-local,
etc.). It is an optional dependency (the ``[llm]`` extra), lazy-imported so the package works
without it -- ``available()`` simply reports ``False`` when it is absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_professor.provider.adapter import (
    AuthError,
    Backend,
    Completion,
    CompletionRequest,
    LLMProvider,
    TransportError,
)
from ai_professor.provider.codex_oauth import CodexBackend


class LiteLLMBackend:
    """A fallback backend via litellm.

    ``model`` follows litellm naming, e.g. "anthropic/claude-sonnet-4-6" or "ollama/llama3".
    """

    def __init__(self, model: str, *, name: str | None = None) -> None:
        self._model = model
        self.name = name if name is not None else f"litellm:{model}"

    def available(self) -> bool:
        try:
            import litellm  # noqa: F401
        except ImportError:
            return False
        return True

    def complete(self, request: CompletionRequest) -> Completion:
        try:
            import litellm
        except ImportError as exc:
            raise TransportError("litellm is not installed (pip install '.[llm]')") from exc
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        kwargs: dict[str, Any] = {}
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        try:
            resp = litellm.completion(model=self._model, messages=messages, **kwargs)
        except Exception as exc:
            # Both auth and transport failures should trigger fallback; we only label for logs.
            if "auth" in type(exc).__name__.lower():
                raise AuthError(str(exc)) from exc
            raise TransportError(str(exc)) from exc
        text = str(resp.choices[0].message.content or "")
        return Completion(text=text, model=self._model, backend=self.name)


def build_default_provider(
    *,
    codex_auth_path: Path | None = None,
    fallback_models: Sequence[str] = (),
) -> LLMProvider:
    """Wire the default provider: the OAuth Codex route first, then any litellm fallbacks.

    ``fallback_models`` are litellm model strings (e.g. "anthropic/claude-sonnet-4-6",
    "ollama/llama3"). Supplying them is how a deployment degrades gracefully if the Codex route
    is cut -- without changing any calling code.
    """
    backends: list[Backend] = [CodexBackend(auth_path=codex_auth_path)]
    backends.extend(LiteLLMBackend(model) for model in fallback_models)
    return LLMProvider(backends)
