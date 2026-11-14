"""Owner-only access. Every console and API route depends on `require_owner`; a test enforces that no route is added
without it (except the short, explicit PUBLIC list in app.py).

The owner has ONE credential: a random access token created by `nano-agent setup` and kept in the secrets store.
  * Browser: open the console URL that ends in `#token=...` (a fragment is never sent to the server, so it is not in logs
    or Referer headers). The page posts it once to /api/login and gets an HttpOnly, SameSite=Lax session cookie.
  * Scripts: `Authorization: Bearer <token>`.
  * Inside LINE: the LIFF SDK gives an id token; /api/login/liff verifies it with LINE and requires that its subject is
    the paired owner's LINE user id.
Mutating requests with an Origin header must come from the same host (CSRF defence in depth on top of SameSite).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets as pysecrets
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response

from .. import keystore

COOKIE = "nano_session"
_FAILS: dict[str, list[float]] = {}


def owner_token() -> str:
    tok = keystore.get("owner.token")
    if not tok:
        tok = pysecrets.token_urlsafe(32)
        keystore.set_("owner.token", tok)
    return tok


def session_value(token: str) -> str:
    return hmac.new(token.encode(), b"nano-agent-session-v1", hashlib.sha256).hexdigest()


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True   # non-browser clients (curl, scripts) send none
    host = request.headers.get("host", "")
    return urlparse(origin).netloc == host


def is_owner(request: Request) -> bool:
    tok = keystore.get("owner.token")
    if not tok:
        return False
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), tok):
        return True
    cookie = request.cookies.get(COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie, session_value(tok))


async def require_owner(request: Request) -> None:
    if not is_owner(request):
        raise HTTPException(status_code=401, detail="owner login required")
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
        raise HTTPException(status_code=403, detail="cross-origin request refused")


def throttle(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _FAILS.get(ip, []) if now - t < 600]
    if len(recent) >= 10:
        raise HTTPException(status_code=429, detail="too many attempts; wait ten minutes")
    _FAILS[ip] = recent


def record_failure(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    _FAILS.setdefault(ip, []).append(time.time())


def login_ok(response: Response, request: Request) -> None:
    tok = keystore.get("owner.token") or ""
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(COOKIE, session_value(tok), httponly=True, samesite="lax", secure=secure, max_age=30 * 86400, path="/")


def check_login_token(token: str) -> bool:
    tok = keystore.get("owner.token") or ""
    return bool(tok) and hmac.compare_digest((token or "").strip(), tok)
