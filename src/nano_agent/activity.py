"""Background-work visibility: what the assistant is doing now and what it did lately (shown live in the console).

    start(kind, title) -> id          a task begins
    step(id, text)                    one more line of what it is doing
    finish(id, ok, text)              it ended
    track(kind, title)                `with activity.track(...) as t:` start, t.step(text), t.result(...), finish (failed if it raises)
    running_count() / recent(limit)   for the "AI is working" pill and the activity page

Details never hold chat message text on purpose (callers pass titles and step labels, not content) and anything that
looks like a secret is masked. Rows older than 3 days are removed. Nothing here leaves the machine.
"""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager

from . import db

KEEP = 3 * 86400
STALE = 1200   # a task still "running" after 20 minutes is shown as failed
_SECRET = re.compile(r"(bearer\s+|token[=:]\s*|key[=:]\s*|secret[=:]\s*|password[=:]\s*)\S+", re.I)


def _clean(text, limit: int) -> str:
    return _SECRET.sub(r"\1***", str(text).strip())[:limit]


def start(kind: str, title: str) -> int:
    if os.environ.get("NANO_ACTIVITY_OFF"):
        return 0
    try:
        db.run("DELETE FROM activity WHERE ts<?", (time.time() - KEEP,))
        return db.run("INSERT INTO activity(ts,kind,title) VALUES(?,?,?)", (time.time(), kind, _clean(title, 120)))
    except Exception:
        return 0


def step(aid: int, text: str) -> None:
    if not aid:
        return
    try:
        r = db.one("SELECT steps FROM activity WHERE id=?", (aid,))
        steps = json.loads(r["steps"]) if r else []
        steps.append({"t": round(time.time(), 1), "text": _clean(text, 200)})
        db.run("UPDATE activity SET steps=? WHERE id=?", (json.dumps(steps[-40:]), aid))
    except Exception:
        pass


def finish(aid: int, ok: bool = True, text: str = "") -> None:
    if not aid:
        return
    try:
        db.run("UPDATE activity SET status=?, ended=?, result=? WHERE id=? AND status='running'",
               ("done" if ok else "failed", time.time(), _clean(text, 400), aid))
    except Exception:
        pass


class _Task:
    def __init__(self, aid: int):
        self.id = aid
        self._res = None

    def step(self, text: str) -> None:
        step(self.id, text)

    def result(self, value):
        """Record a tool result: {"ok": False} or {"error": ...} marks the task failed. Returns the value unchanged."""
        self._res = value
        return value


@contextmanager
def track(kind: str, title: str):
    t = _Task(start(kind, title))
    try:
        yield t
    except Exception as e:
        finish(t.id, False, f"{type(e).__name__}")
        raise
    else:
        bad = isinstance(t._res, dict) and (t._res.get("ok") is False or "error" in t._res)
        finish(t.id, not bad, (t._res.get("error", "") if bad and isinstance(t._res, dict) else ""))


def _expire() -> None:
    db.run("UPDATE activity SET status='failed', ended=ts+?, result='timed out' WHERE status='running' AND ts<?", (STALE, time.time() - STALE))


def running_count() -> int:
    _expire()
    r = db.one("SELECT COUNT(*) c FROM activity WHERE status='running'")
    return int(r["c"]) if r else 0


def _row(r) -> dict:
    d = dict(r)
    d["steps"] = json.loads(d.get("steps") or "[]")
    d["secs"] = round((d["ended"] or time.time()) - d["ts"], 1)
    return d


def recent(limit: int = 30) -> dict:
    _expire()
    run = [_row(r) for r in db.q("SELECT * FROM activity WHERE status='running' ORDER BY ts DESC")]
    done = [_row(r) for r in db.q("SELECT * FROM activity WHERE status!='running' ORDER BY ended DESC LIMIT ?", (limit,))]
    return {"running": run, "done": done}


def get(aid: int) -> dict | None:
    r = db.one("SELECT * FROM activity WHERE id=?", (aid,))
    return _row(r) if r else None
