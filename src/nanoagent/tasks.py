"""Tasks and reminders (local, in nano.db). Times are stored as UTC epoch seconds and shown in the owner's timezone."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from . import config, db


def parse_when(text: str, now: datetime | None = None) -> float:
    """'+30m' '+2h' '+3d', 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', 'HH:MM' (next occurrence). Returns epoch seconds. Raises ValueError."""
    tz = config.tz()
    now = now or datetime.now(tz)
    s = (text or "").strip().lower()
    if not s:
        raise ValueError("empty time")
    m = re.fullmatch(r"\+(\d+)\s*(m|min|h|d)", s)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return (now + timedelta(**{"minutes" if u.startswith("m") else "hours" if u == "h" else "days": n})).timestamp()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        t = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return (t if t > now else t + timedelta(days=1)).timestamp()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                d = d.replace(hour=23, minute=59)
            return d.replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    raise ValueError(f"cannot read the time '{text}'. Use 'YYYY-MM-DD HH:MM', 'HH:MM' or '+30m'.")


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, config.tz()).strftime("%Y-%m-%d %H:%M") if ts else ""


def add(title: str, due: str = "", priority: int = 2) -> dict:
    title = " ".join((title or "").split())[:200]
    if not title:
        return {"ok": False, "error": "a title is required"}
    try:
        due_ts = parse_when(due) if due else 0.0
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    pr = min(3, max(1, int(priority or 2)))
    tid = db.run("INSERT INTO tasks(ts,title,due,priority) VALUES(?,?,?,?)", (time.time(), title, due_ts, pr))
    return {"ok": True, "id": tid, "due": _fmt(due_ts)}


def list_(include_done: bool = False) -> list[dict]:
    rows = db.q("SELECT * FROM tasks" + ("" if include_done else " WHERE done=0") + " ORDER BY done, CASE WHEN due=0 THEN 1 ELSE 0 END, due, priority DESC")
    return [{"id": r["id"], "title": r["title"], "due": _fmt(r["due"]), "priority": r["priority"], "done": bool(r["done"])} for r in rows]


def complete(task_id: int) -> dict:
    r = db.one("SELECT * FROM tasks WHERE id=?", (int(task_id),))
    if not r:
        return {"ok": False, "error": "no such task"}
    db.run("UPDATE tasks SET done=1, done_ts=? WHERE id=?", (time.time(), r["id"]))
    if r["due"]:   # evidence for the user model: how long before the deadline the owner finishes things (no text stored)
        try:
            from . import usermodel
            usermodel.record("reminder_lead", "task_done", f"task:{r['id']}", round((r["due"] - time.time()) / 3600, 1))
        except Exception:
            pass
    return {"ok": True}


def add_reminder(text: str, when: str) -> dict:
    text = " ".join((text or "").split())[:200]
    if not text:
        return {"ok": False, "error": "a text is required"}
    try:
        due = parse_when(when)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    rid = db.run("INSERT INTO reminders(ts,text,due) VALUES(?,?,?)", (time.time(), text, due))
    return {"ok": True, "id": rid, "due": _fmt(due)}


def list_reminders() -> list[dict]:
    return [{"id": r["id"], "text": r["text"], "due": _fmt(r["due"])} for r in db.q("SELECT * FROM reminders WHERE fired=0 ORDER BY due")]


def fire_due() -> list[dict]:
    """Mark due reminders fired and return them (the scheduler notifies the owner)."""
    rows = db.q("SELECT * FROM reminders WHERE fired=0 AND due<=?", (time.time(),))
    for r in rows:
        db.run("UPDATE reminders SET fired=1 WHERE id=?", (r["id"],))
    return [dict(r) for r in rows]
