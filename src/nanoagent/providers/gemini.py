"""Google Gemini (generateContent). The key travels in the x-goog-api-key header, never in the URL, so it cannot
end up in access logs or error messages."""
from __future__ import annotations

from .base import Provider, Response, ToolCall, text_of

_DROP = {"additionalProperties", "$schema", "default", "examples", "title"}


def clean_schema(s):
    """Gemini accepts a strict OpenAPI subset of JSON schema."""
    if isinstance(s, dict):
        out = {k: clean_schema(v) for k, v in s.items() if k not in _DROP}
        if "type" in out and isinstance(out["type"], str):
            out["type"] = out["type"].upper()
        return out
    if isinstance(s, list):
        return [clean_schema(x) for x in s]
    return s


def to_wire(messages: list[dict]) -> list[dict]:
    names: dict[str, str] = {}
    out: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "assistant":
            parts: list[dict] = []
            if (t := text_of(m.get("content"))):
                parts.append({"text": t})
            for c in m.get("tool_calls") or []:
                names[c["id"]] = c["name"]
                parts.append({"functionCall": {"name": c["name"], "args": c.get("args") or {}}})
            out.append({"role": "model", "parts": parts or [{"text": " "}]})
        elif role == "tool":
            part = {"functionResponse": {"name": names.get(m["tool_call_id"], m.get("name", "tool")), "response": {"result": text_of(m["content"])}}}
            if out and out[-1]["role"] == "user" and out[-1]["parts"] and "functionResponse" in out[-1]["parts"][0]:
                out[-1]["parts"].append(part)
            else:
                out.append({"role": "user", "parts": [part]})
        else:
            c = m["content"]
            if isinstance(c, str):
                parts = [{"text": c}]
            else:
                parts = [{"inlineData": {"mimeType": p["mime"], "data": p["data"]}} if p.get("type") == "image" else {"text": p.get("text", "")} for p in c]
            out.append({"role": "user", "parts": parts})
    return out


class GeminiProvider(Provider):
    kind = "gemini"

    async def chat(self, model, messages, tools=None, system=None, temperature=None, max_tokens=None) -> Response:
        sys_text = "\n\n".join(x for x in [system or "", *[text_of(m["content"]) for m in messages if m["role"] == "system"]] if x)
        payload: dict = {"contents": to_wire(messages)}
        if sys_text:
            payload["systemInstruction"] = {"parts": [{"text": sys_text}]}
        gen: dict = {}
        if temperature is not None:
            gen["temperature"] = temperature
        if max_tokens:
            gen["maxOutputTokens"] = max_tokens
        if gen:
            payload["generationConfig"] = gen
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t["name"], "description": t["description"], **({"parameters": clean_schema(t["parameters"])} if t["parameters"].get("properties") else {})}
                for t in tools]}]
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        data = await self._post(f"{self.base_url}/models/{model}:generateContent", headers, payload)
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        calls = [ToolCall(f"gc_{i}", p["functionCall"]["name"], p["functionCall"].get("args") or {}) for i, p in enumerate(x for x in parts if "functionCall" in x)]
        u = data.get("usageMetadata") or {}
        return Response(text=text, tool_calls=calls, usage={"in": u.get("promptTokenCount", 0), "out": u.get("candidatesTokenCount", 0)}, stop=cand.get("finishReason") or "")
