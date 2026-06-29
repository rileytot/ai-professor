"""Tests for the Codex OAuth backend: auth loading, request shaping, parsing, error mapping.

The live Codex endpoint is never contacted -- HTTP is mocked via ``httpx.MockTransport`` and
credentials come from a temp file. (The real wire details still need live validation.)
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from ai_professor.provider.adapter import (
    AuthError,
    BadRequestError,
    CompletionRequest,
    Message,
    TransportError,
)
from ai_professor.provider.codex_oauth import CodexAuth, CodexBackend, load_codex_auth


def _write_auth(path: Path, **payload: object) -> Path:
    auth = path / "auth.json"
    auth.write_text(json.dumps(payload), encoding="utf-8")
    return auth


def _req() -> CompletionRequest:
    return CompletionRequest(messages=[Message(role="user", content="hi")])


def test_load_auth_flat(tmp_path: Path) -> None:
    auth = load_codex_auth(_write_auth(tmp_path, access_token="tok", account_id="acct"))
    assert auth == CodexAuth(access_token="tok", account_id="acct")


def test_load_auth_nested_tokens(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"tokens": {"access_token": "tok", "account_id": "acct"}}))
    auth = load_codex_auth(path)
    assert auth is not None
    assert auth.access_token == "tok"
    assert auth.account_id == "acct"


def test_load_auth_missing_file(tmp_path: Path) -> None:
    assert load_codex_auth(tmp_path / "nope.json") is None


def test_load_auth_malformed(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("not json at all")
    assert load_codex_auth(path) is None


def test_load_auth_without_token(tmp_path: Path) -> None:
    assert load_codex_auth(_write_auth(tmp_path, account_id="acct")) is None


def test_access_token_kept_out_of_repr() -> None:
    assert "secret" not in repr(CodexAuth(access_token="secret", account_id="a"))


def test_available_reflects_credentials(tmp_path: Path) -> None:
    present = CodexBackend(auth_path=_write_auth(tmp_path, access_token="tok"))
    absent = CodexBackend(auth_path=tmp_path / "nope.json")
    assert present.available() is True
    assert absent.available() is False


def test_complete_shapes_request_and_parses_response(tmp_path: Path) -> None:
    auth = _write_auth(tmp_path, access_token="tok", account_id="acct")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization")
        seen["account"] = request.headers.get("chatgpt-account-id")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "hello"}]}
                ]
            },
        )

    backend = CodexBackend(
        auth_path=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = backend.complete(_req())

    assert result.text == "hello"
    assert result.backend == "codex-oauth"
    assert str(seen["path"]).endswith("/responses")
    assert seen["auth"] == "Bearer tok"
    assert seen["account"] == "acct"
    assert seen["body"] == {"model": "gpt-5.1-codex", "input": [{"role": "user", "content": "hi"}]}


def test_complete_without_auth_raises(tmp_path: Path) -> None:
    backend = CodexBackend(auth_path=tmp_path / "nope.json")
    with pytest.raises(AuthError):
        backend.complete(_req())


def test_complete_maps_401_to_auth_error(tmp_path: Path) -> None:
    auth = _write_auth(tmp_path, access_token="tok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    backend = CodexBackend(
        auth_path=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AuthError):
        backend.complete(_req())


def test_complete_maps_400_to_bad_request_error(tmp_path: Path) -> None:
    # A client error is our bug, not a transient/auth failure: it must NOT trigger fallback.
    auth = _write_auth(tmp_path, access_token="tok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "malformed input"})

    backend = CodexBackend(
        auth_path=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(BadRequestError):
        backend.complete(_req())


def test_complete_maps_500_to_transport_error(tmp_path: Path) -> None:
    auth = _write_auth(tmp_path, access_token="tok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    backend = CodexBackend(
        auth_path=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TransportError):
        backend.complete(_req())


def test_complete_maps_network_error_to_transport_error(tmp_path: Path) -> None:
    auth = _write_auth(tmp_path, access_token="tok")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    backend = CodexBackend(
        auth_path=auth, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(TransportError):
        backend.complete(_req())
