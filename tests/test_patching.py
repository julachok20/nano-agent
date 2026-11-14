"""Patch proposals: the hard denylist (code, not prompt), the AST allowlist, test-before-apply, owner-only apply, rollback, undo."""
from __future__ import annotations

import json

import pytest

from nanoagent import db, learning, patching, paths, tools
from nanoagent.agent import Agent
from nanoagent.providers import Response, ToolCall

from .conftest import run

GOOD = '''from nanoagent.tools import tool


@tool("Add two numbers")
def add_numbers_test(a: int, b: int) -> dict:
    return {"sum": a + b}
'''


def edits(path="plugins/adder.py", new=GOOD, old=None):
    e = {"path": path, "new": new}
    if old:
        e["old"] = old
    return [e]


@pytest.mark.parametrize("path", [
    "src/nanoagent/drafts.py", "nanoagent/gateway/auth.py", "gateway/line.py", "../secrets.toml", "plugins/../config.toml", "/etc/passwd", "C:/Windows/x.py",
    "secrets.toml", "config.toml", "nano.db", "plugins/.env", "plugins/credentials.json", "plugins/secrets.py", ".git/config", "tests/test_core.py",
    "plugins/drafts.py", "plugins/gateway/app.py", "SECURITY.md", "plugins/x.sh", "plugins/x.exe", "",
])
def test_denylist_refuses_core_secrets_and_escapes(path):
    r = patching.propose("t", "s", edits(path))
    assert r["ok"] is False and ("refused" in r or r["error"])
    assert patching.check_path(path, False) != ""


def test_readable_only_inside_plugins():
    assert patching.readable("plugins/a.py") and not patching.readable("src/nanoagent/drafts.py") and not patching.readable("secrets.toml")
    assert not patching.readable("../x")


@pytest.mark.parametrize("code,why", [
    ("import os\n", "os"), ("import subprocess\n", "subprocess"), ("from nanoagent import drafts\n", "from nanoagent import"), ("from nanoagent.drafts import approve\n", "not allowed"),
    ("import socket\n", "socket"), ("x = eval('1')\n", "eval"), ("x = open('f')\n", "open"), ("x = ().__class__\n", "__class__"), ("f = getattr(int, 'x')\n", "getattr"),
    ("exec('x')\n", "exec"), ("import importlib\n", "importlib"), ("from . import x\n", "not allowed"), ("def f(:\n", "syntax"),
])
def test_python_ast_allowlist(code, why):
    bad = patching.check_python(code)
    assert bad and any(why in b for b in bad)


@pytest.mark.parametrize("line", [
    "url = 'https://api.line.me/v2/bot/message/push'", "drafts.approve(1)", "import keystore", "x = os.environ['HOME']", "SENDERS['line'](a, b)",
    "token = channel_token", "require_owner = None", "# docker run", "api_key = 'x'",
])
def test_forbidden_lines_in_any_changed_line(line):
    assert patching.check_change("plugins/x.py", None, f"x = 1\n{line}\n"), line


def test_existing_file_removal_of_a_forbidden_line_is_also_refused():
    old = "a = 1\nSENDERS = {}\n"
    assert patching.check_change("plugins/x.py", old, "a = 1\n")


def test_limits():
    big = [{"path": f"plugins/f{i}.py", "new": "x = 1\n"} for i in range(9)]
    assert patching.propose("t", "s", big)["ok"] is False
    assert patching.propose("t", "s", [{"path": "plugins/f.py", "new": "x = 1\n" * 500}])["ok"] is False


def test_good_patch_is_tested_but_not_applied_until_owner_approves():
    r = patching.propose("Adder", "adds numbers", edits())
    assert r["ok"] and r["status"] == "ready" and r["test"]["ok"], r
    assert not (paths.plugins_dir() / "adder.py").exists() and "add_numbers_test" not in tools.REGISTRY   # nothing live changed
    res = patching.apply(r["id"])
    assert res["ok"] and (paths.plugins_dir() / "adder.py").exists() and "add_numbers_test" in tools.REGISTRY
    assert patching.apply(r["id"])["ok"] is False   # double approval
    entry = [e for e in learning.recent_log() if e["kind"] == "patch"][0]
    assert learning.undo(entry["id"])["ok"] and not (paths.plugins_dir() / "adder.py").exists()
    tools.REGISTRY.pop("add_numbers_test", None)


