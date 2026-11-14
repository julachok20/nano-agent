"""The buddy: how the assistant opens a conversation and how it talks. No model call is needed for the opener: it is a
template chosen from what is already stored (tasks, reminders, how long since the last chat, time of day).

Relationship level assistant -> buddy -> friend changes the manner of the replies. It moves up only from buddy to friend
and only on the owner's behaviour (chatted on at least 5 different days in the last 14, 20+ messages), one step per 14
days, never when the owner set it by hand, never down automatically. Every change is on the learning log with an undo.

Honesty rule (also in every prompt, see agent.py): warm and natural, but a sincere "are you an AI?" gets the truth; no
claimed body, family or experiences; no guilt or pressure to keep talking.
"""
from __future__ import annotations

import time
from datetime import datetime

from . import config, db, i18n, tasks

LEVELS = ("assistant", "buddy", "friend")
HONESTY = ("You are the owner's AI assistant. Be warm and natural, but if the owner sincerely asks whether you are an AI, say so plainly. "
           "Never claim a body, family or personal experiences, never pretend to be human to anyone, and never pressure the owner to keep talking.")
MANNER = {
    "assistant": "Manner: polite and efficient, no small talk unless the owner starts it.",
    "buddy": "Manner: friendly and relaxed, short natural sentences.",
    "friend": "Manner: casual and playful, like a close friend, still respectful and honest.",
}


def level() -> str:
    v = db.kv_get("companion_level", {}).get("level") if isinstance(db.kv_get("companion_level", {}), dict) else None
    return v if v in LEVELS else config.load()["companion"].get("level", "buddy")


def set_level(new: str, source: str = "owner") -> dict:
    if new not in LEVELS:
        return {"ok": False, "error": "level must be one of: " + ", ".join(LEVELS)}
    old = level()
    db.kv_set("companion_level", {"level": new, "by": source, "ts": time.time()})
    if old != new:
        from . import learning
        learning.log("companion", f"Relationship level: {old} -> {new}", "", source, {"action": "level_restore", "level": old})
    return {"ok": True, "level": new}


def style_hint() -> str:
    return HONESTY + " " + MANNER[level()]


def maybe_promote() -> bool:
    st = db.kv_get("companion_level", {}) or {}
    if st.get("by") == "owner" or level() != "buddy" or time.time() - st.get("ts", 0) < 14 * 86400:
        return False
    since = time.time() - 14 * 86400
    rows = db.q("SELECT ts FROM messages WHERE role='user' AND ts>?", (since,))
    days = {datetime.fromtimestamp(r["ts"]).date() for r in rows}
    if len(days) >= 5 and len(rows) >= 20:
        set_level("friend", "learned")
        return True
    return False


def _pick(options: list[tuple[int, str]], lang: str) -> str:
    recent = db.kv_get("opener_recent", [])
    pool = [o for o in options if o[1] not in recent] or options
    pool.sort(key=lambda o: -o[0])
    best = [o for o in pool if o[0] == pool[0][0]]
    choice = best[int(time.time()) % len(best)][1]
    db.kv_set("opener_recent", ([choice] + recent)[:3])
    return choice


def opener(lang: str | None = None) -> dict:
    lang = lang or i18n.language()
    cfg = config.load()
    name = cfg["general"]["owner_name"] or ""
    now = datetime.now(config.tz(cfg))
    opts: list[tuple[int, str]] = []

    def T(key, **kw):
        return i18n.t(key, lang, name=name, **kw)

    due_today = [t for t in tasks.list_(False) if t["due"] and t["due"][:10] == now.strftime("%Y-%m-%d")]
    if due_today:
        opts.append((8, T("companion.task_due", title=due_today[0]["title"])))
    last = db.one("SELECT MAX(ts) t FROM messages WHERE role='user'")
    if last and last["t"] and time.time() - last["t"] > 3 * 86400:
        opts.append((5, T("companion.gap")))
    hr = now.hour
    tod = "morning" if 5 <= hr < 11 else "midday" if 11 <= hr < 14 else "afternoon" if 14 <= hr < 18 else "evening" if hr < 22 else "late"
    opts.append((3, T(f"companion.tod_{tod}")))
    opts.append((2, T("companion.plain")))
    return {"text": _pick(opts, lang), "level": level()}
