"""Optional MCP stdio server (extra `[mcp]`): exposes the same tool registry to Hermes, Claude Desktop or any MCP client.

    nano-agent mcp

The registry functions are registered one by one; nothing here imports the agent loop. Approval-first still holds:
`prepare_message` makes a draft, and there is no tool that sends. EXPERIMENTAL in v0.1 (the `mcp` package API moves).
"""
from __future__ import annotations

import inspect


def build():
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError:
        try:
            from mcp.server.mcpserver import MCPServer as FastMCP  # type: ignore
        except ImportError:
            raise SystemExit("Install the MCP extra first: pip install 'nano-agent[mcp]'") from None
    from .. import paths, tools

    paths.ensure_dirs()
    server = FastMCP("nano-agent")
    for name, t in sorted(tools.REGISTRY.items()):
        fn = t.fn

        async def runner(_fn=fn, _name=name, **kw):
            text, _ok = await tools.call(_name, kw)
            return text
        runner.__name__ = name
        runner.__doc__ = t.description
        runner.__signature__ = inspect.signature(fn)  # type: ignore[attr-defined]
        runner.__annotations__ = dict(getattr(fn, "__annotations__", {}))
        server.tool(name=name, description=t.description)(runner)
    return server


def main() -> None:
    build().run()