def test_failing_plugin_is_marked_failed_and_cannot_be_applied():
    broken = "from nanoagent.tools import tool\nraise ValueError('boom')\n"
    r = patching.propose("Broken", "x", edits("plugins/broken.py", broken))
    assert r["ok"] and r["status"] == "failed"
    assert patching.apply(r["id"])["ok"] is False and not (paths.plugins_dir() / "broken.py").exists()


def test_stale_proposal_and_expiry_and_reject():
    r = patching.propose("A", "x", edits())
    (paths.plugins_dir() / "adder.py").write_text("changed = 1\n", encoding="utf-8")   # live file appeared after the proposal
    assert "changed since" in patching.apply(r["id"])["error"]
    r2 = patching.propose("B", "x", edits("plugins/b.py"))
    db.run("UPDATE patches SET ts=ts-90000 WHERE id=?", (r2["id"],))
    assert "expired" in patching.apply(r2["id"])["error"]
    r3 = patching.propose("C", "x", edits("plugins/c.py"))
    patching.reject(r3["id"])
    assert patching.apply(r3["id"])["ok"] is False


def test_apply_rechecks_denylist_against_stored_changes():
    r = patching.propose("D", "x", edits("plugins/d.py", "x = 1\n"))
    changes = json.loads(patching.get(r["id"])["code"])
    changes[0]["path"] = "plugins/secrets.py"
    db.run("UPDATE patches SET code=? WHERE id=?", (json.dumps(changes), r["id"]))
    assert patching.apply(r["id"])["ok"] is False and not (paths.plugins_dir() / "secrets.py").exists()


def test_rollback_when_post_apply_test_fails(monkeypatch):
    r = patching.propose("E", "x", edits("plugins/e.py", "x = 1\n"))
    monkeypatch.setattr(patching, "run_test", lambda files: {"ok": False, "detail": "simulated failure"})
    res = patching.apply(r["id"])
    assert res["ok"] is False and "rolled back" in res["error"] and not (paths.plugins_dir() / "e.py").exists()
    assert patching.get(r["id"])["status"] == "rolled_back"


def test_edit_in_place_uses_unique_old_text_and_undo_restores_original():
    first = patching.propose("F", "x", edits("plugins/f.py", "value = 1\n"))
    patching.apply(first["id"])
    r = patching.propose("F2", "x", edits("plugins/f.py", "value = 2\n", old="value = 1\n"))
    assert r["ok"] and patching.apply(r["id"])["ok"] and (paths.plugins_dir() / "f.py").read_text() == "value = 2\n"
    assert patching.undo(r["id"])["ok"] and (paths.plugins_dir() / "f.py").read_text() == "value = 1\n"
    bad = patching.propose("F3", "x", edits("plugins/f.py", "z", old="not there"))
    assert bad["ok"] is False and "exactly once" in bad["error"]


def test_agent_can_propose_but_the_tool_cannot_apply(fake):
    assert not any("apply" in n or "approve_patch" in n for n in tools.REGISTRY)
    fake.script = [Response(tool_calls=[ToolCall("1", "propose_patch", {"title": "Adder", "summary": "adds", "edits": json.dumps(edits())})]), Response(text="Proposed.")]
    run(Agent().run("make me an adder tool"))
    p = patching.list_patches()[0]
    assert p["status"] == "ready" and not (paths.plugins_dir() / "adder.py").exists()
    result = json.loads(fake.calls[1]["messages"][-1]["content"])
    assert "NOT applied" in result["message"]


def test_agent_cannot_read_core_code_or_secrets_with_code_read():
    assert tools.call_sync("code_read", {"path": "src/nanoagent/drafts.py"})[1] is False
    assert tools.call_sync("code_read", {"path": "secrets.toml"})[1] is False
    assert "propose_patch" in tools.REGISTRY and tools.REGISTRY["propose_patch"].safety == "prepare"
