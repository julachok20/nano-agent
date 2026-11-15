"""Bounded self-tuning with an audit trail. The assistant may adapt HOW it behaves inside a fixed schema; it may never
change WHAT it is allowed to do. Every change has a reason and an undo, and the owner can see and reverse all of it.

    set_pref(scope, key, value, source, reason)   validated against SCHEMA (all or nothing), logged, undoable
    log(kind, title, reason, source, undo)        one line on the "What I learned" page
    undo(log_id)                                  reverses a preference, skill or patch change
    record_signal(...)                            thumbs and explicit feedback (never chat text, never chat names)
    weekly_review()                               a tool-less model call over the week's numbers proposes at most 3 changes

No model weights are trained. "Learning" here means structured, inspectable preferences plus an evidence-backed user
model (usermodel.py). A stored value that stops matching the schema is ignored, never applied.
"""
from __future__ import annotations

import json
import re
import time

from . import config, db

ACCENTS = ("cyan", "violet", "green", "orange", "rose", "blue")
PANELS = ("work", "tasks", "memory", "drafts", "notifications", "system")
BRIEF_SECTIONS = ("tasks", "reminders", "drafts", "activity")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# scope.key -> (type, allowed)   type: enum | int | enumlist | time | days
SCHEMA: dict[str, tuple[str, object]] = {
    "chat.length": ("enum", ("short", "normal", "detailed")),
    "chat.tone": ("enum", ("plain", "friendly", "formal", "playful")),
    "chat.language": ("enum", ("auto", "en", "th")),
    "chat.emoji": ("enum", ("none", "some")),
    "brief.sections": ("enumlist", BRIEF_SECTIONS),
    "brief.length": ("enum", ("short", "normal")),
    "brief.time": ("time", None),
    "brief.days": ("days", None),
    "ui.accent": ("enum", ACCENTS),
    "ui.theme": ("enum", ("spark", "black", "minimal")),
    "ui.density": ("enum", ("compact", "normal", "roomy")),
    "ui.text_size": ("enum", ("s", "m", "l", "xl")),
    "ui.labels": ("enum", ("short", "friendly")),
    "ui.panels": ("enumlist", PANELS),
}
DEFAULTS = {"chat.length": "normal", "chat.tone": "friendly", "chat.language": "auto", "chat.emoji": "none",
            "brief.sections": ["tasks", "reminders", "drafts"], "brief.length": "short", "brief.time": "07:30",
            "brief.days": list(WEEKDAYS), "ui.accent": "cyan", "ui.theme": "spark", "ui.density": "normal", "ui.text_size": "m",
            "ui.labels": "friendly", "ui.panels": list(PANELS)}
AI_FORBIDDEN_SCOPES = ("ui",)   # the weekly review never restyles the console


def norm(scope: str, key: str, value):
    """Return the cleaned value, or raise ValueError. Only values inside the schema pass."""
    spec = SCHEMA.get(f"{scope}.{key}")
    if not spec:
        raise ValueError(f"unknown setting {scope}.{key}")
    kind, allowed = spec
    if kind == "enum":
        if value not in allowed:  # type: ignore[operator]
            raise ValueError(f"{scope}.{key} must be one of {', '.join(allowed)}")  # type: ignore[arg-type]
        return value
    if kind == "enumlist":
        if not isinstance(value, list) or not value or any(v not in allowed for v in value):  # type: ignore[operator]
            raise ValueError(f"{scope}.{key} must be a non-empty list of: {', '.join(allowed)}")  # type: ignore[arg-type]
        return list(dict.fromkeys(value))
    if kind == "time":
        if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("time must look like 07:30")
        return value
    if kind == "days":
        if not isinstance(value, list) or not value or any(v not in WEEKDAYS for v in value):
            raise ValueError("days must be a list of: " + ", ".join(WEEKDAYS))
        return list(dict.fromkeys(value))
    raise ValueError("bad schema")  # pragma: no cover


def log(kind: str, title: str, reason: str, source: str, undo: dict | None = None) -> int:
    return db.run("INSERT INTO learning_log(ts,kind,title,reason,source,undo) VALUES(?,?,?,?,?,?)",
                  (time.time(), kind, title[:200], (reason or "")[:300], source, json.dumps(undo or {})))


def get_pref(scope: str, key: str):
    r = db.one("SELECT value FROM preferences WHERE scope=? AND key=? AND status='active'", (scope, key))
    if r:
        try:
            return norm(scope, key, json.loads(r["value"]))
        except (ValueError, json.JSONDecodeError):
            pass   # a stored value that no longer fits the schema is ignored
    return DEFAULTS.get(f"{scope}.{key}")


