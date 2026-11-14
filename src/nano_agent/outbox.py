"""Messages from the assistant to its owner (reminders, briefs, results). Not for messages to other people: those are
drafts and need approval (see drafts.py).

Every notification is shown in the console (bell). When LINE is enabled it is also queued for LINE and pushed by
`flush()`, within a monthly push cap (the free LINE plan counts pushes), so the owner is never surprised by a bill.
"""
from __future__ import annotations

import json
import time
from datetime import datetime

from . import config, db, drafts

RATE_PER_HOUR = 20
DEFAULT_MONTHLY_CAP = 200


def notify_owner(text: str, kind: str = "notify") -> dict:
    text = " ".join((text or "").split())[:1000]
    if not text:
        return {"ok": False, "error": "empty"}
    if (db.one("SELECT COUNT(*) c FROM outbox WHERE kind=? AND ts>?", (kind, time.time() - 3600)) or {"c": 0})["c"] >= RATE_PER_HOUR:
        return {"ok": False, "error": "notification rate limit reached; try later"}
    now = time.time()
    db.run("INSERT INTO outbox(ts,channel,target,kind,payload,status,sent_ts) VALUES(?,?,?,?,?,?,?)", (now, "console", "owner", kind, json.dumps({"text": text}), "sent", now))
    cfg = config.load()
    if cfg["line"]["enabled"] and cfg["line"]["owner_user_id"]:
        db.run("INSERT INTO outbox(ts,channel,target,kind,payload) VALUES(?,?,?,?,?)", (now, "line", cfg["line"]["owner_user_id"], kind, json.dumps({"text": text})))
    return {"ok": True}


def feed(limit: int = 30) -> list[dict]:
    out = []
    for r in db.q("SELECT * FROM outbox WHERE channel='console' ORDER BY id DESC LIMIT ?", (limit,)):
        out.append({"id": r["id"], "ts": r["ts"], "kind": r["kind"], "text": json.loads(r["payload"]).get("text", "")})
    return out


def _month_key() -> str:
    return "line_push_" + datetime.now().strftime("%Y%m")


async def flush() -> dict:
    """Push queued LINE notifications. Stops at the monthly cap and says so once."""
    sender = drafts.SENDERS.get("line")
    if not sender:
        return {"sent": 0}
    cap = int(db.kv_get("line_push_cap", DEFAULT_MONTHLY_CAP))
    used = int(db.kv_get(_month_key(), 0))
    sent = 0
    for r in db.q("SELECT * FROM outbox WHERE channel='line' AND status='pending' ORDER BY id LIMIT 20"):
        if used >= cap:
            db.run("UPDATE outbox SET status='skipped' WHERE id=?", (r["id"],))
            continue
        try:
            await sender(r["target"], json.loads(r["payload"]).get("text", ""))
            db.run("UPDATE outbox SET status='sent', sent_ts=? WHERE id=?", (time.time(), r["id"]))
            used += 1
            sent += 1
        except Exception:
            db.run("UPDATE outbox SET status='failed' WHERE id=?", (r["id"],))
    db.kv_set(_month_key(), used)
    return {"sent": sent, "used_this_month": used, "cap": cap}
