"""N9: the constitution is in every agent prompt, the agent cannot change it, and a changed file fails closed."""
from __future__ import annotations

import asyncio
from pathlib import Path

from nanoagent import constitution
from nanoagent import sandbox_ws as ws
from nanoagent.agent import Agent
from nanoagent.providers.fake import FakeProvider

ROOT = Path(__file__).resolve().parents[1]


def test_package_copy_matches_the_repository_constitution():
    assert constitution.text() == (ROOT / "CONSTITUTION.md").read_text(encoding="utf-8")


def test_constitution_is_pinned_and_unchanged():
    assert constitution.verify() is True


def test_constitution_and_precedence_are_in_every_agent_prompt(cfg_fake):
    prompt = Agent(provider=FakeProvider(), model="m").system_prompt("hello")
    assert constitution.text().strip() in prompt
    assert "owner's stop, pause or rollback" in prompt
    assert prompt.index("CONSTITUTION") < prompt.index("Owner:")   # precedence starts before the goal


def test_agent_cannot_write_the_constitution_from_inside(home, monkeypatch, tmp_path):
    before = constitution.digest()
    r = ws.write(str(constitution.path()), "anything goes")
    assert r["ok"] is False
    assert ws.audit_rows(5)[-1]["kind"] == "control_path"
    assert constitution.digest() == before


def test_a_changed_constitution_fails_closed(cfg_fake, monkeypatch):
    monkeypatch.setattr(constitution, "PINNED_SHA256", "0" * 64)
    res = asyncio.run(Agent(provider=FakeProvider(), model="m").run("do anything"))
    assert res.error == "constitution_mismatch"
    assert "did not run" in res.text
