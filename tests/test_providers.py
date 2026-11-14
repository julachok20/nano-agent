"""Provider adapters against a mocked HTTP layer: wire formats, tool calls, error messages, and that keys never leak."""
from __future__ import annotations

import json

import httpx
import pytest

from nanoagent import config, keystore
from nanoagent.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAICompatProvider,
    ProviderError,
    Response,
    make_provider,
)
from nanoagent.providers.base import explain_status

from .conftest import run

KEY = "sk-" + "A1b2C3d4" * 4   # scan:allow
TOOLS = [{"name": "add_task", "description": "add", "parameters": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}}]
MSGS = [{"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "add_task", "args": {"title": "x"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "add_task", "content": "{\"ok\": true}"}]


def mock(handler):
    return httpx.MockTransport(handler)


def test_openai_roundtrip_and_tool_calls():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "", "tool_calls": [{"id": "t1", "function": {"name": "add_task", "arguments": "{\"title\": \"milk\"}"}}]}, "finish_reason": "tool_calls"}],
                                         "usage": {"prompt_tokens": 5, "completion_tokens": 2}})
    p = OpenAICompatProvider("o", "https://api.example.com/v1/", KEY, transport=mock(handler))
    r = run(p.chat("gpt-x", MSGS, tools=TOOLS, system="sys"))
    assert seen["url"] == "https://api.example.com/v1/chat/completions" and seen["auth"] == "Bearer " + KEY
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["messages"][2]["tool_calls"][0]["function"]["arguments"] == "{\"title\": \"x\"}"
    assert seen["body"]["messages"][3]["role"] == "tool" and seen["body"]["tools"][0]["function"]["name"] == "add_task"
    assert r.tool_calls[0].name == "add_task" and r.tool_calls[0].args == {"title": "milk"} and r.usage == {"in": 5, "out": 2}


def test_openai_no_key_for_local_server():
    def handler(req):
        assert "authorization" not in req.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    assert run(OpenAICompatProvider("l", "http://localhost:1234/v1", "", transport=mock(handler)).chat("m", [{"role": "user", "content": "x"}])).text == "ok"


def test_anthropic_wire_format():
    seen = {}

    def handler(req):
        seen["h"], seen["body"] = req.headers, json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hello"}, {"type": "tool_use", "id": "u1", "name": "add_task", "input": {"title": "a"}}], "usage": {"input_tokens": 3, "output_tokens": 4}, "stop_reason": "tool_use"})
    r = run(AnthropicProvider("a", "https://api.anthropic.com/v1", KEY, transport=mock(handler)).chat("claude-x", MSGS, tools=TOOLS, system="be brief"))
    assert seen["h"]["x-api-key"] == KEY and seen["h"]["anthropic-version"]
    b = seen["body"]
    assert b["system"] == "be brief" and b["max_tokens"] >= 1 and b["tools"][0]["input_schema"]["type"] == "object"
    assert b["messages"][1]["content"][0]["type"] == "tool_use" and b["messages"][2]["content"][0]["type"] == "tool_result"
    assert r.text == "hello" and r.tool_calls[0].args == {"title": "a"}


def test_gemini_key_in_header_not_url():
    seen = {}

    def handler(req):
        seen["url"], seen["h"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"functionCall": {"name": "add_task", "args": {"title": "z"}}}]}}]})
    tools = [{"name": "t", "description": "d", "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "additionalProperties": False}}]
    r = run(GeminiProvider("g", "https://generativelanguage.googleapis.com/v1beta", KEY, transport=mock(handler)).chat("gemini-x", MSGS, tools=tools, system="s"))
    assert KEY not in seen["url"] and seen["h"]["x-goog-api-key"] == KEY and seen["url"].endswith("models/gemini-x:generateContent")
    decl = seen["body"]["tools"][0]["functionDeclarations"][0]
    assert "additionalProperties" not in json.dumps(decl) and decl["parameters"]["type"] == "OBJECT"
    assert seen["body"]["contents"][1]["parts"][0]["functionCall"]["name"] == "add_task" and seen["body"]["contents"][2]["parts"][0]["functionResponse"]["name"] == "add_task"
    assert r.tool_calls[0].name == "add_task"


def test_ollama_native():
    def handler(req):
        assert str(req.url).endswith("/api/chat") and json.loads(req.content)["stream"] is False
        return httpx.Response(200, json={"message": {"content": "hi", "tool_calls": [{"function": {"name": "add_task", "arguments": {"title": "q"}}}]}, "prompt_eval_count": 4, "eval_count": 6})
    r = run(OllamaProvider("o", "http://localhost:11434", "", transport=mock(handler)).chat("llama3", MSGS, tools=TOOLS))
    assert r.text == "hi" and r.tool_calls[0].args == {"title": "q"} and r.usage == {"in": 4, "out": 6}


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "auth"), (404, "not_found"), (429, "rate_limit"), (400, "bad_request"), (500, "server")])
def test_http_errors_are_explained(status, kind):
    e = explain_status(status, "boom " + KEY, "https://x/v1")
    assert e.kind == kind and e.hint and KEY not in str(e)


def test_error_text_never_contains_the_key():
    def handler(req):
        return httpx.Response(401, text="invalid key " + KEY)
    p = OpenAICompatProvider("o", "https://x/v1", KEY, transport=mock(handler))
    ok, msg = run(p.ping("m"))
    assert not ok and KEY not in msg and "rejected the API key" in msg


def test_connect_error_and_not_json():
    def boom(req):
        raise httpx.ConnectError("no route")
    ok, msg = run(OpenAICompatProvider("o", "http://localhost:9/v1", "", transport=mock(boom)).ping("m"))
    assert not ok and "Cannot connect" in msg
    ok, msg = run(OpenAICompatProvider("o", "http://x/v1", "", transport=mock(lambda r: httpx.Response(200, text="<html>"))).ping("m"))
    assert not ok and "not JSON" in msg


def test_ping_ok():
    p = OpenAICompatProvider("o", "https://x/v1", KEY, transport=mock(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})))
    assert run(p.ping("m")) == (True, "ok")


def test_retries_on_429_then_succeeds(monkeypatch):
    calls = []

    async def nosleep(_):
        return None
    monkeypatch.setattr("nanoagent.providers.base.asyncio.sleep", nosleep)

    def handler(req):
        calls.append(1)
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"choices": [{"message": {"content": "fine"}}]})
    assert run(OpenAICompatProvider("o", "https://x/v1", "k", transport=mock(handler)).chat("m", [{"role": "user", "content": "x"}])).text == "fine" and len(calls) == 3


def test_make_provider_reads_secret_and_roles(home):
    cfg = config.load()
    cfg["providers"]["main"] = {"kind": "openai", "base_url": "https://x/v1", "key_ref": "provider.main"}
    cfg["models"]["chat"] = "main/gpt-x"
    keystore.set_("provider.main", KEY)
    from nanoagent.providers import for_role
    prov, model = for_role(cfg, "fast")   # fast falls back to chat
    assert model == "gpt-x" and prov.api_key == KEY and prov.kind == "openai"
    with pytest.raises(ProviderError):
        make_provider(cfg, "nope")
    with pytest.raises(ProviderError):
        for_role(config.load() | {"models": {"chat": "", "fast": "", "vision": ""}}, "chat")


def test_response_dataclass_defaults():
    assert Response().text == "" and Response().tool_calls == []
