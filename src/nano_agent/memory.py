"""What the assistant knows about the owner: short facts and rules, each with its source. Stored locally only.

Kinds: fact (about the owner), rule (how to behave), lesson (a correction). Never raw chat text, never secrets:
`remember` refuses anything that looks like a key or a password. The owner can list and delete everything
(console > Memory). `recall` ranks by 3-character overlap so it works for Thai (no word spaces) as well as English.
"""
from __future__ import annotations

import re
import time

from . import db
from . import keystore as secrets

KINDS = ("fact", "rule", "lesson")
MAX_LEN = 300
_SECRETISH = re.compile(r"(password|passcode|pin\b|otp|รหัสผ่าน|รหัส\s*otp|เลขบัตร|credit card|card number|ssn\b)", re.I)


def _grams(s: str) -> set[str]:
    s = re.sub(r"\s+", " ", s.lower())
    return {s[i:i + 3] for i in range(max(1, len(s) - 2))}


def remember(text: str, kind: str = "fact", source: str = "owner") -> dict:
    text = " ".join((text or "").split())[:MAX_LEN]
    if not text:
        return {"ok": False, "error": "empty"}
    if kind not in KINDS and not kind.startswith("profile:"):
        kind = "fact"
    if secrets.redact(text) != text or _SECRETISH.search(text):
        return {"ok": False, "error": "refused: that looks like a secret or a sensitive number, so it is not stored"}
    dup = db.one("SELECT id FROM memory WHERE kind=? AND lower(text)=lower(?)", (kind, text))
    if dup:
        return {"ok": True, "id": dup["id"], "duplicate": True}
    return {"ok": True, "id": db.run("INSERT INTO memory(ts,kind,text,source) VALUES(?,?,?,?)", (time.time(), kind, text, source[:40]))}


def forget(mem_id: int) -> bool:
    db.run("DELETE FROM memory WHERE id=?", (int(mem_id),))
    return True


def all_items(kind: str | None = None) -> list[dict]:
    rows = db.q("SELECT * FROM memory WHERE kind=? ORDER BY id DESC", (kind,)) if kind else db.q("SELECT * FROM memory ORDER BY id DESC")
    return [dict(r) for r in rows]


def recall(query: str, limit: int = 6) -> list[dict]:
    q = _grams(query)
    scored = []
    for r in db.q("SELECT * FROM memory"):
        g = _grams(r["text"])
        score = len(q & g) / max(1, len(q))
        if score > 0.12:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def facts_text(limit: int = 30) -> str:
    rows = db.q("SELECT kind,text FROM memory ORDER BY id DESC LIMIT ?", (limit,))
    return "\n".join(f"- ({r['kind']}) {r['text']}" for r in rows)


def overview() -> dict:
    out = {k: 0 for k in KINDS}
    for r in db.q("SELECT kind, COUNT(*) c FROM memory GROUP BY kind"):
        out[r["kind"]] = r["c"]
    return out
