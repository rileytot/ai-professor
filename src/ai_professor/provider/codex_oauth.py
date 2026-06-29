"""The OAuth Codex backend (the v1 preferred runtime route).

Consumes the user's existing Codex/ChatGPT auth from ``~/.codex/auth.json`` and calls the Codex
backend endpoint, which is OpenAI-Responses-shaped and stateless (we resend the full history each
call). Credentials are password-equivalent: the access token is never logged (``repr=False``) and
never persisted by us.

This route is UNOFFICIAL and can change. The wire details below (endpoint, header names, default
model, response shape) are isolated into named constants/methods and MUST be validated against the
current Codex backend before relying on the live path. The structure, auth loading, error mapping,
and request shaping are unit-tested with mocked HTTP and a temp auth file.
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

# --- wire constants (per the documented Codex pattern; validate live before trusting) ----------
CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
RESPONSES_PATH = "/responses"
ACCOUNT_HEADER = "chatgpt-account-id"
CODEX_DEFAULT_MODEL = "gpt-5.1-codex"
DEFAULT_TIMEOUT_S = 60.0


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
        }
        if auth.account_id:
            headers[ACCOUNT_HEADER] = auth.account_id
        payload = self._build_payload(request)
        url = f"{self._base_url}{RESPONSES_PATH}"
        if self._client is not None:
            data = self._post(self._client, url, payload, headers)
        else:
            with httpx.Client(timeout=self._timeout) as client:
                data = self._post(client, url, payload, headers)
        return Completion(
            text=self._parse_text(data), model=str(payload["model"]), backend=self.name
        )

    def _build_payload(self, request: CompletionRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "input": [{"role": m.role, "content": m.content} for m in request.messages],
        }
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
    ) -> dict[str, Any]:
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
            raise BadRequestError(f"Codex HTTP {code}")  # client error -> propagate (our bug)
        parsed: dict[str, Any] = resp.json()
        return parsed

    def _parse_text(self, data: dict[str, Any]) -> str:
        # Responses shape: output[] -> (type=message).content[] -> (type=output_text).text
        for item in data.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text = part.get("text", "")
                        return text if isinstance(text, str) else ""
        if isinstance(data.get("output_text"), str):  # SDK convenience field, if present
            return str(data["output_text"])
        raise TransportError("could not parse Codex response (unexpected shape)")
