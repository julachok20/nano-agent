"""OpenAI-compatible chat completions: OpenAI, OpenRouter, Groq, Together, DeepSeek, vLLM, LM Studio, Ollama's /v1,
and anything else that speaks POST {base_url}/chat/completions."""
from __future__ import annotations

import json

from .base import Provider, Response, ToolCall, parse_args


def _content(parts):
    if isinstance(parts, str):
        return parts
    out = []
    for p in parts:
        if p.get("type") == "image":
            out.append({"type": "image_url", "image_url": {"url": f"data:{p['mime']};base64,{p['data']}"}})
        else:
            out.append({"type": "text", "text": p.get("text", "")})
    return out


def to_wire(messages: list[dict], system: str | None) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m["role"]
        if role == "assistant" and m.get("tool_calls"):
            out.append({
                "role": "assistant", "content": m.get("content") or None,
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c.get("args") or {})}} for c in m["tool_calls"]],
            })
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"] if isinstance(m["content"], str) else str(m["content"])})
        else:
            out.append({"role": role, "content": _content(m["content"])})
    return out


class OpenAICompatProvider(Provider):
    kind = "openai"

    async def chat(self, model, messages, tools=None, system=None, temperature=None, max_tokens=None) -> Response:
        payload: dict = {"model": model, "messages": to_wire(messages, system)}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = await self._post(f"{self.base_url}/chat/completions", headers, payload)
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError, TypeError):
            from .base import ProviderError
            raise ProviderError("The reply had no choices.", "Check the model id and base URL.", kind="bad_response") from None
        calls = [ToolCall(c.get("id") or f"call_{i}", c["function"]["name"], parse_args(c["function"].get("arguments")))
                 for i, c in enumerate(msg.get("tool_calls") or [])]
        u = data.get("usage") or {}
        return Response(text=(msg.get("content") or "").strip(), tool_calls=calls,
                        usage={"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}, stop=choice.get("finish_reason") or "")
