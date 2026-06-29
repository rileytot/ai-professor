"""Tests for the provider auto-fallback engine."""

from __future__ import annotations

import pytest

from ai_professor.provider.adapter import (
    AuthError,
    BadRequestError,
    Completion,
    CompletionRequest,
    LLMProvider,
    Message,
    NoBackendAvailable,
    TransportError,
)


class FakeBackend:
    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        result: Completion | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._available = available
        self._result = result
        self._error = error
        self.calls = 0

    def available(self) -> bool:
        return self._available

    def complete(self, request: CompletionRequest) -> Completion:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _req() -> CompletionRequest:
    return CompletionRequest(messages=[Message(role="user", content="hi")])


def _ok(name: str) -> Completion:
    return Completion(text="ok", model="m", backend=name)


def test_returns_first_available_success() -> None:
    primary = FakeBackend("primary", result=_ok("primary"))
    provider = LLMProvider([primary])
    assert provider.complete(_req()).backend == "primary"
    assert primary.calls == 1


def test_falls_back_on_auth_error() -> None:
    primary = FakeBackend("primary", error=AuthError("expired"))
    fallback = FakeBackend("fallback", result=_ok("fallback"))
    provider = LLMProvider([primary, fallback])
    assert provider.complete(_req()).backend == "fallback"
    assert (primary.calls, fallback.calls) == (1, 1)


def test_falls_back_on_transport_error() -> None:
    primary = FakeBackend("primary", error=TransportError("network"))
    fallback = FakeBackend("fallback", result=_ok("fallback"))
    provider = LLMProvider([primary, fallback])
    assert provider.complete(_req()).backend == "fallback"


def test_skips_unavailable_backend_without_calling() -> None:
    down = FakeBackend("down", available=False)
    up = FakeBackend("up", result=_ok("up"))
    provider = LLMProvider([down, up])
    assert provider.complete(_req()).backend == "up"
    assert down.calls == 0


def test_raises_when_all_backends_fail() -> None:
    provider = LLMProvider(
        [
            FakeBackend("a", error=AuthError("x")),
            FakeBackend("b", error=TransportError("y")),
        ]
    )
    with pytest.raises(NoBackendAvailable):
        provider.complete(_req())


def test_non_fallback_error_propagates() -> None:
    # A bug (e.g. a malformed request) is not something a different backend would fix.
    primary = FakeBackend("primary", error=ValueError("bad request"))
    fallback = FakeBackend("fallback", result=_ok("fallback"))
    provider = LLMProvider([primary, fallback])
    with pytest.raises(ValueError, match="bad request"):
        provider.complete(_req())
    assert fallback.calls == 0


def test_bad_request_propagates_without_fallback() -> None:
    # A 4xx client error is a bug; switching backends would mask it, so it must propagate.
    primary = FakeBackend("primary", error=BadRequestError("malformed"))
    fallback = FakeBackend("fallback", result=_ok("fallback"))
    provider = LLMProvider([primary, fallback])
    with pytest.raises(BadRequestError):
        provider.complete(_req())
    assert fallback.calls == 0


def test_backend_names() -> None:
    provider = LLMProvider([FakeBackend("a"), FakeBackend("b")])
    assert provider.backend_names == ["a", "b"]
