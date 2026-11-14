"""The user model: structured, evidence-backed guesses about the owner that the owner can inspect, correct and delete.

An evidence record is (trait, ts, kind, ref, value): the signal type, when, the id of the source row (`task:12`,
`signal:7`) and a small number. NEVER chat text: `record` rejects any ref that is not `<word>:<number>`.
A learned trait is ACTED ON only with at least N evidence records in the last 60 days AND confidence >= 0.6; below that it
is shown as a guess and ignored. An owner correction has confidence 1.0 and is never overwritten by learning. A deleted
trait (and its evidence) is not learned again until the owner corrects it.
"""
from __future__ import annotations

import re
import time

from . import db

WINDOW = 60 * 86400
MIN_CONF = 0.6
REF_RE = re.compile(r"^[a-z_]{2,20}:\d{1,12}$")
# trait -> evidence needed before it is acted on
TRAITS = {"answer_length": 3, "reminder_lead": 4, "active_hours": 10, "language": 3}


def record(trait: str, kind: str, ref: str, value: float = 0.0) -> bool:
    if trait not in TRAITS or not REF_RE.match(ref or ""):
        return False
    t = db.one("SELECT deleted FROM traits WHERE name=?", (trait,))
    if t and t["deleted"]:
        return False
    db.run("INSERT INTO trait_evidence(trait,ts,kind,ref,value) VALUES(?,?,?,?,?)", (trait, time.time(), kind[:20], ref, float(value)))
    return True


def _evidence(trait: str) -> list:
    return db.q("SELECT * FROM trait_evidence WHERE trait=? AND ts>? ORDER BY ts", (trait, time.time() - WINDOW))


def reflect() -> list[str]:
    """Recompute learned traits from evidence. Skips owner-set and deleted traits. Returns the names that changed."""
    changed = []
    for name in TRAITS:
        cur = db.one("SELECT * FROM traits WHERE name=?", (name,))
        if cur and (cur["source"] == "owner" or cur["deleted"]):
            continue
        ev = _evidence(name)
        n = len(ev)
        if n == 0:
            continue
        if name == "reminder_lead":
            v = f"{sorted(e['value'] for e in ev)[n // 2]:.0f}h before the deadline"
        elif name == "answer_length":
            up = sum(1 for e in ev if e["value"] > 0)
            v = "longer" if up > n - up else "shorter"
        elif name == "active_hours":
            hrs = [int(e["value"]) for e in ev]
            top = max(range(24), key=lambda h: sum(1 for x in hrs if abs(x - h) <= 1))
            v = f"{top:02d}:00 +-1h"
        else:
            vals = [int(e["value"]) for e in ev]
            v = f"code:{max(set(vals), key=vals.count)}"
        conf = round(min(0.95, 0.3 + 0.1 * n), 2)
        if not cur or cur["value"] != v or abs(cur["confidence"] - conf) > 0.01:
            db.run("INSERT INTO traits(name,value,confidence,source,reason,ts) VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
                   "value=excluded.value, confidence=excluded.confidence, source=excluded.source, reason=excluded.reason, ts=excluded.ts",
                   (name, v, conf, "learned", f"{n} evidence records in the last 60 days", time.time()))
            from . import learning
            learning.log("trait", f"{name}: {v}", f"learned from {n} records", "learned", {"action": "trait_restore", "name": name, "value": cur["value"] if cur else None})
            changed.append(name)
    return changed


def trusted(name: str) -> str | None:
    """The value of a trait if it may be ACTED on, else None."""
    t = db.one("SELECT * FROM traits WHERE name=? AND deleted=0", (name,))
    if not t:
        return None
    if t["source"] == "owner":
        return t["value"]
    n = len(_evidence(name))
    return t["value"] if n >= TRAITS.get(name, 99) and t["confidence"] >= MIN_CONF else None


def status() -> list[dict]:
    out = []
    for r in db.q("SELECT * FROM traits WHERE deleted=0 ORDER BY name"):
        n = len(_evidence(r["name"]))
        used = r["source"] == "owner" or (n >= TRAITS.get(r["name"], 99) and r["confidence"] >= MIN_CONF)
        out.append({"name": r["name"], "value": r["value"], "confidence": r["confidence"], "source": r["source"], "reason": r["reason"],
                    "evidence": n, "needed": TRAITS.get(r["name"], 0), "used": used})
    return out


def evidence(name: str) -> list[dict]:
    return [{"id": e["id"], "ts": e["ts"], "kind": e["kind"], "ref": e["ref"], "value": e["value"]} for e in _evidence(name)]


def delete_evidence(eid: int) -> dict:
    db.run("DELETE FROM trait_evidence WHERE id=?", (int(eid),))
    return {"ok": True}


def correct(name: str, value: str) -> dict:
    if name not in TRAITS:
        return {"ok": False, "error": "unknown trait"}
    value = " ".join(str(value).split())[:80]
    db.run("INSERT INTO traits(name,value,confidence,source,reason,ts,deleted) VALUES(?,?,?,?,?,?,0) ON CONFLICT(name) DO UPDATE SET "
           "value=excluded.value, confidence=1.0, source='owner', reason='set by the owner', ts=excluded.ts, deleted=0", (name, value, 1.0, "owner", "set by the owner", time.time()))
    return {"ok": True}


def delete(name: str) -> dict:
    """Forget the trait and its evidence; it will not be learned again until the owner sets it."""
    db.run("DELETE FROM trait_evidence WHERE trait=?", (name,))
    db.run("INSERT INTO traits(name,value,confidence,source,reason,ts,deleted) VALUES(?,?,?,?,?,?,1) ON CONFLICT(name) DO UPDATE SET deleted=1", (name, "", 0, "owner", "deleted", time.time()))
    return {"ok": True}


def restore(name: str, value: str | None) -> dict:
    if value is None:
        return delete(name)
    db.run("UPDATE traits SET value=?, ts=? WHERE name=?", (value, time.time(), name))
    return {"ok": True}
