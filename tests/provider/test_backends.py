"""Tests for the litellm fallback backend's lazy-import resilience and default wiring."""

from __future__ import annotations

import importlib.util

import pytest

from ai_professor.provider.adapter import CompletionRequest, Message, TransportError
from ai_professor.provider.backends import LiteLLMBackend, build_default_provider

_LITELLM_INSTALLED = importlib.util.find_spec("litellm") is not None


def test_litellm_available_reflects_install_state() -> None:
    # Importing the package must never require litellm; availability just mirrors its presence.
    assert LiteLLMBackend("anthropic/claude-x").available() is _LITELLM_INSTALLED


@pytest.mark.skipif(_LITELLM_INSTALLED, reason="litellm is installed in this environment")
def test_litellm_complete_raises_transport_error_when_absent() -> None:
    backend = LiteLLMBackend("anthropic/claude-x")
    request = CompletionRequest(messages=[Message(role="user", content="hi")])
    with pytest.raises(TransportError):
        backend.complete(request)


def test_default_provider_puts_codex_first() -> None:
    provider = build_default_provider(
        fallback_models=["anthropic/claude-sonnet-4-6", "ollama/llama3"]
    )
    assert provider.backend_names == [
        "codex-oauth",
        "litellm:anthropic/claude-sonnet-4-6",
        "litellm:ollama/llama3",
    ]


def test_default_provider_codex_only_by_default() -> None:
    assert build_default_provider().backend_names == ["codex-oauth"]