def set_prefs(scope: str, changes: dict, source: str = "owner", reason: str = "", confidence: float = 1.0) -> dict:
    """Validate everything first; apply all or nothing."""
    try:
        clean = {k: norm(scope, k, v) for k, v in changes.items()}
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not clean:
        return {"ok": False, "error": "nothing to change"}
    for k, v in clean.items():
        old = db.one("SELECT id, value FROM preferences WHERE scope=? AND key=? AND status='active'", (scope, k))
        prev = old["value"] if old else json.dumps(DEFAULTS.get(f"{scope}.{k}"))
        if old:
            db.run("UPDATE preferences SET status='undone' WHERE id=?", (old["id"],))
        pid = db.run("INSERT INTO preferences(ts,scope,key,value,source,confidence,reason,prev) VALUES(?,?,?,?,?,?,?,?)",
                     (time.time(), scope, k, json.dumps(v), source, confidence, reason[:300], prev))
        log("preference", f"{scope}.{k} = {v}", reason, source, {"action": "pref_restore", "pref_id": pid})
        _effects(scope, k, v)
    return {"ok": True, "applied": clean}


def _effects(scope: str, key: str, value) -> None:
    if scope == "brief" and key in ("time", "days"):
        try:
            from . import scheduler
            scheduler.sync_brief_schedule()
        except Exception:
            pass


def undo(log_id: int) -> dict:
    r = db.one("SELECT * FROM learning_log WHERE id=?", (int(log_id),))
    if not r or r["status"] != "done":
        return {"ok": False, "error": "nothing to undo"}
    u = json.loads(r["undo"] or "{}")
    act = u.get("action")
    res = {"ok": False, "error": "this change cannot be undone automatically"}
    if act == "pref_restore":
        p = db.one("SELECT * FROM preferences WHERE id=?", (u["pref_id"],))
        if p:
            db.run("UPDATE preferences SET status='undone' WHERE id=?", (p["id"],))
            try:
                prev = json.loads(p["prev"])
                if prev is not None and prev != DEFAULTS.get(f"{p['scope']}.{p['key']}"):
                    db.run("INSERT INTO preferences(ts,scope,key,value,source,reason) VALUES(?,?,?,?,?,?)", (time.time(), p["scope"], p["key"], p["prev"], "undo", "undo"))
            except json.JSONDecodeError:
                pass
            _effects(p["scope"], p["key"], None)
            res = {"ok": True}
    elif act in ("skill_delete", "skill_restore", "skill_undelete"):
        from . import skills
        res = {"skill_delete": lambda: skills.delete(u["name"], "undo"), "skill_restore": lambda: skills.restore_last(u["name"]),
               "skill_undelete": lambda: skills.undelete(u["name"], u["trash"])}[act]()
    elif act == "patch_undo":
        from . import patching
        res = patching.undo(u["patch_id"])
    elif act == "level_restore":
        from . import companion
        res = companion.set_level(u["level"], "undo")
    elif act == "trait_restore":
        from . import usermodel
        res = usermodel.restore(u["name"], u.get("value"))
    if res.get("ok"):
        db.run("UPDATE learning_log SET status='undone' WHERE id=?", (r["id"],))
    return res


def restore_default(scope: str, key: str) -> dict:
    db.run("UPDATE preferences SET status='undone' WHERE scope=? AND key=? AND status='active'", (scope, key))
    log("preference", f"{scope}.{key} back to default", "owner reset", "owner")
    _effects(scope, key, None)
    return {"ok": True}


def active_prefs() -> dict:
    return {k: get_pref(*k.split(".", 1)) for k in SCHEMA}


def recent_log(limit: int = 40) -> list[dict]:
    return [dict(r) for r in db.q("SELECT id,ts,kind,title,reason,source,status FROM learning_log ORDER BY id DESC LIMIT ?", (limit,))]


def prompt_hint() -> str:
    p = active_prefs()
    bits = [f"answer length: {p['chat.length']}", f"tone: {p['chat.tone']}"]
    if p["chat.language"] != "auto":
        bits.append(f"always answer in: {p['chat.language']}")
    if p["chat.emoji"] == "none":
        bits.append("no emoji")
    return "Owner's chosen style: " + "; ".join(bits) + "."


# ---- signals --------------------------------------------------------------

def record_signal(kind: str, subject: str, value: int, topic: str = "") -> bool:
    """kind: thumb | explicit | opened. subject is a category word, never a chat name or message text."""
    subject, topic = re.sub(r"[^\w.-]", "", subject)[:40], re.sub(r"[^\w .-]", "", topic)[:40]
    if db.one("SELECT 1 FROM signals WHERE kind=? AND subject=? AND value=? AND topic=? AND ts>?", (kind, subject, value, topic, time.time() - 600)):
        return False
    db.run("INSERT INTO signals(ts,kind,subject,value,topic) VALUES(?,?,?,?,?)", (time.time(), kind, subject, int(value), topic))
    return True


