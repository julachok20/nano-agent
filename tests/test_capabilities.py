"""Capability requests (addendum section 6, tests 14-18, 20-21): refused by default, one-time codes, deny and expiry."""
import pytest

from nanoagent import capabilities as cap


@pytest.fixture
def connector(monkeypatch):
    monkeypatch.setitem(cap.REGISTRY, "demo", {"actions": {"list": {"mode": "read"}, "send": {"mode": "write"}}})
    return "demo"


def _code(rid):
    return next(x for x in cap.pending() if x["id"] == rid)["code"]


def test_unknown_connector_is_refused_and_logged():
    r = cap.request("nope", ["list"], "read", "need it")
    assert r["ok"] is False and r["error"] == "unknown connector"
    assert cap.db.q("SELECT status FROM capability_requests WHERE connector='nope'")[0]["status"] == "refused"


def test_unknown_action_is_refused(connector):
    assert cap.request(connector, ["delete_all"], "read", "need it")["error"] == "unknown action"


def test_read_scope_cannot_hold_a_write_action(connector):
    assert cap.request(connector, ["send"], "read", "need it")["error"] == "read scope cannot include write actions"


def test_request_is_pending_and_grants_nothing(connector):
    r = cap.request(connector, ["list"], "read", "need the list to answer")
    assert r["ok"] and not cap.granted(connector, "list")
    assert next(x for x in cap.pending() if x["id"] == r["id"])["status"] == "pending"


def test_wrong_or_missing_code_does_nothing(connector):
    rid = cap.request(connector, ["list"], "read", "need it")["id"]
    wrong = "000000" if _code(rid) != "000000" else "111111"
    assert cap.allow(rid, "")["ok"] is False
    assert cap.allow(rid, wrong)["ok"] is False
    assert not cap.granted(connector, "list")


def test_allow_with_the_code_grants_once(connector):
    rid = cap.request(connector, ["list"], "read", "need it")["id"]
    code = _code(rid)
    assert cap.allow(rid, code)["ok"] is True
    assert cap.granted(connector, "list")
    assert cap.allow(rid, code)["ok"] is False   # one-time: reuse is refused


def test_deny_grants_nothing_and_cannot_be_reversed(connector):
    rid = cap.request(connector, ["list"], "read", "need it")["id"]
    code = _code(rid)
    assert cap.deny(rid, code)["ok"] is True
    assert not cap.granted(connector, "list")
    assert cap.allow(rid, code)["ok"] is False   # already decided: no second decision


def test_expired_request_cannot_be_allowed(connector, monkeypatch):
    rid = cap.request(connector, ["list"], "read", "need it")["id"]
    code = _code(rid)
    real = cap.time.time
    monkeypatch.setattr(cap.time, "time", lambda: real() + cap.CODE_TTL + 1)
    assert cap.allow(rid, code)["ok"] is False
    monkeypatch.undo()
    assert not cap.granted(connector, "list")


def test_reason_is_stored_as_data(connector):
    hostile = "<img src=x onerror=alert(1)> please"
    rid = cap.request(connector, ["list"], "read", hostile)["id"]
    row = next(x for x in cap.pending() if x["id"] == rid)
    assert row["reason"] == hostile and not cap.granted(connector, "list")


def test_listing_routes_are_owner_only():
    from fastapi.testclient import TestClient

    from nanoagent.gateway.app import create_app
    client = TestClient(create_app())
    assert client.get("/api/capabilities").status_code in (401, 403)
    assert client.post("/api/capabilities/1/allow", json={"code": "x"}).status_code in (401, 403)
