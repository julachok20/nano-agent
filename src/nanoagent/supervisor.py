"""The kill switch (N10), enforced OUTSIDE the sandbox.

A supervisor owns the sandbox lifecycle. The sandbox runs only while the supervisor renews a short lease, and each owner
session is time-boxed (default 2 hours). Its state lives in its own folder (`supervisor_dir()`, which the sandbox never
mounts), and it is the only writer of that state. Honest limit: a same-user process can still read and tamper with
files on the same account. For real separation run the supervisor under its own OS user (see docs/SANDBOX.md).

    state:  idle -> running -> (paused | stop_requested | session_ended | frozen_review | killed)

Fail closed: when the lease lapses, new commands are refused at the gate and a running command is frozen by its watcher.
Tripwires (checked on every tick, from the audit table): canary touched, control-path access, N blocked edge attempts in
M minutes, log tampering, resource spike, unknown outbound connection, ignored stop request, heartbeat failure, lease
lapse. A trip: freeze first (pause), then a forensic bundle, then notify the owner, then require a log review before
resume or rollback.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from . import config, db, paths
from . import sandbox_ws as ws
from .sandbox_runtime import RuntimeUnavailable

CONTROL, FORENSIC = "control", "forensic"
STOP_GRACE_S = 30
HB_FAIL_MAX = 3
ALIVE_S = 30
COMMANDS = {"session_start", "pause", "resume", "stop", "kill", "review", "rollback"}


def _now() -> float:
    return time.time()


def default_state() -> dict:
    return {"state": "idle", "lease_until": 0.0, "session_until": 0.0, "stop_at": 0.0, "trip": "", "reviewed": False,
            "hb": 0.0, "hb_fail": 0, "audit_cursor": 0, "audit_head": None, "kill_latency_ms": None, "freeze_ms": None,
            "forensic": "", "events": []}


def read_state(home: Path | None = None) -> dict:
    p = (home or paths.supervisor_dir()) / "state.json"
    try:
        return {**default_state(), **json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return default_state()


def _save(home: Path, st: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    tmp = home / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, home / "state.json")


def _event(st: dict, text: str) -> None:
    st["events"] = (st.get("events", []) + [{"t": round(_now(), 1), "text": str(text)[:200]}])[-50:]


# ---- gate used by the sandbox tools (reads state; the supervisor is the only writer) ------------------

def lease_ok(home: Path | None = None) -> tuple[bool, str]:
    st = read_state(home)
    if st["state"] != "running":
        return False, f"the sandbox is {st['state']}; the owner must start or resume a session"
    if _now() > st["lease_until"]:
        return False, "the supervisor lease expired; the sandbox is frozen until the supervisor renews it"
    return True, ""


def lease_ok_watch() -> bool:
    return lease_ok()[0]


def gate(home: Path | None = None) -> tuple[bool, str]:
    if not ws.enabled():
        return False, "The sandbox workspace is off. The owner can turn it on with `nano-agent sandbox enable` (needs Docker)."
    st = read_state(home)
    if st["state"] == "stop_requested":
        return False, "The owner asked you to stop. Stop now, start no new work, and report what you finished."
    return lease_ok(home)


def begin_run(run_id: str) -> None:
    ws.audit("run_start", run_id, "obs", "")


def end_run(run_id: str) -> None:
    ws.audit("run_end", run_id, "obs", "")


# ---- the supervisor ------------------------------------------------------------------------------------

class Supervisor:
    def __init__(self, home: Path | None = None, runtime=None):
        self.home = Path(home or paths.supervisor_dir())
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / CONTROL).mkdir(exist_ok=True)
        (self.home / FORENSIC).mkdir(exist_ok=True)
        self._rt = runtime

    @property
    def rt(self):
        return self._rt or ws.get_runtime()

    def st(self) -> dict:
        return read_state(self.home)

    def save(self, st: dict) -> None:
        _save(self.home, st)

    def _freeze_rt(self) -> float:
        t0 = time.perf_counter()
        try:
            self.rt.pause(ws.container())
        except (RuntimeUnavailable, OSError):
            pass
        return round((time.perf_counter() - t0) * 1000, 2)

    # owner actions -------------------------------------------------------------------------------------

    def start_session(self) -> dict:
        if not ws.enabled():
            return {"ok": False, "error": "the sandbox workspace is off"}
        st = self.st()
        if st["state"] not in ("idle", "session_ended", "killed"):
            return {"ok": False, "error": f"the sandbox is {st['state']}; resume it or review first"}
        s = ws.settings()
        now = _now()
        try:
            self.rt.ensure(ws.container(), config.load()["sandbox"].get("image", "python:3.12-slim"), ws.root(), float(s["cpu"]), int(s["memory_mb"]))
        except RuntimeUnavailable as e:
            return {"ok": False, "error": str(e)}
        st.update(state="running", session_until=now + float(s["session_h"]) * 3600, lease_until=now + float(s["lease_s"]),
                  trip="", stop_at=0.0, hb_fail=0, reviewed=False, session_start_id=_last_audit_id(),
                  audit_cursor=_last_audit_id())
        _event(st, "session started")
        self.save(st)
        ws.audit("supervisor", "session_start", "allow", "owner started a session")
        return {"ok": True, "state": "running"}

    def pause(self) -> dict:
        st = self.st()
        if st["state"] != "running":
            return {"ok": False, "error": f"nothing to pause (state {st['state']})"}
        freeze_ms = self._freeze_rt()
        st["state"] = "paused"
        _event(st, f"paused by owner (pause {freeze_ms} ms)")
        self.save(st)
        return {"ok": True, "state": "paused"}

    def resume(self) -> dict:
        st = self.st()
        if st["state"] == "frozen_review" and not st["reviewed"]:
            return {"ok": False, "error": "review the forensic log first: nano-agent sandbox review"}
        if st["state"] not in ("paused", "frozen_review", "stop_requested"):
            return {"ok": False, "error": f"cannot resume from state {st['state']}; start a session instead"}
        now = _now()
        if now >= st["session_until"]:
            return {"ok": False, "error": "the session time box has ended; start a new session"}
        try:
            self.rt.unpause(ws.container())
        except (RuntimeUnavailable, OSError):
            pass
        st.update(state="running", stop_at=0.0, lease_until=now + float(ws.settings()["lease_s"]), hb_fail=0)
        _event(st, "resumed")
        self.save(st)
        return {"ok": True, "state": "running"}

    def request_stop(self) -> dict:
        st = self.st()
        if st["state"] not in ("running", "paused"):
            return {"ok": False, "error": f"nothing to stop (state {st['state']})"}
        st.update(state="stop_requested", stop_at=_now())
        _event(st, "owner stop requested")
        self.save(st)
        ws.audit("supervisor", "stop", "allow", "owner stop requested")
        return {"ok": True, "state": "stop_requested"}

    def kill(self) -> dict:
        st = self.st()
        t0 = time.perf_counter()
        try:
            self.rt.kill(ws.container())
        except (RuntimeUnavailable, OSError):
            pass
        latency = round((time.perf_counter() - t0) * 1000, 2)
        st.update(state="killed", lease_until=0.0, kill_latency_ms=latency)
        _event(st, f"killed by owner in {latency} ms")
        self.save(st)
        ws.audit("supervisor", "kill", "allow", f"owner kill, {latency} ms")
        return {"ok": True, "state": "killed", "kill_latency_ms": latency}

    def review(self) -> dict:
        st = self.st()
        if st["state"] not in ("frozen_review", "paused", "killed", "session_ended", "stop_requested"):
            return {"ok": False, "error": "nothing to review right now"}
        reason = st.get("trip") or "owner review"
        rows = ws.audit_rows(limit=20)
        st["reviewed"] = True
        _event(st, "log reviewed by owner")
        self.save(st)
        return {"ok": True, "reason": reason, "forensic": st.get("forensic", ""), "last_rows": rows}

    def rollback(self, snap_id: str) -> dict:
        st = self.st()
        if st["state"] == "running":
            return {"ok": False, "error": "pause or stop the sandbox before a rollback"}
        if st["state"] == "frozen_review" and not st["reviewed"]:
            return {"ok": False, "error": "review the forensic log before a rollback: nano-agent sandbox review"}
        r = ws.restore(snap_id)
        if r.get("ok"):
            st["reviewed"] = False
            _event(st, f"rolled back to {snap_id}")
            self.save(st)
        return r

    # tick: the loop body -----------------------------------------------------------------------------

    def tick(self) -> list[str]:
        events: list[str] = []
        handled: list[tuple[str, dict]] = []
        for f in sorted((self.home / CONTROL).glob("*.json")):
            try:
                cmd = json.loads(f.read_text(encoding="utf-8"))
                f.unlink(missing_ok=True)
                name = str(cmd.get("cmd", ""))
                handled.append((name, self.handle(name, cmd.get("arg"))))
                events.append(name)
            except (OSError, ValueError):
                f.unlink(missing_ok=True)
        st = self.st()
        for name, res in handled:   # a queued command's outcome is shown to the owner in the event log
            _event(st, f"owner {name}: " + ("ok" if res.get("ok") else str(res.get("error", "refused"))))
        now = _now()
        st["hb"] = now
        if st["state"] == "running":
            if now >= st["session_until"]:
                self._freeze_rt()
                st["state"] = "session_ended"
                _event(st, "session time box ended; sandbox frozen")
            elif now > st["lease_until"]:
                self.trip(st, "lease expired: the supervisor was not renewing, so the sandbox froze")
            else:
                try:
                    alive = bool(self.rt.ping(ws.container()))
                except (RuntimeUnavailable, OSError):
                    alive = False
                st["hb_fail"] = 0 if alive else int(st.get("hb_fail", 0)) + 1
                if st["hb_fail"] >= HB_FAIL_MAX:
                    self.trip(st, "heartbeat failure: the sandbox stopped answering")
                else:
                    st["lease_until"] = now + float(ws.settings()["lease_s"])   # renew only while healthy
        if st["state"] in ("running", "stop_requested"):
            reason = self._tripwires(st)
            if reason:
                self.trip(st, reason)
        self.save(st)
        return events

    def _tripwires(self, st: dict) -> str | None:
        s = ws.settings()
        reason: str | None = None
        for r in ws.audit_rows(limit=5000, since_id=int(st["audit_cursor"] or 0)):
            st["audit_cursor"] = max(int(st["audit_cursor"] or 0), int(r["id"]))
            k, d = r["kind"], r["decision"]
            if reason is None and k == "canary_touch":
                reason = f"canary touched: {r['target']}"
            elif reason is None and k == "control_path":
                reason = f"control path access attempt: {r['target']}"
            elif reason is None and k == "fetch" and d == "allow" and s["tier"] == "T1":
                host = (urlparse(r["target"]).hostname or "").lower()
                if not ws._host_allowed(host, s["allowed_domains"]):
                    reason = "unknown outbound connection"
            elif reason is None and k == "resource_limit":
                reason = f"resource limit exceeded: {r['target']}"
        window_s = int(s["tripwire_window_min"]) * 60
        blocked = db.one("SELECT COUNT(*) c FROM sandbox_audit WHERE decision='deny' AND ts>? AND id>?",
                         (_now() - window_s, int(st.get("session_start_id") or 0)))
        if reason is None and blocked and int(blocked["c"]) >= int(s["tripwire_blocked"]):
            reason = f"{blocked['c']} blocked edge attempts in {s['tripwire_window_min']} minutes"
        ok, bad = ws.verify_chain()
        if reason is None and not ok:
            reason = f"log tampering: audit chain broken at row {bad}"
        head = st.get("audit_head")
        if reason is None and head:
            row = db.one("SELECT hash FROM sandbox_audit WHERE id=?", (int(head["id"]),))
            if row is None or row["hash"] != head["hash"]:
                reason = "log tampering: audit rows were removed"
        last = db.one("SELECT id, hash FROM sandbox_audit ORDER BY id DESC LIMIT 1")
        if last:
            st["audit_head"] = {"id": int(last["id"]), "hash": last["hash"]}
        metric = db.one("SELECT target FROM sandbox_audit WHERE kind='metric' ORDER BY id DESC LIMIT 1")
        if reason is None and metric:
            vals = dict(p.split("=", 1) for p in metric["target"].split() if "=" in p)
            if float(vals.get("mem_mb", 0)) > float(s["memory_mb"]):
                reason = f"resource spike: memory {vals.get('mem_mb')} MB over {s['memory_mb']} MB"
        if reason is None and st.get("stop_at"):
            reason = self._ignored_stop(float(st["stop_at"]))
        return reason

    def _ignored_stop(self, stop_at: float) -> str | None:
        """A run that started after the owner's stop (plus grace) and never ended is an ignored stop request."""
        rows = db.q("SELECT kind,target,ts FROM sandbox_audit WHERE kind IN ('run_start','run_end') AND ts>=? ORDER BY id", (stop_at,))
        open_runs: dict[str, float] = {}
        for r in rows:
            if r["kind"] == "run_start":
                open_runs[r["target"]] = float(r["ts"])
            else:
                open_runs.pop(r["target"], None)
        for started in open_runs.values():
            if started > stop_at + STOP_GRACE_S:
                return "ignored stop request: work kept running after the owner's stop"
        return None

    def trip(self, st: dict, reason: str) -> None:
        freeze_ms = self._freeze_rt()                      # 1. freeze first
        bundle = self._forensic(reason)                    # 2. forensic snapshot and audit export
        st.update(state="frozen_review", trip=reason, reviewed=False, freeze_ms=freeze_ms, forensic=str(bundle))
        _event(st, f"TRIPPED: {reason}")
        self._notify(f"Sandbox frozen: {reason}. Review the forensic log before any resume or rollback: nano-agent sandbox review")  # 3.

    def _forensic(self, reason: str) -> Path:
        d = self.home / FORENSIC / time.strftime("%Y%m%d-%H%M%S")
        d.mkdir(parents=True, exist_ok=True)
        (d / "reason.txt").write_text(reason, encoding="utf-8")
        (d / "audit.json").write_text(json.dumps(ws.audit_rows(limit=2000), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        try:
            snap = ws.snapshot("forensic")
            (d / "workspace_snapshot.txt").write_text(snap["path"], encoding="utf-8")
        except OSError:
            (d / "workspace_snapshot.txt").write_text("snapshot failed", encoding="utf-8")
        return d

    def _notify(self, text: str) -> None:
        with (self.home / "notifications.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
        try:
            from . import outbox
            outbox.notify_owner(text, "sandbox")
        except Exception:
            pass   # the log line above is the fallback

    def handle(self, cmd: str, arg=None) -> dict:
        if cmd == "session_start":
            return self.start_session()
        if cmd == "pause":
            return self.pause()
        if cmd == "resume":
            return self.resume()
        if cmd == "stop":
            return self.request_stop()
        if cmd == "kill":
            return self.kill()
        if cmd == "review":
            return self.review()
        if cmd == "rollback":
            return self.rollback(str(arg or ""))
        return {"ok": False, "error": f"unknown command {cmd!r}"}

    def run_forever(self, every: float = 2.0, max_ticks: int | None = None) -> None:
        n = 0
        while max_ticks is None or n < max_ticks:
            self.tick()
            n += 1
            time.sleep(every)


def _last_audit_id() -> int:
    r = db.one("SELECT COALESCE(MAX(id),0) m FROM sandbox_audit")
    return int(r["m"]) if r else 0


def supervisor_alive(home: Path | None = None) -> bool:
    return _now() - float(read_state(home)["hb"] or 0) < ALIVE_S


def command(cmd: str, arg=None, home: Path | None = None) -> dict:
    """Owner entry point (CLI and console API). Queues the command when the supervisor is running, else applies it now."""
    if cmd not in COMMANDS:
        return {"ok": False, "error": f"unknown command {cmd!r}"}
    home = home or paths.supervisor_dir()
    if supervisor_alive(home):
        q = home / CONTROL
        q.mkdir(parents=True, exist_ok=True)
        (q / f"{time.time_ns()}-{cmd}.json").write_text(json.dumps({"cmd": cmd, "arg": arg}), encoding="utf-8")
        return {"ok": True, "queued": True, "state": "queued"}
    return Supervisor(home).handle(cmd, arg)


__all__ = ["Supervisor", "gate", "lease_ok", "command", "read_state", "begin_run", "end_run"]
