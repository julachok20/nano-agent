"""SQLite storage. One file (data/nano.db), WAL mode, one schema. Timestamps are epoch seconds (float, UTC)."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts REAL, session TEXT, role TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, text TEXT, source TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY, ts REAL, title TEXT, due REAL, priority INTEGER DEFAULT 2,
  done INTEGER DEFAULT 0, done_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, ts REAL, name TEXT NOT NULL, goal TEXT DEFAULT '',
  deadline TEXT DEFAULT '', next_step TEXT DEFAULT '', status TEXT DEFAULT 'active', closed_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS project_items(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  ts REAL, kind TEXT NOT NULL, text TEXT NOT NULL, due TEXT DEFAULT '', done INTEGER DEFAULT 0, done_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY, ts REAL, text TEXT, due REAL, fired INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS drafts(id INTEGER PRIMARY KEY, ts REAL, channel TEXT, target TEXT, text TEXT, code TEXT,
  status TEXT DEFAULT 'pending', decided_ts REAL DEFAULT 0, note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, ts REAL, channel TEXT, target TEXT, kind TEXT, payload TEXT,
  status TEXT DEFAULT 'pending', sent_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, title TEXT, status TEXT DEFAULT 'running',
  detail TEXT DEFAULT '', ended REAL DEFAULT 0, steps TEXT DEFAULT '[]', result TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS preferences(id INTEGER PRIMARY KEY, ts REAL, scope TEXT, key TEXT, value TEXT, source TEXT,
  confidence REAL DEFAULT 1, status TEXT DEFAULT 'active', reason TEXT DEFAULT '', prev TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS learning_log(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, title TEXT, reason TEXT, source TEXT,
  undo TEXT DEFAULT '{}', status TEXT DEFAULT 'done');
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, subject TEXT, value INTEGER, topic TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS traits(name TEXT PRIMARY KEY, value TEXT, confidence REAL, source TEXT, reason TEXT, ts REAL,
  deleted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS trait_evidence(id INTEGER PRIMARY KEY, trait TEXT, ts REAL, kind TEXT, ref TEXT, value REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS automations(id INTEGER PRIMARY KEY, name TEXT UNIQUE, job TEXT, prompt TEXT DEFAULT '', schedule TEXT, enabled INTEGER DEFAULT 1,
  last_run REAL DEFAULT 0, last_status TEXT DEFAULT '', next_run REAL DEFAULT 0, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS skill_meta(name TEXT PRIMARY KEY, source TEXT, origin TEXT, ts REAL, review TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS patches(id INTEGER PRIMARY KEY, ts REAL, title TEXT, status TEXT, summary TEXT DEFAULT '',
  files TEXT DEFAULT '[]', diff TEXT DEFAULT '', test_result TEXT DEFAULT '', code TEXT DEFAULT '', applied_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sandbox_audit(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, target TEXT, decision TEXT,
  reason TEXT DEFAULT '', run_id TEXT DEFAULT '', prev TEXT DEFAULT '', hash TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS capability_requests(id INTEGER PRIMARY KEY, ts REAL, connector TEXT, actions TEXT, scope TEXT,
  reason TEXT, code TEXT DEFAULT '', status TEXT DEFAULT 'pending', decided_ts REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS capability_grants(id INTEGER PRIMARY KEY, ts REAL, request_id INTEGER, connector TEXT, actions TEXT,
  scope TEXT, revoked INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_messages_session ON messages(session, id);
CREATE INDEX IF NOT EXISTS ix_activity_ts ON activity(ts);
CREATE INDEX IF NOT EXISTS ix_project_items_project ON project_items(project_id, id);
"""

_initialised: set[str] = set()


def connect() -> sqlite3.Connection:
    paths.ensure_dirs()
    p = str(paths.db_path())
    db = sqlite3.connect(p, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    if p not in _initialised:
        db.executescript(SCHEMA)
        db.commit()
        _initialised.add(p)
    return db


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    db = connect()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with tx() as db:
        return db.execute(sql, args).fetchall()


def one(sql: str, args: tuple = ()) -> sqlite3.Row | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def run(sql: str, args: tuple = ()) -> int:
    """Execute a write; returns lastrowid."""
    with tx() as db:
        return db.execute(sql, args).lastrowid or 0


def kv_get(key: str, default: Any = None) -> Any:
    import json

    r = one("SELECT v FROM kv WHERE k=?", (key,))
    if not r:
        return default
    try:
        return json.loads(r["v"])
    except Exception:
        return default


def kv_set(key: str, value: Any) -> None:
    import json

    run("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, json.dumps(value)))


def now() -> float:
    return time.time()


def reset_cache() -> None:
    """Tests switch NANO_AGENT_HOME between cases; forget which files were initialised."""
    _initialised.clear()
