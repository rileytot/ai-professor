"""The OAuth Codex backend (the v1 preferred runtime route).

Consumes the user's existing Codex/ChatGPT auth from ``~/.codex/auth.json`` and calls the Codex
backend's Responses endpoint, which is stateless (we resend the full history each call) and streams
the answer as Server-Sent Events. Credentials are password-equivalent: the access token is never
logged (``repr=False``) and never persisted by us.

This route is UNOFFICIAL and can change. The wire details below were validated live against the
current Codex backend (June 2026): endpoint ``/backend-api/codex/responses``; ChatGPT-account
models are ``gpt-5.5`` / ``gpt-5.4`` / ``gpt-5.4-mini`` (NOT the ``*-codex`` names -- those are
rejected for ChatGPT accounts); the answer text accumulates from ``response.output_text.delta``
SSE events. They may need revalidation after a Codex update.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from ai_professor.provider.adapter import (
    AuthError,
    BadRequestError,
    Completion,
    CompletionRequest,
    TransportError,
)

# --- wire constants (validated live; revalidate after a Codex update) --------------------------
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
RESPONSES_PATH = "/responses"
ACCOUNT_HEADER = "ChatGPT-Account-ID"  # casing matches the Codex CLI (header is case-insensitive)
CODEX_DEFAULT_MODEL = "gpt-5.5"
# Models the ChatGPT-account Codex route exposes (from GET /codex/models). codex-auto-review is a
# special-purpose model and is intentionally omitted from the general-use set.
SUPPORTED_MODELS = ("gpt-5.5", "gpt-5.4", "gpt-5.4-mini")
DEFAULT_TIMEOUT_S = 120.0
_STATIC_HEADERS = {
    "OpenAI-Beta": "responses=experimental",
    "originator": "codex_cli_rs",
    "User-Agent": "codex_cli_rs/0.0.0",
    "Accept": "text/event-stream",
}


def default_codex_auth_path() -> Path:
    return Path.home() / ".codex" / "auth.json"


@dataclass(frozen=True, slots=True)
class CodexAuth:
    """Loaded Codex credentials. ``access_token`` is secret and kept out of reprs/logs."""

    access_token: str = field(repr=False)
    account_id: str = ""


def load_codex_auth(path: Path) -> CodexAuth | None:
    """Load credentials from a Codex ``auth.json`` (flat or nested ``tokens``).

    Returns ``None`` if the file is absent, unreadable, malformed, or missing an access token.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw_tokens = data.get("tokens")
    tokens = raw_tokens if isinstance(raw_tokens, dict) else {}
    access_token = data.get("access_token") or tokens.get("access_token")
    account_id = data.get("account_id") or tokens.get("account_id") or ""
    if not isinstance(access_token, str) or not access_token:
        return None
    return CodexAuth(access_token=access_token, account_id=str(account_id))


def _content_part_type(role: str) -> str:
    # Responses-API input items: prior assistant turns use output_text, everything else input_text.
    return "output_text" if role == "assistant" else "input_text"


def parse_sse_text(sse: str) -> str:
    """Assemble the answer text from a Responses SSE stream (output_text.delta events)."""
    parts: list[str] = []
    completed_text: str | None = None
    for line in sse.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")
        if etype == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str):
                parts.append(delta)
        elif etype == "response.completed":
            completed_text = _text_from_response(event.get("response", {}))
        elif etype in ("response.failed", "response.error", "error"):
            detail = event.get("response", {}).get("error") or event.get("error") or "stream error"
            raise TransportError(f"Codex stream error: {detail}")
    if parts:
        return "".join(parts)
    if completed_text is not None:
        return completed_text
    raise TransportError("Codex returned no output text")


def _text_from_response(response: dict[str, Any]) -> str | None:
    for item in response.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text" and isinstance(c.get("text"), str):
                    return str(c["text"])
    return None


class CodexBackend:
    """Backend that calls the Codex Responses endpoint with the user's OAuth credentials."""

    name = "codex-oauth"

    def __init__(
        self,
        *,
        auth_path: Path | None = None,
        client: httpx.Client | None = None,
        model: str = CODEX_DEFAULT_MODEL,
        base_url: str = CODEX_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._auth_path = auth_path if auth_path is not None else default_codex_auth_path()
        self._client = client  # injectable for tests; if None, a client is created per call
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    def available(self) -> bool:
        return load_codex_auth(self._auth_path) is not None

    def complete(self, request: CompletionRequest) -> Completion:
        auth = load_codex_auth(self._auth_path)
        if auth is None:
            raise AuthError(f"no Codex credentials at {self._auth_path}")
        headers = {
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
            **_STATIC_HEADERS,
        }
        if auth.account_id:
            headers[ACCOUNT_HEADER] = auth.account_id
        payload = self._build_payload(request)
        url = f"{self._base_url}{RESPONSES_PATH}"
        if self._client is not None:
            sse = self._post(self._client, url, payload, headers)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                sse = self._post(client, url, payload, headers)
        return Completion(text=parse_sse_text(sse), model=str(payload["model"]), backend=self.name)

    def _build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "input": [
                {
                    "role": m.role,
                    "content": [{"type": _content_part_type(m.role), "text": m.content}],
                }
                for m in request.messages
                if m.role != "system"
            ],
            "stream": True,
            "store": False,
        }
        if system:
            payload["instructions"] = system
        if request.max_tokens is not None:
            payload["max_output_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _post(
        self,
        client: httpx.Client,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> str:
        try:
            resp = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise TransportError(f"Codex request failed: {exc}") from exc
        code = resp.status_code
        if code in (401, 403):
            raise AuthError(f"Codex rejected credentials (HTTP {code})")  # fall back
        if code in (408, 429) or code >= 500:
            raise TransportError(f"Codex HTTP {code}")  # transient/server -> fall back
        if code >= 400:
            raise BadRequestError(
                f"Codex HTTP {code}: {resp.text[:200]}"
            )  # client error -> propagate
        return resp.text
