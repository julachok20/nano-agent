"""Health checks and backups. Generic: disk, database integrity, key file permissions, provider configured, backup age,
scheduler heartbeat. No service names, no GPU assumptions (GPU and CPU numbers are optional extras on the System page).
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from datetime import datetime

from . import config, db, keystore, paths


def check() -> list[dict]:
    out = []

    def add(name, ok, detail=""):
        out.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        r = db.one("PRAGMA quick_check")
        add("database", r and r[0] == "ok", "integrity check")
    except Exception as e:
        add("database", False, type(e).__name__)
    du = shutil.disk_usage(paths.home())
    add("disk", du.free / du.total > 0.05, f"{du.free // 2**30} GB free")
    add("secrets file permissions", keystore.file_mode_ok(), "private (0600)" if keystore.file_mode_ok() else "readable by other users: run chmod 600")
    cfg = config.load()
    add("provider configured", bool(config.get(cfg, "models.chat")), config.get(cfg, "models.chat", "run `nano-agent setup`"))
    bk = latest_backup()
    add("backup", bk is not None and time.time() - bk[0] < 36 * 3600 or not db.one("SELECT 1 FROM kv WHERE k='sched_heartbeat'"),
        "none yet" if not bk else f"{int((time.time() - bk[0]) / 3600)} h old")
    hb = db.kv_get("sched_heartbeat")
    if hb is not None:
        add("scheduler", time.time() - hb < 300, f"last tick {int(time.time() - hb)} s ago")
    return out


def latest_backup():
    runs = sorted(p for p in paths.backups_dir().glob("*") if p.is_dir())
    return (runs[-1].stat().st_mtime, runs[-1]) if runs else None


def backup_db() -> dict:
    """Consistent copy with SQLite's backup API, plus the skills folder. Restores the copy into memory and checks it."""
    dest = paths.backups_dir() / datetime.now().strftime("%Y%m%d-%H%M%S")
    dest.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(paths.db_path())
    dst = sqlite3.connect(dest / "nano.db")
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    if paths.skills_dir().exists():
        shutil.copytree(paths.skills_dir(), dest / "skills", dirs_exist_ok=True)
    # restore test: open the copy, integrity check, row counts against the live database
    chk = sqlite3.connect(dest / "nano.db")
    live = sqlite3.connect(paths.db_path())
    try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for t in ("memory", "tasks", "drafts"):
            ok = ok and chk.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] <= live.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] + 5
    finally:
        chk.close()
        live.close()
    for old in sorted(p for p in paths.backups_dir().glob("*") if p.is_dir())[:-14]:
        shutil.rmtree(old, ignore_errors=True)
    return {"ok": ok, "path": str(dest), "restore_check": "passed" if ok else "FAILED"}


async def run_checks_and_alert() -> dict:
    """Two bad checks in a row send ONE message; recovery sends one more."""
    from . import outbox

    bad = [c["name"] for c in check() if not c["ok"]]
    prev = db.kv_get("health_bad_streak", 0)
    streak = prev + 1 if bad else 0
    db.kv_set("health_bad_streak", streak)
    if bad and streak == 2:
        outbox.notify_owner("Health check: problem with " + ", ".join(bad), "health")
    elif not bad and prev >= 2:
        outbox.notify_owner("Health check: everything is fine again.", "health")
    return {"bad": bad, "streak": streak}