def _week_numbers() -> dict:
    since = time.time() - 7 * 86400
    sig = {f"{r['subject']}:{'up' if r['value'] > 0 else 'down'}": r["c"] for r in
           db.q("SELECT subject, value, COUNT(*) c FROM signals WHERE ts>? GROUP BY subject, value", (since,))}
    drafts = {r["status"]: r["c"] for r in db.q("SELECT status, COUNT(*) c FROM drafts WHERE ts>? GROUP BY status", (since,))}
    tasks_done = (db.one("SELECT COUNT(*) c FROM tasks WHERE done_ts>?", (since,)) or {"c": 0})["c"]
    return {"signals": sig, "drafts": drafts, "tasks_done": tasks_done}


async def weekly_review(provider=None, model: str = "", dry: bool = False) -> dict:
    """A tool-less model call sees only numbers and the allowed schema and answers with JSON. At most 3 changes."""
    nums = _week_numbers()
    evidence = sum(nums["signals"].values()) + sum(nums["drafts"].values()) + nums["tasks_done"]
    if evidence < 5:
        return {"ok": True, "skipped": "not enough evidence this week", "evidence": evidence}
    cfg = config.load()
    if provider is None:
        from . import providers
        provider, model = providers.for_role(cfg, "fast")
    allowed = {k: (v[1] if v[0] in ("enum", "enumlist") else v[0]) for k, v in SCHEMA.items() if k.split(".")[0] not in AI_FORBIDDEN_SCOPES}
    prompt = ("You tune a personal assistant's style from weekly numbers. Allowed settings and values: " + json.dumps(allowed) +
              "\nCurrent: " + json.dumps({k: v for k, v in active_prefs().items() if k in allowed}) +
              "\nThis week: " + json.dumps(nums) +
              '\nReply with JSON only: {"note": "<one short sentence>", "changes": [{"scope": "", "key": "", "value": null, "confidence": 0.0, "reason": ""}]}. '
              "At most 3 changes; change nothing if the numbers do not clearly support it.")
    resp = await provider.chat(model, [{"role": "user", "content": prompt}], temperature=0, max_tokens=500)
    m = re.search(r"\{.*\}", resp.text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    applied, proposed, skipped = [], [], []
    for ch in (data.get("changes") or [])[:3]:
        scope, key = str(ch.get("scope", "")), str(ch.get("key", ""))
        conf = float(ch.get("confidence", 0) or 0)
        if scope in AI_FORBIDDEN_SCOPES:
            skipped.append(f"{scope}.{key}")
            continue
        if db.one("SELECT 1 FROM preferences WHERE scope=? AND key=? AND ts>?", (scope, key, time.time() - 7 * 86400)):
            skipped.append(f"{scope}.{key} (changed within 7 days)")
            continue
        try:
            val = norm(scope, key, ch.get("value"))
        except ValueError:
            skipped.append(f"{scope}.{key}")
            continue
        if dry:
            applied.append(f"{scope}.{key}={val} (dry run)")
        elif conf >= 0.6:
            set_prefs(scope, {key: val}, "review", str(ch.get("reason", ""))[:200], conf)
            applied.append(f"{scope}.{key}={val}")
        else:
            db.run("INSERT INTO preferences(ts,scope,key,value,source,confidence,status,reason) VALUES(?,?,?,?,?,?,?,?)",
                   (time.time(), scope, key, json.dumps(val), "review", conf, "proposed", str(ch.get("reason", ""))[:200]))
            proposed.append(f"{scope}.{key}={val}")
    note = str(data.get("note", ""))[:300]
    if not dry:
        db.kv_set("week_note", {"ts": time.time(), "note": note, "applied": applied, "proposed": proposed})
        from . import outbox
        outbox.notify_owner("What I learned this week: " + (note or "nothing changed") + " (see Settings > Learning)", "review")
    return {"ok": True, "note": note, "applied": applied, "proposed": proposed, "skipped": skipped}


def proposals() -> list[dict]:
    return [{"id": r["id"], "scope": r["scope"], "key": r["key"], "value": json.loads(r["value"]), "reason": r["reason"], "confidence": r["confidence"]}
            for r in db.q("SELECT * FROM preferences WHERE status='proposed' ORDER BY id DESC")]


def decide_proposal(pid: int, accept: bool) -> dict:
    r = db.one("SELECT * FROM preferences WHERE id=? AND status='proposed'", (int(pid),))
    if not r:
        return {"ok": False, "error": "no such proposal"}
    db.run("UPDATE preferences SET status='undone' WHERE id=?", (r["id"],))
    if accept:
        return set_prefs(r["scope"], {r["key"]: json.loads(r["value"])}, "owner", "accepted a proposal: " + (r["reason"] or ""))
    return {"ok": True}
