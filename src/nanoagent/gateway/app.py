"""The FastAPI application: console page, owner-only JSON API, LINE webhook, health check.

Auth structure (enforced by tests/test_auth_coverage.py): everything under /api is on a router whose dependency is
`require_owner`. The ONLY routes outside it are listed in PUBLIC below, and each of them returns no private data.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import time
import zoneinfo
from contextlib import asynccontextmanager
from importlib import resources

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .. import (
    __version__,
    activity,
    companion,
    config,
    db,
    drafts,
    i18n,
    learning,
    memory,
    outbox,
    patching,
    paths,
    providers,
    projects,
    scheduler,
    skills,
    tasks,
    tools,
    usermodel,
)
from .. import keystore as secrets
from ..agent import Agent
from . import auth, console
from . import line as line_mod

PUBLIC = {("GET", "/healthz"), ("GET", "/console"), ("GET", "/"), ("GET", "/static/{name}"), ("POST", "/api/login"),
          ("POST", "/api/login/liff"), ("GET", "/api/strings"), ("POST", "/webhook/line")}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "script-src 'self' https://static.line-scdn.net; connect-src 'self' https://*.line.me https://*.line-scdn.net; "
                                "media-src 'self' blob:; frame-ancestors 'self'"),
}


def _bad(msg: str, code: int = 400):
    return JSONResponse({"ok": False, "error": msg}, status_code=code)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def system_info() -> dict:
    info = {"os": f"{platform.system()} {platform.release()}", "python": platform.python_version(), "version": __version__, "host": platform.node(),
            "cpu_name": platform.processor(), "cores": os.cpu_count(), "kernel": platform.version(), "arch": platform.machine(),
            "cpu_pct": None, "ram_pct": None, "disk_pct": None, "gpu": None}
    du = shutil.disk_usage(paths.home())
    info["disk_pct"] = round(100 * du.used / du.total, 1)
    info["disk_total_gb"] = round(du.total / 1024**3, 1)
    try:
        import psutil  # type: ignore
        info["cpu_pct"] = psutil.cpu_percent(interval=0.1)
        info["ram_pct"] = psutil.virtual_memory().percent
        info["ram_total_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        info["uptime_hours"] = round((time.time() - psutil.boot_time()) / 3600, 1)
    except Exception:
        pass
    if shutil.which("nvidia-smi"):   # optional: shown only when present
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=3).stdout.strip().splitlines()[0].split(", ")
            info["gpu"] = {"name": out[0], "util_pct": float(out[1]), "mem_used_mb": float(out[2]), "mem_total_mb": float(out[3]), "temp_c": float(out[4])}
        except Exception:
            pass
    return info


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        paths.ensure_dirs()
        auth.owner_token()
        tools.load_plugins()
        line_mod.register()
        stop = asyncio.Event()
        task = asyncio.create_task(scheduler.run_forever(stop))
        yield
        stop.set()
        await task

    app = FastAPI(title="nano Agent", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------- public (no private data) ----------------
    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "version": __version__}

    @app.get("/")
    @app.get("/console")
    async def console_page():
        return HTMLResponse(console.page())

    @app.get("/static/{name}")
    async def static(name: str):
        if name not in ("console.js", "dashboard.css", "favicon.png", "mascot-n.png", "wordmark-light.png", "wordmark-dark.png", "logo-nano-agent-official.webp", "logo-light-theme.png", "logo-dark-theme.png",
                    "mark-n.png", "mascot-n.svg", "subagents.js", "uiblocks.js"):
            raise HTTPException(404)
        data = resources.files("nanoagent").joinpath("gateway", "static", name).read_bytes()
        media_type = ("text/css" if name.endswith(".css") else "application/javascript" if name.endswith(".js")
                      else "image/svg+xml" if name.endswith(".svg") else "image/webp" if name.endswith(".webp") else "image/png")
        return Response(data, media_type=media_type, headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/strings")
    async def strings():
        return {"lang": i18n.language(), "strings": i18n.ui_strings(), "liff_id": config.load()["line"]["liff_id"]}

    @app.post("/api/login")
    async def login(request: Request, response: Response):
        auth.throttle(request)
        if not auth.check_login_token((await _json(request)).get("token", "")):
            auth.record_failure(request)
            return _bad("wrong token", 401)
        auth.login_ok(response, request)
        return {"ok": True}

    @app.post("/api/login/liff")
    async def login_liff(request: Request, response: Response):
        auth.throttle(request)
        sub = await line_mod.verify_liff_id_token((await _json(request)).get("idToken", ""))
        owner = config.load()["line"]["owner_user_id"]
        if not sub or not owner or sub != owner:
            auth.record_failure(request)
            return _bad("not the owner", 401)
        auth.login_ok(response, request)
        return {"ok": True}

    @app.post("/webhook/line")
    async def webhook(request: Request):
        code = await line_mod.handle_webhook(await request.body(), request.headers.get("x-line-signature", ""))
        return PlainTextResponse("ok" if code == 200 else "error", status_code=code)

    # ---------------- owner only ----------------
    api = APIRouter(prefix="/api", dependencies=[Depends(auth.require_owner)])

    @api.post("/logout")
    async def logout(response: Response):
        response.delete_cookie(auth.COOKIE, path="/")
        return {"ok": True}

    @api.get("/me")
    async def me():
        cfg = config.load()
        return {"owner_name": cfg["general"]["owner_name"], "language": cfg["general"]["language"], "timezone": cfg["general"]["timezone"],
                "voice": {"server_stt": bool(cfg["voice"]["stt_url"]), "server_tts": bool(cfg["voice"]["tts_url"])}, "version": __version__,
                "prefs": {k: v for k, v in learning.active_prefs().items() if k.startswith("ui.")}, "liff_id": cfg["line"]["liff_id"],
                "model": cfg["models"]["chat"], "models": dict(cfg["models"])}

    @api.get("/state")
    async def state():
        return {"running": activity.running_count(), "open_tasks": len(tasks.list_(False)), "drafts": len(drafts.pending()),
                "reminders": len(tasks.list_reminders()), "memory": memory.overview(), "notifications": outbox.feed(5)}

    @api.post("/chat")
    async def chat(request: Request):
        d = await _json(request)
        text = str(d.get("text", "")).strip()[:6000]
        if not text:
            return _bad("empty message")
        session = "console" if d.get("session") not in ("voice", "console") else d["session"]
        role = d.get("role") if d.get("role") in ("chat", "fast", "vision") else "chat"
        before = {x["id"] for x in drafts.pending()}
        res = await Agent().run(text, session=session, role=role)
        return {"ok": not res.error, "text": res.text, "tools": res.tool_calls, "new_drafts": [drafts.public(x) for x in drafts.pending() if x["id"] not in before]}

    @api.get("/history")
    async def history(session: str = "console"):
        rows = db.q("SELECT role,text,ts FROM messages WHERE session=? ORDER BY id DESC LIMIT 40", (session,))
        return {"messages": [dict(r) for r in reversed(rows)]}

    # tasks, reminders
    @api.get("/tasks")
    async def tasks_list():
        return {"tasks": tasks.list_(True)[:200], "reminders": tasks.list_reminders()}

    @api.post("/tasks")
    async def tasks_add(request: Request):
        d = await _json(request)
        return tasks.add(d.get("title", ""), d.get("due", ""), d.get("priority", 2))

    @api.post("/tasks/{tid}/complete")
    async def tasks_done(tid: int):
        return tasks.complete(tid)

    # projects
    @api.get("/projects")
    async def projects_list():
        return {"items": projects.list_()}

    @api.post("/projects")
    async def projects_create(request: Request):
        d = await _json(request)
        return projects.create(d.get("name", ""), d.get("goal", ""), d.get("deadline", ""), d.get("next_step", ""))

    @api.post("/projects/{pid}/items")
    async def project_item_add(pid: int, request: Request):
        d = await _json(request)
        return projects.add_item(pid, d.get("kind", ""), d.get("text", ""), d.get("due", ""))

    @api.put("/projects/{pid}")
    async def project_update(pid: int, request: Request):
        d = await _json(request)
        return projects.update(pid, d.get("goal", ""), d.get("deadline", ""), d.get("next_step", ""))

    @api.post("/projects/{pid}/items/{item_id}/complete")
    async def project_item_complete(pid: int, item_id: int):
        return projects.complete_item(pid, item_id)

    @api.post("/projects/{pid}/close")
    async def project_close(pid: int):
        return projects.close(pid)

    @api.post("/reminders")
    async def reminders_add(request: Request):
        d = await _json(request)
        return tasks.add_reminder(d.get("text", ""), d.get("when", ""))

    # memory
    @api.get("/memory")
    async def memory_list():
        return {"items": memory.all_items(), "overview": memory.overview()}

    @api.post("/memory")
    async def memory_add(request: Request):
        d = await _json(request)
        return memory.remember(d.get("text", ""), d.get("kind", "fact"), "console")

    @api.delete("/memory/{mid}")
    async def memory_del(mid: int):
        return {"ok": memory.forget(mid)}

    # drafts (approval)
    @api.get("/drafts")
    async def drafts_list():
        return {"drafts": [drafts.public(d) for d in drafts.pending()]}

    @api.post("/drafts/{did}/approve")
    async def drafts_approve(did: int):
        return await drafts.approve(did, via="console")

    @api.post("/drafts/{did}/cancel")
    async def drafts_cancel(did: int):
        return drafts.cancel(did)

    @api.post("/drafts/{did}/edit")
    async def drafts_edit(did: int, request: Request):
        r = drafts.edit(did, (await _json(request)).get("text", ""))
        return {k: v for k, v in r.items() if k != "code"}

    @api.get("/notifications")
    async def notifications():
        return {"items": outbox.feed(40)}

    # activity, automations
    @api.get("/activity")
    async def activity_list(count: int = 0):
        return {"running": activity.running_count()} if count else activity.recent(30)

    @api.get("/activity/{aid}")
    async def activity_get(aid: int):
        return activity.get(aid) or _bad("not found", 404)

    @api.get("/automations")
    async def automations():
        return {"items": scheduler.list_automations()}

    @api.post("/automations")
    async def automations_create(request: Request):
        d = await _json(request)
        return scheduler.create(d.get("name", ""), d.get("prompt", ""), d.get("schedule") or {})

    @api.post("/automations/{aid}/toggle")
    async def automations_toggle(aid: int, request: Request):
        return scheduler.set_enabled(aid, bool((await _json(request)).get("enabled")))

    @api.post("/automations/{aid}/run")
    async def automations_run(aid: int):
        return await scheduler.run_now(aid)

    @api.delete("/automations/{aid}")
    async def automations_delete(aid: int):
        return scheduler.delete(aid)

    # skills
    @api.get("/skills")
    async def skills_list():
        return {"skills": skills.list_skills()}

    @api.get("/skills/{name}")
    async def skills_get(name: str):
        r = skills.view(name)
        if r.get("ok") and r["pending"]:
            r["review"] = skills.review_dir(paths.skills_pending_dir() / name)
        return r

    @api.post("/skills")
    async def skills_create(request: Request):
        d = await _json(request)
        return skills.create(d.get("name", ""), d.get("description", ""), d.get("body", ""), "owner")

    @api.put("/skills/{name}")
    async def skills_update(name: str, request: Request):
        d = await _json(request)
        return skills.update(name, d.get("body", ""), d.get("description"), "owner")

    @api.delete("/skills/{name}")
    async def skills_delete(name: str):
        return skills.delete(name, "owner")

    @api.post("/skills/{name}/toggle")
    async def skills_toggle(name: str, request: Request):
        d = await _json(request)
        return skills.set_enabled(name, bool(d.get("enabled")), by="owner", ack=bool(d.get("ack")))

    @api.post("/skills/import")
    async def skills_import(request: Request):
        d = await _json(request)
        if d.get("kind") == "text":
            return {"results": [skills.import_text(d.get("text", ""))]}
        if d.get("kind") == "url":
            return {"results": await skills.import_github(d.get("url", ""))}
        if d.get("kind") == "zip":
            import base64
            return {"results": skills.import_zip(base64.b64decode(d.get("data", "")))}
        return _bad("kind must be text, url or zip")

    # learning, user model, companion, patches
    @api.get("/learning")
    async def learning_get():
        return {"settings": learning.active_prefs(), "log": learning.recent_log(), "proposals": learning.proposals(), "week_note": db.kv_get("week_note"),
                "traits": usermodel.status(), "level": companion.level(), "schema": {k: list(v[1]) if isinstance(v[1], tuple) else v[0] for k, v in learning.SCHEMA.items()}}

    @api.post("/learning/pref")
    async def learning_pref(request: Request):
        d = await _json(request)
        scope, _, key = str(d.get("setting", "")).partition(".")
        return learning.set_prefs(scope, {key: d.get("value")}, "owner", "set by the owner")

    @api.post("/learning/undo")
    async def learning_undo(request: Request):
        return learning.undo(int((await _json(request)).get("id", 0)))

    @api.post("/learning/restore")
    async def learning_restore(request: Request):
        scope, _, key = str((await _json(request)).get("setting", "")).partition(".")
        return learning.restore_default(scope, key)

    @api.post("/learning/proposal")
    async def learning_proposal(request: Request):
        d = await _json(request)
        return learning.decide_proposal(int(d.get("id", 0)), bool(d.get("accept")))

    @api.get("/usermodel/{name}/evidence")
    async def um_evidence(name: str):
        return {"items": usermodel.evidence(name)}

    @api.post("/usermodel/correct")
    async def um_correct(request: Request):
        d = await _json(request)
        return usermodel.correct(d.get("name", ""), d.get("value", ""))

    @api.delete("/usermodel/{name}")
    async def um_delete(name: str):
        return usermodel.delete(name)

    @api.delete("/usermodel/evidence/{eid}")
    async def um_delete_ev(eid: int):
        return usermodel.delete_evidence(eid)

    @api.get("/companion/opener")
    async def opener():
        return companion.opener()

    @api.post("/companion/level")
    async def comp_level(request: Request):
        return companion.set_level((await _json(request)).get("level", ""), "owner")

    @api.get("/patches")
    async def patches_list():
        return {"patches": patching.list_patches()}

    @api.get("/patches/{pid}")
    async def patches_get(pid: int):
        return patching.get(pid) or _bad("not found", 404)

    @api.post("/patches/{pid}/approve")
    async def patches_approve(pid: int):
        return await asyncio.to_thread(patching.apply, pid)

    @api.post("/patches/{pid}/reject")
    async def patches_reject(pid: int):
        return patching.reject(pid)

    # system, settings, models, voice
    @api.get("/system")
    async def system():
        from .. import health
        return {"info": system_info(), "health": health.check(), "tools": sorted(tools.REGISTRY), "providers": {n: {"kind": p.get("kind"), "base_url": p.get("base_url")} for n, p in config.load()["providers"].items()}}

    @api.post("/settings")
    async def settings(request: Request):
        d = await _json(request)
        cfg = config.load()
        if d.get("language") in i18n.SUPPORTED:
            cfg["general"]["language"] = d["language"]
        if isinstance(d.get("owner_name"), str):
            cfg["general"]["owner_name"] = d["owner_name"].strip()[:60]
        if d.get("timezone"):
            try:
                zoneinfo.ZoneInfo(d["timezone"])
                cfg["general"]["timezone"] = d["timezone"]
            except Exception:
                return _bad("unknown timezone")
        config.save(cfg)
        return {"ok": True}

    @api.post("/models/test")
    async def models_test(request: Request):
        role = (await _json(request)).get("role", "chat")
        try:
            prov, model = providers.for_role(config.load(), role if role in ("chat", "fast", "vision") else "chat")
        except providers.ProviderError as e:
            return {"ok": False, "message": str(e)}
        ok, msg = await prov.ping(model)
        return {"ok": ok, "message": msg, "model": model}

    @api.post("/voice/stt")
    async def voice_stt(request: Request):
        from ..voice import adapters
        data = await request.body()
        if not data or len(data) > 10_000_000:
            return _bad("audio missing or too large")
        try:
            return {"ok": True, "text": await adapters.transcribe(data, request.headers.get("content-type", "audio/webm"))}
        except adapters.VoiceError as e:
            return _bad(str(e), 503)

    @api.post("/voice/tts")
    async def voice_tts(request: Request):
        from ..voice import adapters
        text = str((await _json(request)).get("text", ""))[:2000]
        try:
            audio, mime = await adapters.speak(text)
        except adapters.VoiceError as e:
            return _bad(str(e), 503)
        return Response(audio, media_type=mime)

    app.include_router(api)
    from .sandbox_api import router as sandbox_router  # N8 to N10: owner-only like every other private route
    app.include_router(sandbox_router, prefix="/api", dependencies=[Depends(auth.require_owner)])
    return app


def serve(host: str | None = None, port: int | None = None) -> None:
    import logging

    import uvicorn

    cfg = config.load()
    logging.getLogger().addFilter(secrets.RedactingFilter())
    uvicorn.run(create_app(), host=host or cfg["gateway"]["host"], port=port or cfg["gateway"]["port"], log_level="warning", access_log=False)


def dump_routes(app: FastAPI) -> list[tuple[str, str]]:
    return sorted((m, r.path) for r in app.routes for m in getattr(r, "methods", []) or [] if m not in ("HEAD", "OPTIONS"))


_ = json  # json is imported for route helpers added by plugins

