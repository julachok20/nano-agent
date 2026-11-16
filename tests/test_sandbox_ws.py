"""N8: the sandbox workspace. Synthetic data only. Commands run through LocalRuntime, a TEST DOUBLE on the host (no isolation):
these tests check the edge rules, the audit log, scheduling and rollback. Real Docker isolation is not tested here."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from nanoagent import config, db, outbox, scheduler
from nanoagent import sandbox_ws as ws
from nanoagent import supervisor as sv
from nanoagent.providers.base import Response, ToolCall
from nanoagent.providers.fake import FakeProvider
from nanoagent.sandbox_runtime import DockerRuntime, LocalRuntime, docker_run_args


@pytest.fixture
def sbx(home, monkeypatch, tmp_path):
    monkeypatch.setenv("NANO_SUPERVISOR_HOME", str(tmp_path / "sup"))
    cfg = config.load()
    cfg["sandbox"].update(workspace=True, tier="T0", lease_s=120, session_h=2, run_timeout_s=10, disk_mb=50, memory_mb=512)
    config.save(cfg)
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(sv, "_now", lambda: clock["t"])
    rt = LocalRuntime()
    ws.use(rt)
    sup = sv.Supervisor(runtime=rt)
    assert sup.start_session()["ok"]
    yield SimpleNamespace(sup=sup, rt=rt, clock=clock, tmp=tmp_path)
    ws.use(None)


def _set_tier(tier: str, domains: list[str] | None = None, caps: list[str] | None = None) -> None:
    cfg = config.load()
    cfg["sandbox"].update(tier=tier, allowed_domains=domains or [], capabilities=caps or [])
    config.save(cfg)


# ---- tiers and the edge ------------------------------------------------------------------------------

def test_unknown_tier_falls_back_to_closed(home):
    cfg = config.load()
    cfg["sandbox"]["tier"] = "T9"
    assert ws.settings(cfg)["tier"] == "T0"


def test_t0_has_no_network_and_the_refusal_is_logged(sbx):
    r = asyncio.run(ws.fetch("https://example.test/page"))
    assert r["ok"] is False and "T0" in r["error"]
    assert any(x["kind"] == "fetch" and x["decision"] == "deny" for x in ws.audit_rows())


def test_t1_refuses_domains_not_on_the_allowlist(sbx):
    _set_tier("T1", domains=["allowed.example.test"])
    r = asyncio.run(ws.fetch("https://other.example.test/x"))
    assert r["ok"] is False and "allowlist" in r["error"]


def test_host_file_read_is_refused_and_logged(sbx):
    secret_file = sbx.tmp / "host_only.txt"
    secret_file.write_text("HOST-ONLY", encoding="utf-8")
    r = ws.read(str(secret_file))
    assert r["ok"] is False and "denied" in r["error"]
    assert any(x["kind"] == "host_read" and x["decision"] == "deny" for x in ws.audit_rows())


def test_secret_request_is_always_refused(sbx):
    r = ws.secret_request("provider.example")
    assert r["ok"] is False
    assert any(x["kind"] == "secret_read" and x["decision"] == "deny" for x in ws.audit_rows())


def test_sending_a_message_is_refused_outside_t3(sbx):
    r = ws.send_request("line", "friend-1", "hi")
    assert r["ok"] is False and "nothing was sent" in r["error"]
    assert any(x["kind"] == "send" and x["decision"] == "deny" for x in ws.audit_rows())


def test_brokered_call_needs_tier_t3_and_never_payments(sbx):
    assert "T3" in asyncio.run(ws.broker("calendar", "v1"))["error"]
    _set_tier("T3", caps=["payments=pay.example.test"])
    assert "never enabled" in asyncio.run(ws.broker("payments", "charge"))["error"]


def test_messaging_in_t3_is_queued_as_a_draft_never_sent(sbx, cfg_fake):
    _set_tier("T3", caps=["messaging"])
    r = ws.send_request("line", "friend-1", "hello from the sandbox")
    assert r["ok"] is True and r["queued_as_draft"] is True
    assert any(x["kind"] == "send" and x["decision"] == "queued" for x in ws.audit_rows())


def test_keys_are_not_in_the_sandbox_environment(sbx):
    r = ws.run_command("python -c \"import os; print(sorted(os.environ))\"")
    assert r["ok"] is True
    assert "OPENAI" not in r["stdout"] and "NANO_AGENT_HOME" not in r["stdout"]


# ---- the agent builds a tool and a scheduled automation -------------------------------------------------

def test_agent_creates_and_runs_a_new_tool_with_no_preset_tool(sbx, cfg_fake):
    from nanoagent.agent import Agent
    script = FakeProvider(script=[
        Response(tool_calls=[ToolCall("a", "ws_write", {"path": "tools/adder.py", "text": "print(2 + 3)"})]),
        Response(tool_calls=[ToolCall("b", "ws_shell", {"command": "python tools/adder.py"})]),
        Response(text="The tool printed 5."),
    ])
    res = asyncio.run(Agent(provider=script, model="m").run("build a small adder tool"))
    assert [c["name"] for c in res.tool_calls] == ["ws_write", "ws_shell"]
    assert (ws.root() / "tools" / "adder.py").exists()
    assert any(x["kind"] == "exec" and "adder" in x["target"] for x in ws.audit_rows())


def test_agent_sees_no_workspace_tools_while_the_workspace_is_off(home):
    from nanoagent import tools
    assert ws.hidden_tools() == set(ws.NAMES)
    schemas = {s["name"] for s in tools.schemas(ws.hidden_tools())}
    assert not (schemas & ws.NAMES)


def test_scheduled_job_runs_in_the_sandbox_and_logs_activity(sbx):
    from nanoagent import activity
    ws.write("tools/hello.py", "print('scheduled hello')")
    jid = ws.job_create("hello job", "tools/hello.py", {"every_min": 5})["id"]
    row = db.one("SELECT * FROM automations WHERE id=?", (jid,))
    assert asyncio.run(scheduler.run_job(row)) == "ok"
    done = activity.recent()["done"]
    assert any(d["kind"] == "sandbox" and any("scheduled hello" in s["text"] for s in d["steps"]) for d in done)


def test_failing_job_retries_then_tells_the_owner_once(sbx):
    ws.write("tools/bad.py", "import sys\nsys.exit(3)\n")
    jid = ws.job_create("bad job", "tools/bad.py", {"every_min": 5})["id"]
    row = db.one("SELECT * FROM automations WHERE id=?", (jid,))
    for expected in ("failed: RuntimeError",) * 3:
        assert asyncio.run(scheduler.run_job(row)) == expected
        row = db.one("SELECT * FROM automations WHERE id=?", (jid,))
    assert sum("failed 3 times" in i["text"] for i in outbox.feed(50)) == 1
    asyncio.run(scheduler.run_job(row))   # a fourth failure does not notify again
    assert sum("failed 3 times" in i["text"] for i in outbox.feed(50)) == 1


def test_job_edit_pause_delete_and_only_sandbox_jobs(sbx):
    ws.write("tools/a.py", "print(1)")
    ws.write("tools/b.py", "print(2)")
    jid = ws.job_create("editable", "tools/a.py", {"daily": "07:30"})["id"]
    assert ws.job_edit(jid, script="tools/b.py")["ok"]
    assert ws.job_set_enabled(jid, False)["ok"]
    assert ws.job_list()[0]["script"] == "tools/b.py" and ws.job_list()[0]["enabled"] is False
    assert ws.job_delete(jid)["ok"]
    assert ws.job_edit(9999)["ok"] is False


def test_scripts_must_live_in_the_workspace(sbx):
    assert "inside the workspace" in ws.job_create("x", "../../evil.py", {"every_min": 5})["error"]


# ---- limits -----------------------------------------------------------------------------------------------

def test_time_limit_stops_a_runaway_command(sbx):
    r = ws.run_command("python -c \"import time; time.sleep(30)\"", timeout_s=2)
    assert r["ok"] is False and r["timed_out"] is True


def test_disk_limit_is_recorded_as_a_tripwire_event(sbx):
    cfg = config.load()
    cfg["sandbox"]["disk_mb"] = 1
    config.save(cfg)
    ws.write("big.bin", "x" * (2 * 1024 * 1024))
    ws.run_command("python -c \"print(1)\"")
    assert any(x["kind"] == "resource_limit" for x in ws.audit_rows())


# ---- snapshots and rollback -------------------------------------------------------------------------------

def test_snapshot_and_restore_roll_the_workspace_back(sbx):
    ws.write("notes/a.txt", "original")
    sid = ws.snapshot("before")["id"]
    ws.write("notes/a.txt", "changed")
    ws.write("extra.txt", "new file")
    assert ws.restore(sid)["ok"] is True
    assert ws.read("notes/a.txt")["text"] == "original"
    assert not (ws.root() / "extra.txt").exists()


def test_restore_refuses_unsafe_snapshot_paths_and_changes_nothing(sbx):
    import zipfile

    from nanoagent import paths
    ws.write("keep.txt", "keep me")
    paths.snapshots_dir().mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(paths.snapshots_dir() / "evil.zip", "w") as z:
        z.writestr("../escape.txt", "x")
    assert ws.restore("evil")["ok"] is False
    assert ws.read("keep.txt")["text"] == "keep me"


# ---- audit and configuration ------------------------------------------------------------------------------

def test_audit_chain_detects_an_edited_row(sbx):
    ws.read("nothing.txt")
    assert ws.verify_chain()[0] is True
    db.run("UPDATE sandbox_audit SET target='nothing-to-see.txt' WHERE id=(SELECT MAX(id) FROM sandbox_audit)")
    ok, bad = ws.verify_chain()
    assert ok is False and bad >= 1


def test_docker_arguments_keep_the_sandbox_closed(tmp_path):
    args = docker_run_args("nano-test", "python:3.12-slim", tmp_path, 1.0, 512)
    joined = " ".join(args)
    assert "--network none" in joined and "--privileged" not in joined and "host" not in args
    assert "docker.sock" not in joined and "--cap-drop ALL" in joined and "no-new-privileges" in joined
    assert "--memory 512m" in joined and "--pids-limit" in joined
    mounts = [a for a in args if a.endswith(":/work")]
    assert len(mounts) == 1 and str(tmp_path.resolve()) in mounts[0]


def test_no_host_fallback_when_docker_is_missing(monkeypatch):
    monkeypatch.setattr("nanoagent.sandbox_runtime.shutil.which", lambda _name: None)
    ok, why = DockerRuntime().available()
    assert ok is False and "stays OFF" in why


def test_first_run_notice_exists_in_both_languages(home):
    from nanoagent import i18n
    for lang in ("en", "th"):
        assert len(i18n.t("sandbox.notice", lang=lang)) > 80


def test_prompt_hint_is_empty_when_off_and_tells_the_agent_to_save_skills_when_on(sbx):
    hint = ws.prompt_hint()
    assert "SKILL.md" in hint and "cannot change your tier" in hint
    cfg = config.load()
    cfg["sandbox"]["workspace"] = False
    config.save(cfg)
    assert ws.prompt_hint() == ""


def test_status_is_json_safe(sbx):
    json.dumps(ws.status())
