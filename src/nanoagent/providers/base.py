"""The one interface every model provider implements, plus shared HTTP and error handling.

Internal message format (provider adapters translate to and from it):

    {"role": "system" | "user" | "assistant" | "tool", "content": str | [parts],
     "tool_calls": [{"id", "name", "args"}]      # assistant only
     "tool_call_id": str, "name": str}           # tool results only

`content` parts for vision: {"type": "text", "text": ...} and {"type": "image", "mime": ..., "data": <base64>}.
Tools are [{"name", "description", "parameters": <JSON schema>}].
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from .. import keystore as secrets

DEFAULT_TRANSPORT: httpx.AsyncBaseTransport | None = None   # tests inject httpx.MockTransport here


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Response:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    stop: str = ""


class ProviderError(Exception):
    """A failure with a message that is safe to show (secrets already masked) and a hint on how to fix it."""

    def __init__(self, message: str, hint: str = "", status: int = 0, kind: str = "error"):
        super().__init__(message)
        self.message, self.hint, self.status, self.kind = message, hint, status, kind

    def __str__(self) -> str:
        return self.message + (f" — {self.hint}" if self.hint else "")


def explain_status(status: int, body: str, base_url: str) -> ProviderError:
    detail = secrets.redact(body)[:300]
    if status in (401, 403):
        return ProviderError(f"The provider rejected the API key (HTTP {status}).",
                             "Check the key (`nano-agent models set-key`), its permissions, and that it belongs to this provider.", status, "auth")
    if status == 404:
        return ProviderError("Not found (HTTP 404): the model name or the base URL is wrong.",
                             f"Base URL is {base_url}. Check the model id spelling; for local servers the base URL usually ends in /v1.", status, "not_found")
    if status == 429:
        return ProviderError("Rate limit or quota reached (HTTP 429).", "Wait a moment, check your plan and billing, or pick another model.", status, "rate_limit")
    if status == 400:
        return ProviderError(f"The provider rejected the request (HTTP 400): {detail}",
                             "Often an unknown model id or a model without tool support.", status, "bad_request")
    if status >= 500:
        return ProviderError(f"The provider had a server error (HTTP {status}).", "Try again shortly.", status, "server")
    return ProviderError(f"Unexpected response (HTTP {status}): {detail}", "", status)


class Provider:
    kind = "base"

    def __init__(self, name: str, base_url: str, api_key: str = "", timeout: float = 120.0, transport=None):
        self.name, self.base_url, self.api_key, self.timeout = name, base_url.rstrip("/"), api_key, timeout
        self.transport = transport or DEFAULT_TRANSPORT

    # ---- to implement -------------------------------------------------
    async def chat(self, model: str, messages: list[dict], tools: list[dict] | None = None, system: str | None = None,
                   temperature: float | None = None, max_tokens: int | None = None) -> Response:
        raise NotImplementedError

    # ---- shared -------------------------------------------------------
    async def _post(self, url: str, headers: dict, payload: dict, retries: int = 2) -> dict:
        delay = 1.0
        for attempt in range(retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
                    r = await c.post(url, headers=headers, json=payload)
            except httpx.ConnectError:
                raise ProviderError(f"Cannot connect to {self.base_url}.",
                                    "Is the server running and the base URL right? For local servers check the port.", kind="connect") from None
            except httpx.TimeoutException:
                if attempt < retries:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                raise ProviderError("The provider did not answer in time.", "Try again, or use a faster model.", kind="timeout") from None
            except httpx.HTTPError as e:
                raise ProviderError(f"Network error: {secrets.redact(e)}", kind="network") from None
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if r.status_code >= 400:
                raise explain_status(r.status_code, r.text, self.base_url)
            try:
                return r.json()
            except json.JSONDecodeError:
                raise ProviderError("The provider returned something that is not JSON.", "Check the base URL.", kind="bad_response") from None
        raise ProviderError("Request failed.")  # pragma: no cover

    async def ping(self, model: str) -> tuple[bool, str]:
        """One tiny call that checks the key, the base URL and the model together. Returns (ok, short message)."""
        try:
            r = await self.chat(model, [{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=16, temperature=0)
        except ProviderError as e:
            return False, str(e)
        except Exception as e:  # never leak a key through an unexpected exception text
            return False, "Unexpected error: " + secrets.redact(e)
        return True, (r.text.strip() or "(empty reply)")[:60]


def text_of(content: Any) -> str:
    """Flatten message content (string or parts) to plain text."""
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")


def parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
