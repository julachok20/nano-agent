"""Owner-only API for the sandbox workspace (N8 to N10). Mounted in app.py behind `require_owner`, so the agent and the
public routes cannot reach it. The console buttons are NOT built here (see docs/N8_UI_TODO.md): this is the API only.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import sandbox_ws as ws
from .. import supervisor as sv

router = APIRouter(prefix="/sandbox")

ACTIONS = {"start": "session_start", "pause": "pause", "resume": "resume", "stop": "stop", "kill": "kill", "review": "review"}


@router.get("/status")
def status() -> dict:
    st = sv.read_state()
    return {"config": ws.status(),
            "supervisor": {k: st[k] for k in ("state", "lease_until", "session_until", "trip", "reviewed", "freeze_ms", "kill_latency_ms")},
            "events": st.get("events", [])[-20:], "audit_chain_ok": ws.verify_chain()[0]}


@router.get("/audit")
def audit(limit: int = 200) -> dict:
    return {"rows": ws.audit_rows(limit=max(1, min(int(limit), 1000)))}


@router.post("/rollback")
async def rollback(request: Request):
    body = await request.json() if (request.headers.get("content-type") or "").startswith("application/json") else {}
    snap = str((body or {}).get("snapshot", ""))
    if not snap:
        return JSONResponse({"ok": False, "error": "snapshot id required"}, status_code=400)
    return sv.command("rollback", snap)


@router.post("/{action}")
def action(action: str):
    if action not in ACTIONS:
        return JSONResponse({"ok": False, "error": "unknown action"}, status_code=404)
    return sv.command(ACTIONS[action])
