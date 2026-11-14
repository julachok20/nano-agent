"""Ollama native API (/api/chat). Ollama also speaks the OpenAI format at /v1 (use the `openai` kind for that); this
adapter uses the native endpoint, which needs no key and reports clearer errors for models that are not pulled yet."""
from __future__ import annotations

from .base import Provider, ProviderError, Response, ToolCall, text_of


def to_wire(messages: list[dict], system: str | None) -> list[dict]:
    out: list[dict] = [{"role": "system", "content": system}] if system else []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": text_of(m.get("content")),
                        "tool_calls": [{"function": {"name": c["name"], "arguments": c.get("args") or {}}} for c in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": text_of(m["content"]), "tool_name": m.get("name", "")})
        else:
            c = m["content"]
            msg = {"role": m["role"], "content": text_of(c)}
            if not isinstance(c, str):
                imgs = [p["data"] for p in c if p.get("type") == "image"]
                if imgs:
                    msg["images"] = imgs
            out.append(msg)
    return out


class OllamaProvider(Provider):
    kind = "ollama"

    async def chat(self, model, messages, tools=None, system=None, temperature=None, max_tokens=None) -> Response:
        payload: dict = {"model": model, "stream": False, "messages": to_wire(messages, system)}
        opts = {}
        if temperature is not None:
            opts["temperature"] = temperature
        if max_tokens:
            opts["num_predict"] = max_tokens
        if opts:
            payload["options"] = opts
        if tools:
            payload["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
        try:
            data = await self._post(f"{self.base_url}/api/chat", {"Content-Type": "application/json"}, payload)
        except ProviderError as e:
            if e.status == 404:
                raise ProviderError(f"Ollama does not know model '{model}'.", f"Run `ollama pull {model}` first, and check the base URL (default http://localhost:11434).", 404, "not_found") from None
            raise
        msg = data.get("message") or {}
        calls = [ToolCall(f"ol_{i}", c["function"]["name"], c["function"].get("arguments") or {}) for i, c in enumerate(msg.get("tool_calls") or [])]
        return Response(text=(msg.get("content") or "").strip(), tool_calls=calls,
                        usage={"in": data.get("prompt_eval_count", 0), "out": data.get("eval_count", 0)}, stop=data.get("done_reason") or "")
