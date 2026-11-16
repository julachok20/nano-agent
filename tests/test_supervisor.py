"""N10: the supervisor (lease, tripwires, freeze, forensics, review, kill). Fake clock, LocalRuntime test double, synthetic data.
These tests show the state machine and the tripwire rules. They do not show that a same-user process is contained."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nanoagent import config, db
from nanoagent import sandbox_ws as ws
from nanoagent import supervisor as sv
from nanoagent.sandbox_runtime import LocalRuntime


@pytest.fixture
def sbx(home, monkeypatch, tmp_path):
    monkeypatch.setenv("NANO_SUPERVISOR_HOME", str(tmp_path / "sup"))
    cfg = config.load()
    cfg["sandbox"].update(workspace=True, tier="T0", lease_s=120, session_h=2, run_timeout_s=10, disk_mb=50, memory_mb=512,
                          tripwire_blocked=5, tripwire_window_min=10)
    config.save(cfg)
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(sv, "_now", lambda: clock["t"])
    rt = LocalRuntime()
    ws.use(rt)
    sup = sv.Supervisor(runtime=rt)
    assert sup.start_session()["ok"]
    ws.plant_canaries()
    yield SimpleNamespace(sup=sup, rt=rt, clock=clock, home=tmp_path / "sup")
    ws.use(None)


def _state() -> dict:
    return sv.read_state()


def _trip_reason(sbx) -> str:
    sbx.sup.tick()
    assert _state()["state"] == "frozen_review", _state()
    return _state()["trip"]


# ---- lease and session ----------------------------------------------------------------------------------

def test_lease_expiry_freezes_a_running_job(sbx):
    res: dict = {}

    def job():
        res["r"] = ws.run_command("python -c \"import time; time.sleep(5)\"")

    th = threading.Thread(target=job)
    th.start()
    time.sleep(0.4)                      # the job is running
    sbx.clock["t"] += 200                # the supervisor stops renewing: the lease (120 s) lapses
    th.join(timeout=30)
    assert res["r"]["frozen"] is True
    assert sv.lease_ok()[0] is False
    assert _trip_reason(sbx).startswith("lease expired")


def test_no_new_work_after_the_lease_lapses(sbx):
    sbx.clock["t"] += 200
    r = ws.run_command("python -c \"print(1)\"")
    assert r["ok"] is False and "lease" in r["error"]


def test_session_time_box_ends_the_session(sbx):
    sbx.clock["t"] += 3 * 3600
    sbx.sup.tick()
    assert _state()["state"] == "session_ended"
    assert sv.gate()[0] is False


def test_renewal_keeps_a_healthy_session_alive(sbx):
    for _ in range(3):
        sbx.clock["t"] += 100
        sbx.sup.tick()
    assert _state()["state"] == "running" and sv.gate()[0] is True


# ---- tripwires: each one fires ----------------------------------------------------------------------------

def test_tripwire_canary_touched(sbx):
    ws.read(".canary/fake_keys.env")
    assert "canary touched" in _trip_reason(sbx)


def test_tripwire_control_path_access(sbx):
    ws.write("../../supervisor/state.json", "{}")
    assert "control path access" in _trip_reason(sbx)


def test_tripwire_blocked_edge_attempts(sbx):
    for i in range(5):
        ws.read(f"../../escape-{i}.txt")
    assert "blocked edge attempts" in _trip_reason(sbx)


def test_tripwire_log_tampering_by_edited_row(sbx):
    ws.read("a.txt")
    sbx.sup.tick()
    db.run("UPDATE sandbox_audit SET target='rewritten' WHERE id=(SELECT MAX(id) FROM sandbox_audit)")
    assert "log tampering" in _trip_reason(sbx)


def test_tripwire_log_tampering_by_removed_rows(sbx):
    ws.read("a.txt")
    sbx.sup.tick()                       # the head of the chain is recorded here
    db.run("DELETE FROM sandbox_audit WHERE id=(SELECT MAX(id) FROM sandbox_audit)")
    assert "rows were removed" in _trip_reason(sbx)


def test_tripwire_resource_spike_from_metrics(sbx):
    ws.audit("metric", "mem_mb=99999.0 disk_mb=1.0", "obs")
    assert "resource spike" in _trip_reason(sbx)


def test_tripwire_resource_limit_event(sbx):
    ws.audit("resource_limit", "disk over", "trip")
    assert "resource limit" in _trip_reason(sbx)


def test_tripwire_unknown_outbound_connection(sbx):
    cfg = config.load()
    cfg["sandbox"].update(tier="T1", allowed_domains=["allowed.example.test"])
    config.save(cfg)
    ws.audit("fetch", "https://evil.example.test/x", "allow", "edge let it through")
    assert "unknown outbound connection" in _trip_reason(sbx)


def test_tripwire_ignored_stop_request(sbx):
    sv.begin_run("chat-stuck")           # work starts and never ends
    sbx.sup.request_stop()
    sbx.clock["t"] += 120                # it keeps going past the grace period
    sbx.sup.tick()
    assert _state()["state"] == "frozen_review" and "ignored stop" in _state()["trip"]


def test_tripwire_heartbeat_failure(sbx):
    sbx.rt.fail_ping = True
    for _ in range(3):
        sbx.sup.tick()
    assert _state()["state"] == "frozen_review" and "heartbeat" in _state()["trip"]


# ---- order, forensics, review, rollback ------------------------------------------------------------------

def test_trip_freezes_first_then_keeps_forensics_and_notifies(sbx):
    ws.write("evidence.txt", "before the trip")
    ws.read(".canary/fake_keys.env")
    sbx.sup.tick()
    assert sbx.rt.paused is True                        # frozen
    bundle = Path(_state()["forensic"])
    assert (bundle / "audit.json").exists() and (bundle / "reason.txt").exists()
    assert "Sandbox frozen" in (sbx.home / "notifications.log").read_text(encoding="utf-8")


def test_resume_and_rollback_need_a_log_review_first(sbx):
    ws.write("evidence.txt", "x")
    ws.read(".canary/fake_keys.env")
    sbx.sup.tick()
    assert sbx.sup.resume()["ok"] is False
    assert "review" in sbx.sup.rollback("anything")["error"]
    assert sbx.sup.review()["ok"] is True
    assert sbx.sup.resume()["ok"] is True
    assert _state()["state"] == "running" and sbx.rt.paused is False


def test_rollback_after_review_restores_the_workspace(sbx):
    ws.write("notes/keep.txt", "good state")
    sid = ws.snapshot("good")["id"]
    ws.write("notes/keep.txt", "tampered")
    ws.read(".canary/fake_keys.env")
    sbx.sup.tick()
    sbx.sup.review()
    assert sbx.sup.rollback(sid)["ok"] is True
    assert ws.read("notes/keep.txt")["text"] == "good state"


# ---- kill switch, control path, command queue -------------------------------------------------------------

def test_kill_is_immediate_measured_and_final(sbx):
    r = sbx.sup.kill()
    assert r["ok"] is True and r["state"] == "killed"
    assert isinstance(r["kill_latency_ms"], float) and r["kill_latency_ms"] >= 0
    assert sbx.rt.killed is True
    assert sv.gate()[0] is False
    assert sbx.sup.resume()["ok"] is False


def test_owner_command_is_queued_when_the_supervisor_is_alive_and_applied_on_tick(sbx):
    sbx.sup.tick()                       # marks the supervisor alive
    assert sv.command("kill", home=sbx.home) == {"ok": True, "queued": True, "state": "queued"}
    assert _state()["state"] == "running"
    sbx.sup.tick()
    assert _state()["state"] == "killed"
    assert any("owner kill: ok" in e["text"] for e in _state()["events"])


def test_a_refused_queued_command_is_logged_to_the_owner(sbx):
    sbx.sup.tick()
    sv.command("resume", home=sbx.home)  # nothing to resume while running: refused on the tick, not silently
    sbx.sup.tick()
    assert any("owner resume:" in e["text"] and "ok" not in e["text"] for e in _state()["events"])


def test_agent_cannot_reach_the_supervisor_folder(sbx):
    assert ws.is_control(sbx.home / "control" / "x.json") is True
    assert ws.write("../supervisor/control/x.json", "{}")["ok"] is False
    assert ws.read("../supervisor/state.json")["ok"] is False
    assert str(sbx.home) not in str(ws.root())   # the supervisor folder is never inside the mounted workspace


def test_kill_latency_is_recorded_in_the_state(sbx):
    sbx.sup.kill()
    assert _state()["kill_latency_ms"] is not None
