"""LINE connector (official Messaging API only). Optional.

  * `/webhook/line` verifies X-Line-Signature (HMAC-SHA256 of the raw body with the channel secret) BEFORE parsing anything.
  * Only the paired owner is served. Everyone else gets no reply at all (we do not reveal that the bot is a personal one).
  * Pairing: `nano-agent line pair` prints a code; the owner sends `pair <code>` to the OA once and their user id is saved.
  * Messages from the owner go to the agent; the answer is a reply (free). Pending drafts get quick-reply buttons whose text
    carries the draft's one-time code (`send #12 a1b2c3`); a tap arrives as the owner's own message and is checked here.
  * Pushes (reminders, brief) go through outbox.flush with a monthly cap.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets as pysecrets
import time

import httpx

from .. import config, db, drafts, keystore
from .. import keystore as secrets

API = "https://api.line.me"
TRANSPORT: httpx.AsyncBaseTransport | None = None
PAIR_TTL = 900


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, signature)


def _token() -> str:
    return keystore.get("line.channel_token") or ""


async def _post(path: str, payload: dict) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20, transport=TRANSPORT, base_url=API) as c:
        return await c.post(path, json=payload, headers={"Authorization": f"Bearer {_token()}"})


async def reply(reply_token: str, messages: list[dict]) -> bool:
    r = await _post("/v2/bot/message/reply", {"replyToken": reply_token, "messages": messages[:5]})
    return r.status_code == 200


async def push(to: str, messages: list[dict]) -> None:
    r = await _post("/v2/bot/message/push", {"to": to, "messages": messages[:5]})
    if r.status_code != 200:
        raise RuntimeError(f"LINE push failed (HTTP {r.status_code})")


async def send_text(target: str, text: str) -> None:
    """The registered sender for channel 'line' (used for approved drafts and pushes)."""
    chunks = [text[i:i + 4800] for i in range(0, len(text), 4800)] or [""]
    await push(target, [{"type": "text", "text": c} for c in chunks[:5]])


def text_messages(text: str, quick: list[dict] | None = None) -> list[dict]:
    chunks = [text[i:i + 4800] for i in range(0, len(text), 4800)][:5] or ["(no reply)"]
    msgs = [{"type": "text", "text": c} for c in chunks]
    if quick:
        msgs[-1]["quickReply"] = {"items": quick[:13]}
    return msgs


def draft_buttons(draft_ids: list[int]) -> list[dict]:
    items = []
    for did in draft_ids[:6]:
        d = drafts.get(did)
        if d and d["status"] == "pending":
            items.append({"type": "action", "action": {"type": "message", "label": f"Send #{did}", "text": f"send #{did} {d['code']}"}})
            items.append({"type": "action", "action": {"type": "message", "label": f"Cancel #{did}", "text": f"cancel #{did}"}})
    return items


def new_pair_code() -> str:
    code = pysecrets.token_hex(3)
    db.kv_set("line_pair", {"code": code, "ts": time.time()})
    return code


def console_link() -> str:
    cfg = config.load()
    if cfg["line"]["liff_id"]:
        return f"https://liff.line.me/{cfg['line']['liff_id']}"
    base = cfg["gateway"]["public_url"] or f"http://{cfg['gateway']['host']}:{cfg['gateway']['port']}"
    return base.rstrip("/") + "/console"


def _bind_owner(user_id: str) -> None:
    cfg = config.load()
    cfg["line"]["owner_user_id"] = user_id
    config.save(cfg)


async def handle_event(ev: dict) -> None:
    if ev.get("type") != "message" or ev.get("message", {}).get("type") != "text":
        return
    uid = (ev.get("source") or {}).get("userId", "")
    text = ev["message"]["text"].strip()
    token = ev.get("replyToken", "")
    cfg = config.load()
    owner = cfg["line"]["owner_user_id"]
    if not owner:   # pairing mode: only the exact one-time code binds an owner
        pr = db.kv_get("line_pair")
        m = re.fullmatch(r"pair\s+([0-9a-f]{6})", text.lower())
        if pr and m and time.time() - pr["ts"] < PAIR_TTL and hmac.compare_digest(m.group(1), pr["code"]):
            _bind_owner(uid)
            db.kv_set("line_pair", None)
            await reply(token, text_messages("Paired. I will only talk to you. Say hi!"))
        return
    if uid != owner:
        return   # strangers get silence
    m = re.fullmatch(r"(send|cancel)\s+#(\d+)(?:\s+([0-9a-f]{6}))?", text.lower())
    if m:
        did = int(m.group(2))
        res = await (drafts.approve(did, m.group(3), via="line") if m.group(1) == "send" else _cancel(did))
        await reply(token, text_messages("Sent." if res.get("ok") and m.group(1) == "send" else "Cancelled." if res.get("ok") else f"Not done: {res.get('error', '')}"))
        return
    if text.lower() in ("console", "dashboard", "menu"):
        await reply(token, text_messages("Your console: " + console_link()))
        return
    from ..agent import Agent
    before = {d["id"] for d in drafts.pending()}
    res = await Agent().run(text, session="line")
    new = [d["id"] for d in drafts.pending() if d["id"] not in before]
    msgs = text_messages(res.text, draft_buttons(new))
    if not await reply(token, msgs):   # reply token expired (slow model): fall back to a push, within the monthly cap
        await push(owner, msgs)


async def _cancel(did: int) -> dict:
    return drafts.cancel(did)


async def handle_webhook(body: bytes, signature: str) -> int:
    """Returns an HTTP status. 403 on a bad signature, 200 otherwise (LINE retries on errors)."""
    if not verify_signature(body, signature, keystore.get("line.channel_secret") or ""):
        return 403
    try:
        events = json.loads(body).get("events", [])
    except json.JSONDecodeError:
        return 400
    for ev in events:
        try:
            await handle_event(ev)
        except Exception as e:   # one bad event must not break the batch or leak details
            from .. import activity
            activity.finish(activity.start("line", "LINE event failed"), False, type(e).__name__)
    return 200


def register() -> bool:
    cfg = config.load()
    if cfg["line"]["enabled"] and keystore.get("line.channel_token"):
        drafts.register_sender("line", send_text)
        return True
    return False


async def verify_liff_id_token(id_token: str) -> str | None:
    """Returns the LINE user id for a valid LIFF id token, else None."""
    cfg = config.load()
    liff = cfg["line"]["liff_id"]
    if not liff:
        return None
    async with httpx.AsyncClient(timeout=15, transport=TRANSPORT) as c:
        r = await c.post(f"{API}/oauth2/v2.1/verify", data={"id_token": id_token, "client_id": liff.split("-")[0]})
    return r.json().get("sub") if r.status_code == 200 else None


__all__ = ["handle_webhook", "register", "verify_signature", "new_pair_code", "secrets"]
