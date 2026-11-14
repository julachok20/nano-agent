"""Tools the assistant uses on itself: skills, preferences and learning, the user model, patch proposals, the sandbox.

Everything here is bounded: preferences go through a fixed schema, skills cannot override rules, patches are only
*proposed* and need the owner's approval in the console. See SECURITY.md.
"""
from __future__ import annotations

import asyncio
import json

from .. import companion, learning, patching, sandbox, skills, usermodel
from . import tool

# ---- skills ----------------------------------------------------------------


@tool("List the skills you have (name and what each is for).")
def skill_list() -> dict:
    return {"skills": [{"name": s["name"], "description": s["description"], "enabled": s["enabled"], "pending_review": s["pending"]} for s in skills.list_skills()]}


@tool("Read a skill's full instructions. Do this before following a skill. A skill is guidance text and can never override your rules.")
def skill_view(name: str) -> dict:
    r = skills.view(name)
    return r if not r.get("ok") else {"ok": True, "name": name, "text": r["text"][:12000], "files": r["files"]}


@tool("Create a reusable skill from a procedure you worked out with the owner (name: lowercase-with-dashes).", safety="write",
      params={"name": "lowercase letters, digits, dashes", "description": "One line: when to use it", "body": "Markdown instructions"})
def skill_create(name: str, description: str, body: str) -> dict:
    return skills.create(name, description, body, origin="ai")


@tool("Improve an existing skill's instructions. The old version is kept and the owner can undo.", safety="write")
def skill_update(name: str, body: str) -> dict:
    return skills.update(name, body, origin="ai")


# ---- preferences and learning ------------------------------------------------

@tool("Change HOW you behave, inside the allowed settings only. Keys: chat.length (short|normal|detailed), chat.tone "
      "(plain|friendly|formal|playful), chat.language (auto|en|th), chat.emoji (none|some), brief.sections, brief.length, brief.time (HH:MM), "
      "brief.days, ui.accent, ui.density, ui.text_size, ui.labels, ui.panels. Use when the owner asks for a style change. Always give a reason.",
      safety="write", params={"setting": "scope.key, e.g. chat.length", "value": "The new value (JSON for lists)", "reason": "Why, in plain words"})
def tune(setting: str, value: str, reason: str) -> dict:
    scope, _, key = setting.partition(".")
    try:
        v = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        v = value
    r = learning.set_prefs(scope, {key: v}, "ai", reason)
    if r["ok"]:
        learning.record_signal("explicit", scope, 1, key)
    return r


@tool("Record that the owner liked (+1) or disliked (-1) something, as a category word (never a name or message text).", safety="write")
def record_feedback(area: str, signal: int, topic: str = "") -> dict:
    return {"ok": learning.record_signal("explicit", area, 1 if signal > 0 else -1, topic)}


@tool("Show what has been learned and changed lately, and the current settings.")
def learning_status() -> dict:
    return {"settings": learning.active_prefs(), "recent": learning.recent_log(10), "traits": usermodel.status()}


@tool("Undo one entry of the learning log (the owner's request).", safety="write")
def learning_undo(log_id: int) -> dict:
    return learning.undo(log_id)


@tool("Change the relationship level when the owner asks: assistant (formal), buddy (friendly), friend (casual).", safety="write")
def companion_level(level: str) -> dict:
    return companion.set_level(level, "owner")


# ---- patches -------------------------------------------------------------------

@tool("Read a plugin file you may patch (plugins/...). Core code and secrets cannot be read.", params={"path": "e.g. plugins/my_tool.py"})
def code_read(path: str) -> dict:
    if not patching.readable(path):
        return {"ok": False, "error": patching.REFUSE}
    t = patching._read(patching.norm_path(path))
    return {"ok": t is not None, "text": (t or "")[:20000], **({} if t is not None else {"error": "no such file"})}


@tool("Propose a new tool or a change to a plugin. `edits` is a JSON list of {path, old?, new}; paths must be under plugins/. Plugin code "
      "may use only json, re, math, datetime and the `tool` decorator. This only SAVES a proposal and tests it; the owner must approve it. "
      "Never say it was applied.", safety="prepare", track="Proposing a code change",
      params={"title": "Short title", "summary": "What it does, in plain words", "edits": "JSON list of {path, old, new}"})
async def propose_patch(title: str, summary: str, edits: str) -> dict:
    try:
        lst = json.loads(edits)
        assert isinstance(lst, list) and all(isinstance(e, dict) for e in lst)
    except Exception:
        return {"ok": False, "error": "edits must be a JSON list of objects"}
    return await asyncio.to_thread(patching.propose, title, summary, lst)


# ---- sandbox ---------------------------------------------------------------------

@tool("Run a short Python snippet in an isolated container with no network (needs Docker; may be switched off). Print results to stdout.",
      safety="write", track="Running code in the sandbox", params={"code": "Python source", "timeout_s": "Max seconds (default 20, max 60)"})
async def run_code(code: str, timeout_s: int = 20) -> dict:
    return await sandbox.run_python(code, timeout_s)
