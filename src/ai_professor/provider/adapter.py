"""The one ``LLMProvider`` interface and its auto-fallback engine.

The professor and extractor call LLMs only through this interface (the v1 judger is deterministic
and calls no LLM). Multiple backends sit behind it; on an auth/transport failure of the preferred
backend the provider drops to the next available one automatically -- so "use OAuth as long as
possible" never breaks a session mid-curriculum (DESIGN.md runtime-model posture).

Backends differ in *wire shape*, not just credentials; each backend absorbs its own shape so that
switching among implemented backends is a config flip. Statelessness (e.g. the Codex route) is
handled naturally because every call passes the full message history.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """Base class for provider failures."""


class AuthError(ProviderError):
    """Credentials are missing, invalid, or rejected. Triggers fallback."""


class TransportError(ProviderError):
    """Network/HTTP/backend failure. Triggers fallback."""


class NoBackendAvailable(ProviderError):
    """Every backend was unavailable or failed with an auth/transport error."""


@dataclass(frozen=True, slots=True)
class Message:
    """One conversation turn. ``role`` is "system" | "user" | "assistant"."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """A request for a completion over the full message history."""

    messages: Sequence[Message]
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    """A model response. ``backend`` records which backend served it (observability)."""

    text: str
    model: str
    backend: str


class Backend(Protocol):
    """A single LLM backend behind the adapter."""

    name: str

    def available(self) -> bool:
        """Cheap check (e.g. credentials present) -- avoids attempting a doomed call."""
        ...

    def complete(self, request: CompletionRequest) -> Completion:
        """Perform the call. Raise ``AuthError``/``TransportError`` to trigger fallback."""
        ...


class LLMProvider:
    """Tries backends in priority order; falls back automatically on auth/transport failure.

    Non-auth/transport errors (e.g. a malformed request) propagate -- those are bugs to fix, not
    conditions a different backend would resolve.
    """

    def __init__(self, backends: Sequence[Backend]) -> None:
        self._backends = list(backends)

    @property
    def backend_names(self) -> list[str]:
        return [b.name for b in self._backends]

    def complete(self, request: CompletionRequest) -> Completion:
        failures: list[str] = []
        for backend in self._backends:
            try:
                if not backend.available():
                    failures.append(f"{backend.name}: unavailable")
                    continue
                return backend.complete(request)
            except (AuthError, TransportError) as exc:
                failures.append(f"{backend.name}: {type(exc).__name__}")
                continue
        raise NoBackendAvailable("; ".join(failures) or "no backends configured")
