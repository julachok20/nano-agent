"""The gateway: owner-only auth on EVERY route (structural + live), login flow, chat, LINE webhook and approval taps."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from nanoagent import config, db, drafts, keystore
from nanoagent.gateway import auth, line
from nanoagent.gateway.app import PUBLIC, create_app, dump_routes
from nanoagent.providers import Response, ToolCall

TOKEN = "owner-token-for-tests-only-0123456789"   # scan:allow  (same value as conftest)


@pytest.fixture
def app(cfg_fake):
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, base_url="http://testserver")


@pytest.fixture
def owner(client):
    assert client.post("/api/login", json={"token": TOKEN}).status_code == 200
    return client


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


# ---------------------------------------------------------------- auth coverage (the rule: owner-only on every route)

def test_every_route_is_owner_only_or_explicitly_public(app):
    routes = dump_routes(app)
    assert routes, "no routes found"
    public_seen = set()
    for r in app.routes:
        methods = [m for m in getattr(r, "methods", []) or [] if m not in ("HEAD", "OPTIONS")]
        for m in methods:
            if (m, r.path) in PUBLIC:
                public_seen.add((m, r.path))
                continue
            calls = [d.call for d in r.dependant.dependencies]
            assert auth.require_owner in calls, f"{m} {r.path} is not protected by require_owner"
    assert public_seen == PUBLIC, "PUBLIC list and real routes differ: " + str(PUBLIC ^ public_seen)


def test_unauthenticated_requests_get_401_everywhere(app, client):
    for m, path in dump_routes(app):
        if (m, path) in PUBLIC:
            continue
        resp = client.request(m, _fill(path), json={} if m != "GET" else None)
        assert resp.status_code == 401, f"{m} {path} answered {resp.status_code} without login"


def test_wrong_cookie_and_wrong_bearer_are_refused(client):
    client.cookies.set(auth.COOKIE, "0" * 64)
    assert client.get("/api/me").status_code == 401
    client.cookies.clear()
    assert client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


def test_public_routes_carry_no_private_data(client):
    assert client.get("/healthz").json().keys() == {"ok", "version"}
    page = client.get("/console").text
    assert "nano Agent" in page and TOKEN not in page
    strings = client.get("/api/strings").json()
    assert strings["lang"] == "en" and "login_title" in strings["strings"]
    assert "Alex" not in json.dumps(strings)


def test_security_headers_and_static_whitelist(client):
    r = client.get("/console")
    assert r.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in r.headers["content-security-policy"]
    assert client.get("/static/console.js").status_code == 200
    assert client.get("/static/dashboard.css").headers["content-type"].startswith("text/css")
    assert client.get("/static/../config.py").status_code in (404, 422)
    assert client.get("/static/secrets.toml").status_code == 404
    assert client.get("/api/me").headers.get("cache-control") == "no-store"


def test_console_js_never_uses_dangerous_dom_apis():
    js = (Path(__file__).parents[1] / "src/nanoagent/gateway/static/console.js").read_text(encoding="utf-8")
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert bad not in js, f"console.js uses {bad}"


# ---------------------------------------------------------------- login

def test_login_cookie_flow_and_logout(client):
    assert client.post("/api/login", json={"token": "wrong"}).status_code == 401
    r = client.post("/api/login", json={"token": TOKEN})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert client.get("/api/me").json()["owner_name"] == "Alex"
    assert client.post("/api/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401


def test_login_is_rate_limited(client):
    auth._FAILS.clear()
    codes = [client.post("/api/login", json={"token": f"bad{i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    auth._FAILS.clear()


def test_cross_origin_mutation_is_refused(owner):
    r = owner.post("/api/tasks", json={"title": "x"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert owner.post("/api/tasks", json={"title": "x"}, headers={"Origin": "http://testserver"}).status_code == 200


def test_liff_login_requires_owner_subject(client, monkeypatch):
    cfg = config.load()
    cfg["line"].update(liff_id="1234567890-AbCdEfGh", owner_user_id="U" + "a" * 32)   # scan:allow
    config.save(cfg)

    def handler(req):
        sub = "U" + "a" * 32 if b"good" in req.content else "U" + "b" * 32   # scan:allow
        return httpx.Response(200, json={"sub": sub})
    line.TRANSPORT = httpx.MockTransport(handler)
    try:
        assert client.post("/api/login/liff", json={"idToken": "good"}).status_code == 200
        client.cookies.clear()
        assert client.post("/api/login/liff", json={"idToken": "other"}).status_code == 401
    finally:
        line.TRANSPORT = None


# ---------------------------------------------------------------- the API works end to end

def test_all_get_routes_answer_json_for_the_owner(app, owner):
    for m, path in dump_routes(app):
        if m != "GET" or path in ("/static/{name}", "/console", "/", "/api/voice/tts") or "{" in path:
            continue
        r = owner.get(path)
        assert r.status_code == 200, f"GET {path} -> {r.status_code}"
        if path.startswith("/api"):
            r.json()


def test_chat_task_memory_draft_approval_through_the_api(owner, fake):
    sent = []

    async def sender(t, x):
        sent.append((t, x))
    drafts.register_sender("line", sender)
    fake.script = [Response(tool_calls=[ToolCall("1", "add_task", {"title": "pay rent", "due": "+1d"}), ToolCall("2", "remember", {"text": "I live in Chiang Mai"}),
                                       ToolCall("3", "prepare_message", {"channel": "line", "target": "Ufriend", "text": "Running late"})]), Response(text="All done.")]
    r = owner.post("/api/chat", json={"text": "do three things"}).json()
    assert r["ok"] and r["text"] == "All done." and [t["name"] for t in r["tools"]] == ["add_task", "remember", "prepare_message"]
    assert r["new_drafts"][0]["status"] == "pending" and "code" not in r["new_drafts"][0] and sent == []
    assert owner.get("/api/tasks").json()["tasks"][0]["title"] == "pay rent"
    assert owner.get("/api/memory").json()["items"][0]["text"] == "I live in Chiang Mai"
    did = r["new_drafts"][0]["id"]
    assert owner.post(f"/api/drafts/{did}/approve").json()["ok"] and sent == [("Ufriend", "Running late")]
    assert owner.post(f"/api/drafts/{did}/approve").json()["ok"] is False
    assert owner.post("/api/chat", json={"text": ""}).status_code == 400


def test_skills_learning_automation_and_settings_routes(owner):
    assert owner.post("/api/skills", json={"name": "greet", "description": "Say hello", "body": "Say hello nicely."}).json()["ok"]
    assert owner.post("/api/skills/import", json={"kind": "text", "text": "---\nname: ext\ndescription: d\n---\nbody"}).json()["results"][0]["ok"]
    assert owner.post("/api/skills/ext/toggle", json={"enabled": True}).json()["ok"] is False   # needs the review ack
    assert owner.post("/api/skills/ext/toggle", json={"enabled": True, "ack": True}).json()["ok"]
    assert owner.post("/api/learning/pref", json={"setting": "ui.accent", "value": "violet"}).json()["ok"]
    assert owner.get("/api/me").json()["prefs"]["ui.accent"] == "violet"
    assert owner.post("/api/learning/pref", json={"setting": "ui.accent", "value": "evil"}).json()["ok"] is False
    assert owner.post("/api/automations", json={"name": "n", "prompt": "p", "schedule": {"daily": "08:00"}}).json()["ok"]
    assert owner.post("/api/settings", json={"language": "th", "owner_name": "Sam", "timezone": "Asia/Bangkok"}).json()["ok"]
    assert owner.post("/api/settings", json={"timezone": "Nowhere/City"}).status_code == 400
    from nanoagent import i18n
    i18n.set_language(None)   # the test fixture pins English; the running gateway never does
    assert owner.get("/api/strings").json()["lang"] == "th"
    assert owner.post("/api/models/test").json()["ok"] is True


def test_system_page_is_generic(owner):
    body = json.dumps(owner.get("/api/system").json())
    for personal in ("spark", "tail0", "vllm", "gemma", "litellm", "hermes"):
        assert personal not in body.lower()


# ---------------------------------------------------------------- LINE connector

SECRET = "line-secret-for-tests"   # scan:allow
OWNER = "U" + "1" * 32   # scan:allow


def sign(body: bytes) -> str:
    return base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()


def msg_event(text: str, uid: str = OWNER, token: str = "rt") -> dict:
    return {"events": [{"type": "message", "replyToken": token, "source": {"type": "user", "userId": uid}, "message": {"type": "text", "text": text}}]}


@pytest.fixture
def linectx(client, fake):
    cfg = config.load()
    cfg["line"].update(enabled=True, owner_user_id=OWNER)
    config.save(cfg)
    keystore.set_("line.channel_secret", SECRET)
    keystore.set_("line.channel_token", "line-access-token-for-tests")   # scan:allow
    api = []

    def handler(req: httpx.Request):
        api.append((req.url.path, json.loads(req.content), req.headers["authorization"]))
        return httpx.Response(200, json={})
    line.TRANSPORT = httpx.MockTransport(handler)
    line.register()
    yield api
    line.TRANSPORT = None
    drafts.SENDERS.pop("line", None)


def post(client, payload: dict, sig: str | None = None):
    body = json.dumps(payload).encode()
    return client.post("/webhook/line", content=body, headers={"x-line-signature": sig if sig is not None else sign(body), "content-type": "application/json"})


def test_webhook_rejects_bad_or_missing_signature(client, linectx):
    assert post(client, msg_event("hi"), sig="bad").status_code == 403
    assert post(client, msg_event("hi"), sig="").status_code == 403
    assert linectx == []


def test_owner_message_goes_to_the_agent_and_is_answered_by_reply(client, linectx):
    assert post(client, msg_event("hello bot")).status_code == 200
    path, body, auth_h = linectx[0]
    assert path == "/v2/bot/message/reply" and body["replyToken"] == "rt" and body["messages"][0]["text"] == "[fake] hello bot" and auth_h.startswith("Bearer ")


def test_stranger_gets_total_silence(client, linectx):
    assert post(client, msg_event("hi", uid="U" + "9" * 32)).status_code == 200   # scan:allow
    assert linectx == [] and db.q("SELECT * FROM messages") == []


def test_pairing_binds_only_with_the_one_time_code(client, linectx):
    cfg = config.load()
    cfg["line"]["owner_user_id"] = ""
    config.save(cfg)
    code = line.new_pair_code()
    stranger = "U" + "7" * 32   # scan:allow
    post(client, msg_event("pair 000000", uid=stranger))
    assert config.load()["line"]["owner_user_id"] == "" and linectx == []
    post(client, msg_event(f"pair {code}", uid=stranger))
    assert config.load()["line"]["owner_user_id"] == stranger and "Paired" in linectx[0][1]["messages"][0]["text"]
    post(client, msg_event(f"pair {code}", uid="U" + "8" * 32))   # scan:allow
    assert config.load()["line"]["owner_user_id"] == stranger   # code is single-use


def test_agent_draft_gets_quick_reply_buttons_and_tap_sends(client, linectx, fake):
    fake.script = [Response(tool_calls=[ToolCall("1", "prepare_message", {"channel": "line", "target": "Ufriend", "text": "On my way"})]), Response(text="I drafted it.")]
    post(client, msg_event("tell Sam I'm on my way"))
    reply = linectx[0][1]["messages"][-1]
    labels = [i["action"]["text"] for i in reply["quickReply"]["items"]]
    send_text = [t for t in labels if t.startswith("send #")][0]
    assert not any(c[0] == "/v2/bot/message/push" for c in linectx)   # nothing sent yet
    post(client, msg_event(send_text, token="rt2"))
    pushes = [c for c in linectx if c[0] == "/v2/bot/message/push"]
    assert pushes[0][1]["to"] == "Ufriend" and pushes[0][1]["messages"][0]["text"] == "On my way"
    post(client, msg_event(send_text, token="rt3"))   # a second tap sends nothing more
    assert len([c for c in linectx if c[0] == "/v2/bot/message/push"]) == 1


def test_wrong_code_tap_does_not_send_and_cancel_works(client, linectx):
    d = drafts.prepare("line", "Ux", "secret plan")
    post(client, msg_event(f"send #{d['id']} 000000"))
    assert not [c for c in linectx if c[0] == "/v2/bot/message/push"] and drafts.get(d["id"])["status"] == "pending"
    post(client, msg_event(f"cancel #{d['id']}"))
    assert drafts.get(d["id"])["status"] == "cancelled"


def test_console_command_returns_link_without_token(client, linectx):
    post(client, msg_event("console"))
    txt = linectx[0][1]["messages"][0]["text"]
    assert "/console" in txt and TOKEN not in txt


def test_slow_agent_falls_back_to_push_when_reply_token_expired(client, linectx):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(400 if req.url.path.endswith("/reply") else 200, json={})
    line.TRANSPORT = httpx.MockTransport(handler)
    post(client, msg_event("hi"))
    assert calls == ["/v2/bot/message/reply", "/v2/bot/message/push"]
