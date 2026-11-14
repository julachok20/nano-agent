"""A model that needs no network. Used by tests, CI and `nano-agent setup --provider fake` for trying the console.

Scripted mode: FakeProvider(script=[Response, ...]) returns them in order.
Default mode:  "/tool NAME {json}" in a user message makes a tool call; after a tool result it answers "Done: ..."; any
               other text is echoed back as "[fake] <text>". Deterministic, so end-to-end checks are stable.
"""
from __future__ import annotations

import json
import re

from .base import Provider, Response, ToolCall, text_of


class FakeProvider(Provider):
    kind = "fake"

    def __init__(self, name="fake", base_url="fake://", api_key="", script: list[Response] | None = None, **kw):
        super().__init__(name, base_url, api_key, **kw)
        self.script = list(script or [])
        self.calls: list[dict] = []   # what the agent sent, for assertions

    async def chat(self, model, messages, tools=None, system=None, temperature=None, max_tokens=None) -> Response:
        self.calls.append({"model": model, "messages": messages, "tools": tools, "system": system})
        if self.script:
            return self.script.pop(0)
        last = messages[-1] if messages else {"role": "user", "content": ""}
        if last["role"] == "tool":
            return Response(text="Done: " + text_of(last["content"])[:200])
        text = text_of(last["content"])
        m = re.match(r"/tool\s+(\w+)\s*(\{.*\})?\s*$", text.strip(), re.S)
        if m:
            return Response(tool_calls=[ToolCall("fake_1", m.group(1), json.loads(m.group(2) or "{}"))])
        return Response(text="[fake] " + text[:300], usage={"in": len(text), "out": len(text)})
