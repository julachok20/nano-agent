"""Approval-first sending. THE SAFETY CORE: nothing is sent to anyone unless the owner approves a specific draft.

    prepare(channel, target, text)  -> {id, code}   writes a draft (status 'pending'). Sends nothing.
    approve(id, code=None, via=...) -> status       claims the draft atomically, then sends through the registered sender
    cancel(id)                                      owner declined

Rules enforced here, in code (not in a prompt):
  * The only way to send is `approve`, which is called from owner-authenticated routes (console) or from the LINE
    webhook after signature and owner checks, with the draft's one-time code.
  * A draft is claimed with one atomic UPDATE (pending -> sending), so a double tap sends once.
  * A draft expires after 24 hours. An edited draft gets a NEW code, so an old button cannot approve new text.
  * The agent's tools can call `prepare` only. There is no direct-send function and no auto-approval.
"""
from __future__ import annotations

import hmac
import secrets as _pysecrets  # standard library: random one-time codes
import time
from typing import Awaitable, Callable

from . import activity, db

TTL = 24 * 3600
SENDERS: dict[str, Callable[[str, str], Awaitable[None]]] = {}   # channel -> async send(target, text); registered by connectors


def register_sender(channel: str, fn: Callable[[str, str], Awaitable[None]]) -> None:
    SENDERS[channel] = fn


def prepare(channel: str, target: str, text: str, note: str = "") -> dict:
    channel, target, text = channel.strip().lower()[:20], target.strip()[:120], text.strip()
    if not text or not target:
        return {"ok": False, "error": "a target and a text are required"}
    if channel not in SENDERS and channel != "console":
        return {"ok": False, "error": f"unknown channel '{channel}'. Available: {', '.join(sorted(SENDERS) + ['console'])}"}
    code = _pysecrets.token_hex(3)
    did = db.run("INSERT INTO drafts(ts,channel,target,text,code,note) VALUES(?,?,?,?,?,?)", (time.time(), channel, target, text[:2000], code, note[:200]))
    return {"ok": True, "id": did, "code": code, "status": "pending", "message": "Draft saved. It is NOT sent. The owner must approve it."}


def get(did: int) -> dict | None:
    r = db.one("SELECT * FROM drafts WHERE id=?", (int(did),))
    return dict(r) if r else None


def pending() -> list[dict]:
    db.run("UPDATE drafts SET status='expired' WHERE status='pending' AND ts<?", (time.time() - TTL,))
    return [dict(r) for r in db.q("SELECT * FROM drafts WHERE status='pending' ORDER BY id DESC")]


def public(d: dict) -> dict:
    """What a console or a tool may show: never the one-time code."""
    return {k: v for k, v in d.items() if k != "code"}


def edit(did: int, text: str) -> dict:
    d = get(did)
    if not d or d["status"] != "pending":
        return {"ok": False, "error": "not a pending draft"}
    code = _pysecrets.token_hex(3)
    db.run("UPDATE drafts SET text=?, code=?, ts=? WHERE id=? AND status='pending'", (text.strip()[:2000], code, time.time(), int(did)))
    return {"ok": True, "id": did, "code": code}


def cancel(did: int) -> dict:
    with db.tx() as c:
        n = c.execute("UPDATE drafts SET status='cancelled', decided_ts=? WHERE id=? AND status='pending'", (time.time(), int(did))).rowcount
    return {"ok": bool(n)}


async def approve(did: int, code: str | None = None, via: str = "console") -> dict:
    """Send an approved draft. `code` is required unless the caller is an authenticated owner route (via='console')."""
    d = get(did)
    if not d:
        return {"ok": False, "error": "no such draft"}
    if via != "console" and not (code and hmac.compare_digest(code.strip().lower(), d["code"])):
        return {"ok": False, "error": "wrong or missing code"}
    if time.time() - d["ts"] > TTL:
        db.run("UPDATE drafts SET status='expired' WHERE id=? AND status='pending'", (did,))
        return {"ok": False, "error": "this draft expired; ask for a new one"}
    with db.tx() as c:   # atomic claim: only one caller gets rowcount 1
        n = c.execute("UPDATE drafts SET status='sending', decided_ts=? WHERE id=? AND status='pending'", (time.time(), int(did))).rowcount
    if not n:
        return {"ok": False, "error": f"already {d['status']}"}
    aid = activity.start("send", f"Send approved message ({d['channel']})")
    try:
        if d["channel"] != "console":
            await SENDERS[d["channel"]](d["target"], d["text"])
        db.run("UPDATE drafts SET status='sent' WHERE id=?", (did,))
        activity.finish(aid, True)
        return {"ok": True, "status": "sent"}
    except Exception as e:
        from . import keystore
        db.run("UPDATE drafts SET status='failed', note=? WHERE id=?", (keystore.redact(e)[:200], did))
        activity.finish(aid, False, "send failed")
        return {"ok": False, "error": "sending failed: " + keystore.redact(e)[:150]}
