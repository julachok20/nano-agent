"""Owner-managed projects and their milestones, blockers, notes, and decisions."""
from __future__ import annotations

import time
from datetime import date

from . import db

KINDS = {"milestone", "blocker", "note", "decision"}


def _text(value: str, limit: int) -> str:
    return " ".join((value or "").split())[:limit]


def _date(value: str) -> str:
    if not value:
        return ""
    return date.fromisoformat(value).isoformat()


def list_(include_closed: bool = False) -> list[dict]:
    sql = "SELECT * FROM projects" + ("" if include_closed else " WHERE status='active'") + " ORDER BY status, id DESC"
    result = []
    for row in db.q(sql):
        project = dict(row)
        items = [dict(item) for item in db.q("SELECT * FROM project_items WHERE project_id=? ORDER BY id", (row["id"],))]
        project["milestones"] = [item for item in items if item["kind"] == "milestone"]
        project["blockers"] = [item for item in items if item["kind"] == "blocker" and not item["done"]]
        project["recent"] = [item for item in items if item["kind"] in {"note", "decision"}][-5:]
        project["progress"] = {"done": sum(bool(item["done"]) for item in project["milestones"]),
                               "total": len(project["milestones"])}
        result.append(project)
    return result


def create(name: str, goal: str = "", deadline: str = "", next_step: str = "") -> dict:
    name = _text(name, 100)
    if not name:
        return {"ok": False, "error": "a project name is required"}
    try:
        deadline = _date(deadline)
    except ValueError:
        return {"ok": False, "error": "deadline must be YYYY-MM-DD"}
    pid = db.run("INSERT INTO projects(ts,name,goal,deadline,next_step) VALUES(?,?,?,?,?)",
                 (time.time(), name, _text(goal, 500), deadline, _text(next_step, 300)))
    return {"ok": True, "id": pid}


def add_item(pid: int, kind: str, text: str, due: str = "") -> dict:
    if not db.one("SELECT 1 FROM projects WHERE id=? AND status='active'", (pid,)):
        return {"ok": False, "error": "no active project"}
    if kind not in KINDS:
        return {"ok": False, "error": "invalid item kind"}
    text = _text(text, 500)
    if not text:
        return {"ok": False, "error": "text is required"}
    try:
        due = _date(due)
    except ValueError:
        return {"ok": False, "error": "due date must be YYYY-MM-DD"}
    item_id = db.run("INSERT INTO project_items(project_id,ts,kind,text,due) VALUES(?,?,?,?,?)",
                     (pid, time.time(), kind, text, due if kind == "milestone" else ""))
    return {"ok": True, "id": item_id}


def complete_item(pid: int, item_id: int) -> dict:
    row = db.one("SELECT 1 FROM project_items WHERE id=? AND project_id=? AND kind IN ('milestone','blocker')", (item_id, pid))
    if not row:
        return {"ok": False, "error": "no such milestone or blocker"}
    db.run("UPDATE project_items SET done=1, done_ts=? WHERE id=? AND project_id=?", (time.time(), item_id, pid))
    return {"ok": True}


def close(pid: int) -> dict:
    if not db.one("SELECT 1 FROM projects WHERE id=? AND status='active'", (pid,)):
        return {"ok": False, "error": "no active project"}
    db.run("UPDATE projects SET status='closed', closed_ts=? WHERE id=?", (time.time(), pid))
    return {"ok": True}
