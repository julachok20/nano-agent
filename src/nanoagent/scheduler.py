"""The scheduler: replaces cron (and Hermes cron). An asyncio loop inside the gateway process.

Automations are rows in the `automations` table: a built-in job (reminders, outbox, backup, health, brief, weekly review,
cleanup) or an "agent" job that sends a stored prompt to the assistant and notifies the owner with the answer.

Schedules (JSON): {"every_min": 5} | {"daily": "07:30", "days": ["mon", ...]} | {"weekly": "sun 19:00"}
A job that fails is logged to activity and retried at its next slot; it never stops the loop. After the machine sleeps,
a missed job runs once, not once per missed slot.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from . import activity, config, db, outbox, tasks

JOBS: dict[str, Callable[[dict], Awaitable[dict | None]]] = {}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
BUILTIN = [
    ("reminders", "reminders", {"every_min": 1}, 1),
    ("outbox", "outbox", {"every_min": 2}, 1),
    ("health", "health", {"every_min": 15}, 1),
    ("backup", "backup", {"daily": "03:30"}, 1),
    ("cleanup", "cleanup", {"daily": "04:00"}, 1),
    ("learning", "learning", {"daily": "04:30"}, 1),
    ("weekly_review", "weekly_review", {"weekly": "sun 19:00"}, 1),
    ("brief", "brief", {"daily": "07:30"}, 0),
]


def job(name: str):
    def deco(fn):
        JOBS[name] = fn
        return fn
    return deco


def compute_next(schedule: dict, after: float, tz=None) -> float:
    tz = tz or config.tz()
    if "every_min" in schedule:
        return after + max(1, int(schedule["every_min"])) * 60
    base = datetime.fromtimestamp(after, tz)
    if "daily" in schedule:
        hh, mm = map(int, schedule["daily"].split(":"))
        days = schedule.get("days") or list(DAYS)
    else:
        d, t = schedule["weekly"].split()
        hh, mm = map(int, t.split(":"))
        days = [d[:3].lower()]
    for add in range(0, 9):
        cand = (base + timedelta(days=add)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand.timestamp() > after and DAYS[cand.weekday()] in days:
            return cand.timestamp()
    return after + 86400


def valid_schedule(s: dict) -> bool:
    try:
        compute_next(s, time.time())
        return True
    except Exception:
        return False


def ensure_builtin() -> None:
    now = time.time()
    for name, jobname, sched, enabled in BUILTIN:
        if not db.one("SELECT 1 FROM automations WHERE name=?", (name,)):
            db.run("INSERT INTO automations(name,job,schedule,enabled,next_run,builtin) VALUES(?,?,?,?,?,1)",
                   (name, jobname, json.dumps(sched), enabled, compute_next(sched, now)))
    sync_brief_schedule()


def sync_brief_schedule() -> None:
    from . import learning
    sched = {"daily": learning.get_pref("brief", "time"), "days": learning.get_pref("brief", "days")}
    db.run("UPDATE automations SET schedule=?, next_run=? WHERE name='brief'", (json.dumps(sched), compute_next(sched, time.time())))


def list_automations() -> list[dict]:
    return [{**dict(r), "schedule": json.loads(r["schedule"])} for r in db.q("SELECT * FROM automations ORDER BY builtin DESC, id")]


def create(name: str, prompt: str, schedule: dict) -> dict:
    name = " ".join(name.split())[:60]
    if not name or not prompt.strip():
        return {"ok": False, "error": "a name and a prompt are required"}
    if not valid_schedule(schedule):
        return {"ok": False, "error": 'schedule must be {"every_min": N}, {"daily": "HH:MM"} or {"weekly": "sun 19:00"}'}
    if "every_min" in schedule and int(schedule["every_min"]) < 5:
        return {"ok": False, "error": "an AI automation cannot run more often than every 5 minutes"}
    if db.one("SELECT 1 FROM automations WHERE name=?", (name,)):
        return {"ok": False, "error": "an automation with that name exists"}
    aid = db.run("INSERT INTO automations(name,job,prompt,schedule,enabled,next_run) VALUES(?,?,?,?,1,?)", (name, "agent", prompt[:2000], json.dumps(schedule), compute_next(schedule, time.time())))
    return {"ok": True, "id": aid}


def set_enabled(aid: int, enabled: bool) -> dict:
    db.run("UPDATE automations SET enabled=?, next_run=? WHERE id=?", (1 if enabled else 0, time.time() + 60, int(aid)))
    return {"ok": True}


def delete(aid: int) -> dict:
    db.run("DELETE FROM automations WHERE id=? AND builtin=0", (int(aid),))
    return {"ok": True}


async def run_job(row) -> str:
    fn = JOBS.get(row["job"])
    if not fn:
        return "unknown job"
    aid = activity.start("automation", f"Automation: {row['name']}") if row["job"] not in ("reminders", "outbox") else 0
    try:
        await asyncio.wait_for(fn(dict(row)), 300)
        activity.finish(aid, True)
        return "ok"
    except Exception as e:
        activity.finish(aid, False, type(e).__name__)
        return f"failed: {type(e).__name__}"


async def run_now(aid: int) -> dict:
    row = db.one("SELECT * FROM automations WHERE id=?", (int(aid),))
    if not row:
        return {"ok": False, "error": "no such automation"}
    st = await run_job(row)
    db.run("UPDATE automations SET last_run=?, last_status=? WHERE id=?", (time.time(), st, row["id"]))
    return {"ok": st == "ok", "status": st}


async def tick() -> int:
    db.kv_set("sched_heartbeat", time.time())
    now = time.time()
    due = db.q("SELECT * FROM automations WHERE enabled=1 AND next_run<=?", (now,))
    for row in due:
        sched = json.loads(row["schedule"])
        db.run("UPDATE automations SET next_run=? WHERE id=?", (compute_next(sched, now), row["id"]))   # advance first: a crash cannot loop
        st = await run_job(row)
        db.run("UPDATE automations SET last_run=?, last_status=? WHERE id=?", (time.time(), st, row["id"]))
    return len(due)


async def run_forever(stop: asyncio.Event, every: float = 20.0) -> None:
    ensure_builtin()
    while not stop.is_set():
        try:
            await tick()
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), every)
        except asyncio.TimeoutError:
            pass


# ---- built-in jobs ------------------------------------------------------------

@job("reminders")
async def _reminders(_row: dict) -> None:
    for r in tasks.fire_due():
        outbox.notify_owner("Reminder: " + r["text"], "reminder")


@job("outbox")
async def _outbox(_row: dict) -> None:
    await outbox.flush()


@job("health")
async def _health(_row: dict) -> None:
    from . import health
    await health.run_checks_and_alert()


@job("backup")
async def _backup(_row: dict) -> None:
    from . import health
    r = await asyncio.to_thread(health.backup_db)
    if not r["ok"]:
        outbox.notify_owner("Backup problem: the restore check failed.", "health")


@job("cleanup")
async def _cleanup(_row: dict) -> None:
    from . import skills
    skills.purge_trash()
    db.run("DELETE FROM messages WHERE ts<?", (time.time() - 30 * 86400,))
    db.run("DELETE FROM outbox WHERE ts<?", (time.time() - 30 * 86400,))
    db.run("DELETE FROM activity WHERE ts<?", (time.time() - 3 * 86400,))


@job("learning")
async def _learning(_row: dict) -> None:
    from . import companion, usermodel
    usermodel.reflect()
    companion.maybe_promote()


@job("weekly_review")
async def _weekly(_row: dict) -> None:
    from . import learning
    if config.load()["learning"]["enabled"]:
        await learning.weekly_review()


def build_brief() -> str:
    from . import drafts, learning
    secs = learning.get_pref("brief", "sections")
    short = learning.get_pref("brief", "length") == "short"
    lim = 3 if short else 8
    lines = ["Good morning." if config.load()["general"]["language"] == "en" else "สวัสดีตอนเช้า"]
    if "tasks" in secs:
        ts = tasks.list_(False)[:lim]
        lines.append("Tasks: " + ("; ".join(f"{t['title']}" + (f" ({t['due']})" if t["due"] else "") for t in ts) if ts else "none open"))
    if "reminders" in secs:
        rs = tasks.list_reminders()[:lim]
        lines.append("Reminders: " + ("; ".join(f"{r['text']} ({r['due']})" for r in rs) if rs else "none"))
    if "drafts" in secs:
        n = len(drafts.pending())
        lines.append(f"Drafts waiting for your approval: {n}")
    if "activity" in secs:
        lines.append(f"Background work now: {activity.running_count()}")
    return "\n".join(lines)


@job("brief")
async def _brief(_row: dict) -> None:
    outbox.notify_owner(build_brief(), "brief")


@job("sandbox")
async def _sandbox(row: dict) -> None:
    """N8: a script the agent wrote runs inside the sandbox workspace (retry and owner notice live in sandbox_ws)."""
    from . import sandbox_ws
    await asyncio.to_thread(sandbox_ws.run_scheduled, row)


@job("agent")
async def _agent(row: dict) -> None:
    from .agent import Agent
    res = await Agent().run(row["prompt"], session=f"automation:{row['id']}")
    if not res.error:
        outbox.notify_owner(f"{row['name']}: {res.text}"[:1000], "automation")
