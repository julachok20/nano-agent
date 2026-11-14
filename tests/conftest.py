"""Shared fixtures. Every test runs against a throw-away NANO_AGENT_HOME with synthetic data: it never touches a real home."""
from __future__ import annotations

import asyncio

import pytest

from nano_agent import config, db, keystore, paths
from nano_agent.providers import FakeProvider
from nano_agent.providers import base as pbase


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("NANO_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NANO_ACTIVITY_OFF", "")
    monkeypatch.delenv("NANO_SECRET_OWNER_TOKEN", raising=False)
    monkeypatch.setattr(paths, "pointer_file", lambda: tmp_path / "pointer")
    db.reset_cache()
    paths.ensure_dirs()
    from nano_agent import i18n
    i18n.set_language("en")
    yield tmp_path / "home"
    db.reset_cache()


@pytest.fixture
def cfg_fake(home):
    """A configured install that uses the fake model."""
    cfg = config.load()
    cfg["general"].update(owner_name="Alex", timezone="UTC")
    cfg["providers"]["fake"] = {"kind": "fake", "base_url": "fake://", "key_ref": "provider.fake"}
    cfg["models"].update(chat="fake/fake-1", fast="fake/fake-1")
    config.save(cfg)
    keystore.set_("owner.token", "owner-token-for-tests-only-0123456789")   # scan:allow
    return cfg


@pytest.fixture
def fake(monkeypatch, cfg_fake):
    """The singleton FakeProvider the agent will use, so a test can script it."""
    from nano_agent import providers
    providers._FAKE_SINGLETONS.clear()
    p = providers.make_provider(config.load(), "fake")
    return p


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def no_transport():
    old = pbase.DEFAULT_TRANSPORT
    yield
    pbase.DEFAULT_TRANSPORT = old


__all__ = ["run", "FakeProvider"]
