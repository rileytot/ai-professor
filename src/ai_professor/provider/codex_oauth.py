"""The OAuth Codex backend (the v1 preferred runtime route).

Consumes the user's existing Codex/ChatGPT auth from ``~/.codex/auth.json`` and calls the Codex
backend's Responses endpoint, which is stateless (we resend the full history each call) and streams
the answer as Server-Sent Events. Credentials are password-equivalent: the access token is never
logged (``repr=False``).

This route is UNOFFICIAL and can change. The wire details below were validated live against the
current Codex backend (June 2026): endpoint ``/backend-api/codex/responses``; ChatGPT-account
models are ``gpt-5.5`` / ``gpt-5.4`` / ``gpt-5.4-mini`` (NOT the ``*-codex`` names -- those are
rejected for ChatGPT accounts); the ``originator: codex_cli_rs`` header is required (403 without
it); the answer accumulates from ``response.output_text.delta`` SSE events. Revalidate after a
Codex update.

**Token refresh.** The access token is short-lived. We re-read ``auth.json`` each call (so a refresh
by the Codex app is picked up automatically) and, for long sessions where the Codex app is not
actively refreshing, refresh it ourselves: proactively when it is within minutes of expiry, and on a
401. A refresh rotates the refresh token server-side, so we write the rotated token back atomically
to keep the Codex app working too. (A simultaneous refresh by the Codex app at the same instant is a
rare edge case -- during a learning session the user is driving this harness, not Codex.)
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
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

# Token refresh (auth.openai.com). Constants from the openai/codex source.
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
TOKEN_URL = "https://auth.openai.com/oauth/token"
_REFRESH_WINDOW_S = 5 * 60  # refresh if the access token expires within this many seconds


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
    data = _read_auth_file(path)
    if data is None:
        return None
    raw_tokens = data.get("tokens")
    tokens = raw_tokens if isinstance(raw_tokens, dict) else {}
    access_token = data.get("access_token") or tokens.get("access_token")
    account_id = data.get("account_id") or tokens.get("account_id") or ""
    if not isinstance(access_token, str) or not access_token:
        return None
    return CodexAuth(access_token=access_token, account_id=str(account_id))


# --- token refresh -----------------------------------------------------------------------------


def _read_auth_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _write_auth_file(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same filesystem


def _jwt_exp(token: str) -> int | None:
    """Read the ``exp`` (epoch seconds) claim from a JWT access token, or None if unreadable."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return int(exp) if isinstance(exp, int | float) else None


def needs_refresh(
    access_token: str, *, now: float | None = None, window_s: int = _REFRESH_WINDOW_S
) -> bool:
    """True if the token expires within ``window_s`` (False if its expiry can't be read)."""
    exp = _jwt_exp(access_token)
    if exp is None:
        return False
    return exp - (time.time() if now is None else now) <= window_s


def refresh_codex_auth(path: Path, *, client: httpx.Client | None = None) -> CodexAuth | None:
    """Refresh the access token via auth.openai.com and write the rotated tokens back atomically."""
    data = _read_auth_file(path)
    if data is None:
        return None
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    refresh_token = tokens.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    body = {
        "client_id": CODEX_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {"Content-Type": "application/json"}
    try:
        if client is not None:
            resp = client.post(TOKEN_URL, json=body, headers=headers)
        else:
            with httpx.Client(timeout=30.0) as owned:
                resp = owned.post(TOKEN_URL, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise TransportError(f"Codex token refresh failed: {exc}") from exc
    if resp.status_code != 200:
        raise AuthError(f"Codex token refresh rejected (HTTP {resp.status_code})")
    new = resp.json()
    if not isinstance(new, dict):
        raise AuthError("Codex token refresh returned an unexpected body")
    for key in ("access_token", "id_token", "refresh_token"):
        value = new.get(key)
        if isinstance(value, str) and value:
            tokens[key] = value
    data["tokens"] = tokens
    data["last_refresh"] = datetime.now(UTC).isoformat()
    _write_auth_file(path, data)
    return load_codex_auth(path)


# --- request/response shaping ------------------------------------------------------------------


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
        refresh: bool = True,
    ) -> None:
        self._auth_path = auth_path if auth_path is not None else default_codex_auth_path()
        self._client = client  # injectable for tests; if None, a client is created per call
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._refresh = refresh

    def available(self) -> bool:
        return load_codex_auth(self._auth_path) is not None

    def complete(self, request: CompletionRequest) -> Completion:
        auth = self._fresh_auth()
        if auth is None:
            raise AuthError(
                f"no Codex credentials at {self._auth_path}; "
                "sign in via the Codex app or run `codex login`"
            )
        payload = self._build_payload(request)
        url = f"{self._base_url}{RESPONSES_PATH}"
        if self._client is not None:
            sse = self._post_with_retry(self._client, url, payload, auth)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                sse = self._post_with_retry(client, url, payload, auth)
        return Completion(text=parse_sse_text(sse), model=str(payload["model"]), backend=self.name)

    def _fresh_auth(self) -> CodexAuth | None:
        auth = load_codex_auth(self._auth_path)
        if auth is None:
            return None
        if self._refresh and needs_refresh(auth.access_token):
            refreshed = self._safe_refresh(self._client)
            if refreshed is not None:
                return refreshed
        return auth

    def _safe_refresh(self, client: httpx.Client | None) -> CodexAuth | None:
        try:
            return refresh_codex_auth(self._auth_path, client=client)
        except (AuthError, TransportError):
            return None

    def _headers(self, auth: CodexAuth) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
            **_STATIC_HEADERS,
        }
        if auth.account_id:
            headers[ACCOUNT_HEADER] = auth.account_id
        return headers

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

    def _post_with_retry(
        self, client: httpx.Client, url: str, payload: dict[str, Any], auth: CodexAuth
    ) -> str:
        try:
            return self._post(client, url, payload, self._headers(auth))
        except AuthError:
            if not self._refresh:
                raise
            refreshed = self._safe_refresh(client)
            if refreshed is None:
                raise
            return self._post(client, url, payload, self._headers(refreshed))

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
            raise AuthError(f"Codex rejected credentials (HTTP {code})")  # may refresh + retry
        if code in (408, 429) or code >= 500:
            raise TransportError(f"Codex HTTP {code}")  # transient/server -> fall back
        if code >= 400:
            raise BadRequestError(
                f"Codex HTTP {code}: {resp.text[:200]}"
            )  # client error -> propagate
        return resp.text
