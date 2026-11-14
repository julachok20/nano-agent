"""Tool registry. A tool is a plain Python function with a decorator; nothing here imports the agent loop, so the same
tools serve the loop, the console API and the optional MCP server.

    @tool("What it does", safety="read", untrusted=False, params={"text": "what text is"})
    def my_tool(text: str, count: int = 1) -> dict: ...

`safety` is documentation the code relies on:
    read     reads local data
    write    changes local data (memory, tasks, preferences)
    prepare  prepares something for the owner to approve (a draft, a patch): never performs it
    external reads from outside the machine (web)
`untrusted=True` marks results that contain third-party text (web pages): the agent wraps them as data.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

from .. import activity


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable
    parameters: dict
    safety: str = "read"
    untrusted: bool = False
    track: str = ""
    extra: dict = field(default_factory=dict)

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


REGISTRY: dict[str, Tool] = {}


def _json_type(ann: Any) -> dict:
    origin = typing.get_origin(ann)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return _json_type(args[0]) if args else {"type": "string"}
    if origin in (list, typing.List):
        a = typing.get_args(ann)
        return {"type": "array", "items": _json_type(a[0]) if a else {"type": "string"}}
    if ann is bool:
        return {"type": "boolean"}
    if ann is int:
        return {"type": "integer"}
    if ann is float:
        return {"type": "number"}
    if origin is dict or ann is dict:
        return {"type": "object"}
    return {"type": "string"}


def tool(description: str, name: str | None = None, safety: str = "read", untrusted: bool = False,
         params: dict[str, str] | None = None, track: str = ""):
    def deco(fn: Callable) -> Callable:
        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn)
        props, required = {}, []
        for pname, p in sig.parameters.items():
            if pname.startswith("_"):
                continue
            spec = _json_type(hints.get(pname, str))
            if params and pname in params:
                spec["description"] = params[pname]
            props[pname] = spec
            if p.default is inspect.Parameter.empty:
                required.append(pname)
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        t = Tool(name or fn.__name__, description, fn, schema, safety, untrusted, track)
        REGISTRY[t.name] = t
        fn.tool = t  # type: ignore[attr-defined]
        return fn
    return deco


def schemas(exclude: set[str] | None = None) -> list[dict]:
    return [t.schema() for n, t in sorted(REGISTRY.items()) if not exclude or n not in exclude]


async def call(name: str, args: dict | None, max_chars: int = 6000) -> tuple[str, bool]:
    """Run a tool. Returns (text for the model, ok). Never raises: errors become text the model can read."""
    t = REGISTRY.get(name)
    if not t:
        return json.dumps({"ok": False, "error": f"unknown tool '{name}'"}), False
    args = {k: v for k, v in (args or {}).items() if not k.startswith("_")}
    try:
        inspect.signature(t.fn).bind(**args)
    except TypeError as e:
        return json.dumps({"ok": False, "error": f"bad arguments: {e}"}), False
    aid = activity.start("tool", f"{t.track or name}") if t.track else 0
    try:
        res = t.fn(**args)
        if inspect.isawaitable(res):
            res = await res
        ok = not (isinstance(res, dict) and (res.get("ok") is False or "error" in res))
        activity.finish(aid, ok, res.get("error", "") if isinstance(res, dict) and not ok else "")
    except Exception as e:  # a failing tool must not break the loop
        from .. import keystore
        activity.finish(aid, False, type(e).__name__)
        return json.dumps({"ok": False, "error": f"{type(e).__name__}: {keystore.redact(e)[:200]}"}), False
    text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + f"... [truncated {len(text) - max_chars} chars]"
    return text, ok


def call_sync(name: str, args: dict | None = None) -> tuple[str, bool]:
    return asyncio.run(call(name, args))


def load_plugins() -> list[str]:
    """Import data/plugins/*.py so approved patches and the owner's own tools register themselves. Failures are reported, not raised."""
    from .. import paths

    loaded = []
    for p in sorted(paths.plugins_dir().glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"nano_plugin_{p.stem}", p)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            loaded.append(p.name)
        except Exception as e:
            loaded.append(f"{p.name} (FAILED: {type(e).__name__})")
    return loaded


from . import core, self_tools, web  # noqa: E402,F401  (registers the built-in tools)
