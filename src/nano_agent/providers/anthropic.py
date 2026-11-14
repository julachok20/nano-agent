"""Anthropic Messages API (Claude)."""
from __future__ import annotations

from .base import Provider, Response, ToolCall, text_of

API_VERSION = "2023-06-01"


def _blocks(content):
    if isinstance(content, str):
        return content
    out = []
    for p in content:
        if p.get("type") == "image":
            out.append({"type": "image", "source": {"type": "base64", "media_type": p["mime"], "data": p["data"]}})
        else:
            out.append({"type": "text", "text": p.get("text", "")})
    return out


def to_wire(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue  # handled through the top-level `system` field
        if role == "assistant":
            blocks: list[dict] = []
            if (t := text_of(m.get("content"))):
                blocks.append({"type": "text", "text": t})
            for c in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["name"], "input": c.get("args") or {}})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": " "}]})
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": text_of(m["content"])}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                out[-1]["content"].append(block)   # all results of one assistant turn go in one user message
            else:
                out.append({"role": "user", "content": [block]})
        else:
            out.append({"role": "user", "content": _blocks(m["content"])})
    return out


class AnthropicProvider(Provider):
    kind = "anthropic"

    async def chat(self, model, messages, tools=None, system=None, temperature=None, max_tokens=None) -> Response:
        sys_text = "\n\n".join(x for x in [system or "", *[text_of(m["content"]) for m in messages if m["role"] == "system"]] if x)
        payload: dict = {"model": model, "max_tokens": max_tokens or 2048, "messages": to_wire(messages)}
        if sys_text:
            payload["system"] = sys_text
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
        headers = {"x-api-key": self.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"}
        data = await self._post(f"{self.base_url}/messages", headers, payload)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        calls = [ToolCall(b["id"], b["name"], b.get("input") or {}) for b in data.get("content", []) if b.get("type") == "tool_use"]
        u = data.get("usage") or {}
        return Response(text=text, tool_calls=calls, usage={"in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0)}, stop=data.get("stop_reason") or "")
