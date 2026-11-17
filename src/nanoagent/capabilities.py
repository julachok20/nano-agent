"""Capability requests (v0.2 addendum, section 3). The model may ask for a connector; it can never grant one.

Rules enforced here, in code:
  * A request names a connector and actions that exist in REGISTRY. Unknown connectors or actions are refused and logged.
  * Allow and Deny each need the one-time code shown on the owner's card. The code is bound to one request, is used
    once, and expires CODE_TTL seconds after the request. Only owner-authenticated routes can list it.
  * Deny by default: a request with no decision expires and grants nothing.
  * An allow stores a grant (connector, actions, scope). It holds no key and makes no call by itself.
  * REGISTRY is empty in v0.2: no connector is built, so every request is refused until one is added as code.
"""
from __future__ import annotations

import hmac
import secrets
import time

from . import db

CODE_TTL = 15 * 60          # a request, and its code, are valid for 15 minutes; then it expires
SCOPES = ("read", "write")  # "write" means draft-only in v0.2 (section 3.2)
REGISTRY: dict[str, dict] = {}   # connector id -> {"actions": {name: {"mode": "read" | "write"}}}; filled by code only


def _refuse(connector, actions, scope, reason, why: str) -> dict:
    db.run("INSERT INTO capability_requests(ts,connector,actions,scope,reason,code,status,decided_ts) VALUES(?,?,?,?,?,'','refused',?)",
           (time.time(), str(connector)[:60], ",".join(map(str, actions))[:300], str(scope)[:10], str(reason)[:300], time.time()))
    return {"ok": False, "error": why}


def request(connector, actions, scope, reason) -> dict:
    """Record a request. The reason is stored and shown as plain text. Nothing is granted here."""
    actions = [str(a) for a in actions] if isinstance(actions, (list, tuple)) else []
    reason = str(reason or "").strip()
    if not reason or len(reason) > 300:
        return _refuse(connector, actions, scope, reason, "reason is required (max 300 characters)")
    if scope not in SCOPES:
        return _refuse(connector, actions, scope, reason, "scope must be read or write")
    spec = REGISTRY.get(str(connector))
    if not spec:
        return _refuse(connector, actions, scope, reason, "unknown connector")
    table = spec.get("actions", {})
    if not actions or any(a not in table for a in actions):
        return _refuse(connector, actions, scope, reason, "unknown action")
    if scope == "read" and any(table[a].get("mode") != "read" for a in actions):
        return _refuse(connector, actions, scope, reason, "read scope cannot include write actions")
    code = secrets.token_hex(3)
    rid = db.run("INSERT INTO capability_requests(ts,connector,actions,scope,reason,code,status,decided_ts) VALUES(?,?,?,?,?,?,'pending',0)",
                 (time.time(), str(connector), ",".join(actions), scope, reason, code))
    return {"ok": True, "id": rid}


def _expire_old() -> None:
    db.run("UPDATE capability_requests SET status='expired', decided_ts=? WHERE status='pending' AND ts<?",
           (time.time(), time.time() - CODE_TTL))


def pending() -> list[dict]:
    """Owner-only listing. Includes the one-time code for the owner's card; never send this to the model."""
    _expire_old()
    return [dict(r) for r in db.q("SELECT id,ts,connector,actions,scope,reason,code,status FROM capability_requests "
                                  "WHERE status='pending' ORDER BY id DESC")]


def pending_count() -> int:
    _expire_old()
    return len(db.q("SELECT id FROM capability_requests WHERE status='pending'"))


def grants() -> list[dict]:
    return [dict(r) for r in db.q("SELECT id,ts,request_id,connector,actions,scope FROM capability_grants WHERE revoked=0 ORDER BY id DESC")]


def _decide(rid: int, code, to_status: str) -> dict:
    row = db.one("SELECT * FROM capability_requests WHERE id=?", (int(rid),))
    d = dict(row) if row else None
    if not d or d["status"] != "pending":
        return {"ok": False, "error": "not a pending request"}
    if time.time() - d["ts"] > CODE_TTL:
        db.run("UPDATE capability_requests SET status='expired', decided_ts=? WHERE id=? AND status='pending'", (time.time(), int(rid)))
        return {"ok": False, "error": "this request expired; the AI must ask again"}
    if not code or not hmac.compare_digest(str(code).strip().lower(), d["code"]):
        return {"ok": False, "error": "wrong or missing code"}
    with db.tx() as c:   # one atomic claim: a double tap or a reused code decides once
        n = c.execute("UPDATE capability_requests SET status=?, decided_ts=? WHERE id=? AND status='pending'",
                      (to_status, time.time(), int(rid))).rowcount
    if not n:
        return {"ok": False, "error": "already decided"}
    if to_status == "granted":
        db.run("INSERT INTO capability_grants(ts,request_id,connector,actions,scope) VALUES(?,?,?,?,?)",
               (time.time(), int(rid), d["connector"], d["actions"], d["scope"]))
    return {"ok": True, "status": to_status}


def allow(rid: int, code) -> dict:
    return _decide(rid, code, "granted")


def deny(rid: int, code) -> dict:
    return _decide(rid, code, "denied")


def granted(connector: str, action: str) -> bool:
    """For the broker (not built in v0.2): true only for an active grant that names this connector and action."""
    return any(g["connector"] == connector and action in g["actions"].split(",") for g in grants())
