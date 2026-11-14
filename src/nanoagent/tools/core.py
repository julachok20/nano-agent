"""Built-in tools: time, memory, tasks, reminders, drafts (approval-first), notifications, dashboard summary.

None of these can send a message to another person. `prepare_message` only writes a draft the owner must approve.
"""
from __future__ import annotations

from datetime import datetime

from .. import activity, config, drafts, memory, outbox, tasks
from . import tool


def _cfg() -> dict:
    return config.load()


@tool("Get the current date, time and weekday in the owner's timezone.")
def get_time() -> dict:
    now = datetime.now(config.tz(_cfg()))
    return {"iso": now.isoformat(timespec="minutes"), "weekday": now.strftime("%A"), "timezone": str(now.tzinfo)}


@tool("Remember a short durable fact about the owner (preference, routine, relationship, goal). Use for things the owner states "
      "about themselves. Never store passwords, keys or ID numbers.", safety="write",
      params={"text": "One short sentence.", "kind": "fact | rule | lesson"})
def remember(text: str, kind: str = "fact") -> dict:
    return memory.remember(text, kind, source="agent")


@tool("Search what you remember about the owner.", params={"query": "Words to look for."})
def recall(query: str) -> dict:
    return {"items": [{"id": r["id"], "kind": r["kind"], "text": r["text"]} for r in memory.recall(query)]}


@tool("Forget one remembered item by id (get ids from recall).", safety="write")
def forget(memory_id: int) -> dict:
    return {"ok": memory.forget(memory_id)}


@tool("Add a to-do task. `due` is optional: 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM', '+2h' or '+3d'.", safety="write")
def add_task(title: str, due: str = "", priority: int = 2) -> dict:
    return tasks.add(title, due, priority)


@tool("List open tasks (soonest due first).")
def list_tasks(include_done: bool = False) -> dict:
    return {"tasks": tasks.list_(include_done)}


@tool("Mark a task done.", safety="write")
def complete_task(task_id: int) -> dict:
    return tasks.complete(task_id)


@tool("Set a reminder. `when`: 'YYYY-MM-DD HH:MM', 'HH:MM' (next time it is that o'clock), '+30m', '+2h' or '+1d'. The owner gets a notification.",
      safety="write")
def set_reminder(text: str, when: str) -> dict:
    return tasks.add_reminder(text, when)


@tool("List pending reminders.")
def list_reminders() -> dict:
    return {"reminders": tasks.list_reminders()}


@tool("Prepare a message to someone else for the owner to approve. NOTHING is sent: this only saves a draft and the owner must "
      "approve it. channel is 'line' (target = a LINE user id) or 'console'. Never claim a message was sent after calling this.",
      safety="prepare", params={"channel": "line | console", "target": "Recipient id or name", "text": "The exact message text"})
def prepare_message(channel: str, target: str, text: str) -> dict:
    r = drafts.prepare(channel, target, text, note="prepared by the agent")
    return {k: v for k, v in r.items() if k != "code"}   # the one-time code never reaches the model


@tool("List drafts that wait for the owner's approval.")
def list_drafts() -> dict:
    return {"drafts": [drafts.public(d) for d in drafts.pending()]}


@tool("Change the text of a pending draft (it needs approval again).", safety="prepare")
def edit_draft(draft_id: int, text: str) -> dict:
    r = drafts.edit(draft_id, text)
    return {"ok": r["ok"], **({"error": r["error"]} if not r["ok"] else {"message": "Updated. Still waiting for approval."})}


@tool("Cancel a pending draft.", safety="write")
def cancel_draft(draft_id: int) -> dict:
    return drafts.cancel(draft_id)


@tool("Send the owner a short notification (console bell and LINE if enabled). Rate limited. Use for reminders and results, not chatter.",
      safety="write")
def notify_owner(text: str) -> dict:
    return outbox.notify_owner(text)


@tool("Read a summary of the dashboard: open tasks, reminders, memory counts, drafts waiting, background work.")
def read_dashboard() -> dict:
    return {
        "open_tasks": len(tasks.list_(False)),
        "reminders_pending": len(tasks.list_reminders()),
        "drafts_waiting": len(drafts.pending()),
        "memory": memory.overview(),
        "background_running": activity.running_count(),
        "providers": sorted((_cfg().get("providers") or {}).keys()),
    }


@tool("Say where the owner can open the web console (the link carries no secret).")
def show_console() -> dict:
    g = _cfg()["gateway"]
    base = g.get("public_url") or f"http://{g['host']}:{g['port']}"
    return {"url": base.rstrip("/") + "/console", "note": "The owner opens it with their own access token."}
