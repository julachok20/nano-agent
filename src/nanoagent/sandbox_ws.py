"""The sandbox workspace (N8): one persistent isolated workspace where the agent may write code, build tools and skills,
and schedule its own jobs. Rules live at the EDGE, in host code, and every edge request is written to a hash-chained
audit table.

Tiers (set once by the owner in config, the agent has no tool that changes them):
    T0  no network at all
    T1  outbound only to owner-listed domains (host edge checks every request, public addresses only)
    T2  broad outbound web reads, no credentials
    T3  as T2, plus brokered keyed calls per capability (keys never enter the sandbox); messaging and payments are
        off unless the owner lists them. Payments are never implemented.

Every outbound request, host file access, secret request, message and brokered call goes through this module. Inside
the container there is no network (`--network none`) in every tier: all outbound traffic is made by the host edge.

The host never executes model text itself: commands run inside the container (DockerRuntime), or in tests only on the
host through LocalRuntime, which is not isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from . import activity, config, db, keystore, outbox, paths
from .sandbox_runtime import DockerRuntime, RuntimeUnavailable

TIERS = ("T0", "T1", "T2", "T3")
CONTAINER = "nano-agent-workspace"   # the owner's container; red-team runs use their own name (see OVERRIDE)
MAX_TEXT = 20000
GENESIS = "GENESIS"
RUN = {"id": "chat"}   # who is acting: "chat", "automation:<id>", "redteam:<scenario>"; set by the caller
OVERRIDE: dict = {}    # red-team only: a throwaway workspace folder and tier. Empty in normal use.

NAMES = {"ws_shell", "ws_read", "ws_write", "ws_list", "ws_fetch", "ws_broker", "ws_send", "ws_secret",
         "ws_job_create", "ws_job_edit", "ws_job_set_enabled", "ws_job_delete", "ws_job_list"}


# ---- settings ---------------------------------------------------------------------------------------

def settings(cfg: dict | None = None) -> dict:
    s = {**dict((cfg or config.load())["sandbox"]), **OVERRIDE.get("settings", {})}
    tier = str(s.get("tier", "T0")).strip().upper()
    s["tier"] = tier if tier in TIERS else "T0"           # unknown value: the most closed tier
    s["workspace"] = bool(s.get("workspace", False))
    s["allowed_domains"] = [str(d).strip().lower() for d in (s.get("allowed_domains") or []) if str(d).strip()]
    caps: dict[str, str] = {}
    for item in s.get("capabilities") or []:
        name, _, dom = str(item).partition("=")
        if name.strip():
            caps[name.strip().lower()] = dom.strip().lower()
    s["capabilities"] = caps
    return s


def enabled(cfg: dict | None = None) -> bool:
    return settings(cfg)["workspace"]


def hidden_tools() -> set[str]:
    """Tool names the model should not even see while the workspace is off."""
    return set() if enabled() else set(NAMES)


# ---- audit: hash-chained -------------------------------------------------------------------------------

def _chain(prev: str, ts: float, kind: str, target: str, decision: str, reason: str, run_id: str) -> str:
    body = json.dumps([prev, ts, kind, target, decision, reason, run_id], ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def audit(kind: str, target: str, decision: str, reason: str = "", run_id: str | None = None) -> int:
    target = keystore.redact(str(target))[:400]
    reason = keystore.redact(str(reason))[:300]
    rid = (run_id if run_id is not None else RUN["id"])[:80]
    with db.tx() as c:
        last = c.execute("SELECT hash FROM sandbox_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        ts = time.time()
        h = _chain(prev, ts, kind, target, decision, reason, rid)
        cur = c.execute("INSERT INTO sandbox_audit(ts,kind,target,decision,reason,run_id,prev,hash) VALUES(?,?,?,?,?,?,?,?)",
                        (ts, kind, target, decision, reason, rid, prev, h))
        return int(cur.lastrowid or 0)


def verify_chain() -> tuple[bool, int]:
    """(True, 0) when every row still links to the one before it; else (False, id of the first broken row)."""
    prev = GENESIS
    for r in db.q("SELECT * FROM sandbox_audit ORDER BY id"):
        if r["prev"] != prev or _chain(r["prev"], r["ts"], r["kind"], r["target"], r["decision"], r["reason"], r["run_id"]) != r["hash"]:
            return False, int(r["id"])
        prev = r["hash"]
    return True, 0


def audit_rows(limit: int = 200, since_id: int = 0) -> list[dict]:
    rows = db.q("SELECT * FROM sandbox_audit WHERE id>? ORDER BY id DESC LIMIT ?", (since_id, limit))
    return [dict(r) for r in rows][::-1]


# ---- edge decisions -----------------------------------------------------------------------------------

def _host_allowed(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def decide_fetch(url: str, s: dict) -> tuple[bool, str]:
    if s["tier"] == "T0":
        return False, "tier T0 has no network"
    host = (urlparse(url).hostname or "").lower()
    if s["tier"] == "T1" and not _host_allowed(host, s["allowed_domains"]):
        return False, "domain is not on the owner's allowlist"
    from .tools import web
    try:
        web.check_url(url)
    except Exception as e:   # BlockedURL: private address, bad scheme, credentials
        return False, f"blocked: {e}"
    return True, "allowed"


async def fetch(url: str, run_id: str | None = None) -> dict:
    s = settings()
    ok, reason = decide_fetch(str(url), s)
    audit("fetch", str(url), "allow" if ok else "deny", reason, run_id)
    if not ok:
        return {"ok": False, "error": f"blocked by the sandbox edge: {reason}"}
    from .tools import web
    try:
        r = await web._get(str(url))
    except Exception as e:
        return {"ok": False, "error": f"fetch failed: {type(e).__name__}"}
    return {"ok": r.status_code < 400, "status": r.status_code, "text": keystore.redact(r.text)[:6000]}


async def broker(capability: str, path: str, run_id: str | None = None) -> dict:
    """T3 only: the host makes the keyed call. The key is read here and never returned to the sandbox."""
    import httpx
    s = settings()
    cap = str(capability).strip().lower()
    target = f"{cap}:{str(path)[:120]}"
    if s["tier"] != "T3":
        audit("broker", target, "deny", "brokered calls need tier T3", run_id)
        return {"ok": False, "error": "brokered calls need tier T3; ask the owner"}
    if cap == "payments":
        audit("broker", target, "deny", "payments are never enabled", run_id)
        return {"ok": False, "error": "payments are never enabled"}
    dom = s["capabilities"].get(cap, "")
    if not dom or cap == "messaging":
        audit("broker", target, "deny", "capability not enabled by the owner", run_id)
        return {"ok": False, "error": "that capability is not enabled by the owner"}
    key = keystore.get(f"broker.{cap}")
    if not key:
        audit("broker", target, "deny", "owner has not stored a key for this capability", run_id)
        return {"ok": False, "error": "the owner has not set up this capability yet"}
    url = f"https://{dom}/{str(path).lstrip('/')}"
    ok, reason = decide_fetch(url, {**s, "tier": "T2"})
    audit("broker", target, "allow" if ok else "deny", reason, run_id)
    if not ok:
        return {"ok": False, "error": f"blocked by the sandbox edge: {reason}"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as c:
        r = await c.get(url, headers={"Authorization": f"Bearer {key}"})
    return {"ok": r.status_code < 400, "status": r.status_code, "text": keystore.redact(r.text)[:6000]}


def send_request(channel: str, target: str, text: str, run_id: str | None = None) -> dict:
    """Messages to people. Off in T0 to T2. In T3 only when the owner listed `messaging`, and even then it is queued as a
    draft for approval: auto-send is NOT built (see docs/SANDBOX.md)."""
    s = settings()
    if s["tier"] == "T3" and "messaging" in s["capabilities"]:
        from . import drafts
        d = drafts.prepare(channel, target, text, note="from the sandbox workspace")
        audit("send", f"{channel}:{target}", "queued", "waiting for owner approval", run_id)
        return {"ok": True, "queued_as_draft": True, "draft": d}
    audit("send", f"{channel}:{target}", "deny", "messaging is off in this tier", run_id)
    return {"ok": False, "error": "messaging is off. The owner must enable it; nothing was sent."}


def secret_request(name: str, run_id: str | None = None) -> dict:
    """Keys never enter the sandbox. Always denied and logged."""
    audit("secret_read", str(name)[:80], "deny", "keys never enter the sandbox", run_id)
    return {"ok": False, "error": "keys never enter the sandbox. Use a brokered capability instead."}


# ---- workspace files ------------------------------------------------------------------------------------

def container() -> str:
    return OVERRIDE.get("container") or CONTAINER


def root() -> Path:
    p = Path(OVERRIDE["root"]) if OVERRIDE.get("root") else paths.workspace_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _real(p: Path) -> Path:
    return Path(os.path.realpath(p))


def inside(rel: str, base: Path | None = None) -> Path | None:
    base = base or root()
    cand = Path(rel) if Path(rel).is_absolute() else base / rel
    real, broot = _real(cand), _real(base)
    if real == broot or broot in real.parents:
        return real
    return None


CONTROL_NAMES = {"constitution.md", "config.toml", "secrets.toml", "nano.db", "state.json", "notifications.log"}


def _cand(rel: str) -> Path:
    return Path(rel) if Path(rel).is_absolute() else root() / rel


def is_control(p: Path) -> bool:
    """Paths that belong to the owner's control layer: supervisor, config, secrets, database, logs, constitution.
    Relative paths are judged where they would land (inside the workspace), and control file names are refused anywhere."""
    from . import constitution
    p = Path(p)
    if p.name in CONTROL_NAMES or {"supervisor", "logs"} & set(p.parts):
        return True
    real = _real(p)
    for g in (paths.supervisor_dir(), paths.config_path(), paths.secrets_path(), paths.db_path(), paths.logs_dir(), constitution.path()):
        g = _real(Path(g))
        if real == g or g in real.parents:
            return True
    return False


def canaries() -> list[str]:
    return list(db.kv_get("sandbox.canaries", []) or [])


def plant_canaries() -> list[str]:
    """Honeypot files with FAKE keys inside the workspace. Any read, write or command that names one is a tripwire."""
    base = root()
    rel = ".canary/fake_keys.env"
    (base / ".canary").mkdir(parents=True, exist_ok=True)
    (base / rel).write_text("FAKE_PROVIDER_KEY=CANARY-0000-NOT-A-REAL-KEY\n", encoding="utf-8")
    db.kv_set("sandbox.canaries", [rel])
    return [rel]


def _canary_hit(text: str) -> str | None:
    for rel in canaries():
        if Path(rel).name in text or rel in text:
            return rel
    return None


def read(rel: str, run_id: str | None = None) -> dict:
    p = inside(rel)
    if p is None:
        kind = "control_path" if is_control(_cand(rel)) else "host_read"
        audit(kind, rel, "deny", "outside the workspace", run_id)
        return {"ok": False, "error": "outside the workspace: denied and logged"}
    if _canary_hit(str(rel)):
        audit("canary_touch", rel, "trip", "read a honeypot file", run_id)
    if not p.is_file():
        return {"ok": False, "error": "no such file in the workspace"}
    audit("read", rel, "allow", "", run_id)
    return {"ok": True, "text": p.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT]}


def write(rel: str, text: str, run_id: str | None = None) -> dict:
    p = inside(rel)
    if p is None:
        kind = "control_path" if is_control(_cand(rel)) else "host_write"
        audit(kind, rel, "deny", "outside the workspace", run_id)
        return {"ok": False, "error": "outside the workspace: denied and logged"}
    if _canary_hit(str(rel)):
        audit("canary_touch", rel, "trip", "wrote a honeypot file", run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(text), encoding="utf-8")
    audit("write", rel, "allow", f"{len(str(text))} chars", run_id)
    return {"ok": True, "path": rel}


def listing(rel: str = ".") -> dict:
    p = inside(rel or ".")
    if p is None or not p.is_dir():
        return {"ok": False, "error": "not a folder in the workspace"}
    names = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())[:300]
    return {"ok": True, "entries": names}


def dir_mb(base: Path | None = None) -> float:
    total = 0
    for dp, _dn, files in os.walk(base or root()):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 2)


# ---- commands -----------------------------------------------------------------------------------------

_runtime: dict = {"obj": None}


def get_runtime():
    """The active runtime. Production: Docker. Tests and the red-team test mode install a LocalRuntime with use()."""
    if _runtime["obj"] is None:
        _runtime["obj"] = DockerRuntime()
    return _runtime["obj"]


def use(runtime) -> None:
    _runtime["obj"] = runtime


def run_command(command: str, run_id: str | None = None, timeout_s: int | None = None) -> dict:
    """Run one shell command inside the workspace container. Gated by the supervisor and watched for lease expiry."""
    from . import supervisor
    rid = run_id if run_id is not None else RUN["id"]
    ok, why = supervisor.gate()
    if not ok:
        audit("exec", str(command)[:200], "deny", why, rid)
        return {"ok": False, "error": why}
    hit = _canary_hit(str(command))
    if hit:
        audit("canary_touch", str(command)[:200], "trip", f"command names honeypot {hit}", rid)
    s = settings()
    rt = get_runtime()
    limit = max(1, min(int(timeout_s or s.get("run_timeout_s", 120)), 600))
    try:
        rt.ensure(container(), config.load()["sandbox"].get("image", "python:3.12-slim"), root(),
                  float(s.get("cpu", 1.0)), int(s.get("memory_mb", 512)))
    except RuntimeUnavailable as e:
        audit("exec", str(command)[:200], "deny", str(e), rid)
        return {"ok": False, "error": str(e)}
    aid = activity.start("sandbox", f"Sandbox: {str(command)[:90]}")
    activity.step(aid, f"$ {str(command)[:150]}")
    supervisor.begin_run(rid)
    try:
        res = rt.exec(container(), str(command), limit, watch=supervisor.lease_ok_watch)
    except RuntimeUnavailable as e:
        activity.finish(aid, False, str(e)[:200])
        audit("exec", str(command)[:200], "deny", str(e), rid)
        return {"ok": False, "error": str(e)}
    finally:
        supervisor.end_run(rid)
    for line in (res.stdout or "").splitlines()[:20]:
        activity.step(aid, line[:200])
    mb = dir_mb()
    mem = rt.stats_mb(container())
    audit("metric", f"mem_mb={mem:.1f} disk_mb={mb:.1f}", "obs", "", rid)
    if mb > float(s.get("disk_mb", 512)):
        audit("resource_limit", f"disk {mb} MB over {s.get('disk_mb')}", "trip", "workspace over disk limit", rid)
    outcome = "frozen" if res.frozen else "timed out" if res.timed_out else f"exit {res.exit}"
    good = res.exit == 0 and not res.timed_out and not res.frozen
    audit("exec", str(command)[:200], "allow", outcome, rid)   # it ran; the exit code is data, not a refusal
    activity.finish(aid, good, outcome)
    return {"ok": good, "exit": res.exit, "stdout": (res.stdout or "")[-4000:], "stderr": (res.stderr or "")[-2000:],
            "timed_out": res.timed_out, "frozen": res.frozen}


# ---- scheduled sandbox jobs (the existing scheduler runs them) ---------------------------------------------

RETRY_S = (60, 300, 900)
MAX_ATTEMPTS = 3


def _schedule_ok(schedule: dict) -> tuple[bool, str]:
    from . import scheduler
    if not scheduler.valid_schedule(schedule):
        return False, 'schedule must be {"every_min": N}, {"daily": "HH:MM"} or {"weekly": "sun 19:00"}'
    return True, ""


def _script_ok(script: str) -> tuple[bool, str]:
    p = inside(script)
    if p is None:
        return False, "the script must be inside the workspace"
    if not p.is_file():
        return False, "write the script into the workspace first (ws_write), then schedule it"
    return True, ""


def job_create(name: str, script: str, schedule: dict, run_id: str | None = None) -> dict:
    name = " ".join(str(name).split())[:60]
    if not name:
        return {"ok": False, "error": "a name is required"}
    ok, why = _script_ok(script)
    if not ok:
        return {"ok": False, "error": why}
    ok, why = _schedule_ok(schedule)
    if not ok:
        return {"ok": False, "error": why}
    if db.one("SELECT 1 FROM automations WHERE name=?", (name,)):
        return {"ok": False, "error": "an automation with that name exists"}
    from . import scheduler
    jid = db.run("INSERT INTO automations(name,job,prompt,schedule,enabled,next_run) VALUES(?,?,?,?,1,?)",
                 (name, "sandbox", script, json.dumps(schedule), scheduler.compute_next(schedule, time.time())))
    audit("job", f"create {name}", "allow", script, run_id)
    return {"ok": True, "id": jid}


def _sandbox_job(job_id: int):
    return db.one("SELECT * FROM automations WHERE id=? AND job='sandbox'", (int(job_id),))


def job_edit(job_id: int, script: str = "", schedule: dict | None = None, run_id: str | None = None) -> dict:
    row = _sandbox_job(job_id)
    if not row:
        return {"ok": False, "error": "no such sandbox job"}
    new_script = script or row["prompt"]
    if script:
        ok, why = _script_ok(script)
        if not ok:
            return {"ok": False, "error": why}
    sched = schedule if schedule is not None else json.loads(row["schedule"])
    ok, why = _schedule_ok(sched)
    if not ok:
        return {"ok": False, "error": why}
    from . import scheduler
    db.run("UPDATE automations SET prompt=?, schedule=?, next_run=? WHERE id=?",
           (new_script, json.dumps(sched), scheduler.compute_next(sched, time.time()), int(job_id)))
    audit("job", f"edit {job_id}", "allow", "", run_id)
    return {"ok": True}


def job_set_enabled(job_id: int, enabled_: bool, run_id: str | None = None) -> dict:
    if not _sandbox_job(job_id):
        return {"ok": False, "error": "no such sandbox job"}
    from . import scheduler
    scheduler.set_enabled(int(job_id), bool(enabled_))
    audit("job", f"{'resume' if enabled_ else 'pause'} {job_id}", "allow", "", run_id)
    return {"ok": True}


def job_delete(job_id: int, run_id: str | None = None) -> dict:
    if not _sandbox_job(job_id):
        return {"ok": False, "error": "no such sandbox job"}
    db.run("DELETE FROM automations WHERE id=? AND job='sandbox'", (int(job_id),))
    audit("job", f"delete {job_id}", "allow", "", run_id)
    return {"ok": True}


def job_list() -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "script": r["prompt"], "enabled": bool(r["enabled"]),
             "schedule": json.loads(r["schedule"]), "last_status": r["last_status"]}
            for r in db.q("SELECT * FROM automations WHERE job='sandbox' ORDER BY id")]


def run_scheduled(row: dict) -> None:
    """Called by the scheduler for a `sandbox` job. Failures retry with backoff; the owner is told once after the last attempt."""
    res = run_command(f"python {shlex.quote(str(row['prompt']))}", run_id=f"automation:{row['id']}")
    key, notified = f"sbjob_fail:{row['id']}", f"sbjob_notified:{row['id']}"
    if res.get("ok"):
        db.kv_set(key, 0)
        db.kv_set(notified, False)
        return
    fails = int(db.kv_get(key, 0) or 0) + 1
    if fails >= MAX_ATTEMPTS:
        if not db.kv_get(notified, False):
            outbox.notify_owner(f"Sandbox job '{row['name']}' failed {fails} times. It keeps its normal schedule. Check the activity page.", "sandbox")
            db.kv_set(notified, True)
        db.kv_set(key, 0)
    else:
        db.kv_set(key, fails)
        db.run("UPDATE automations SET next_run=? WHERE id=?", (time.time() + RETRY_S[min(fails, len(RETRY_S)) - 1], row["id"]))
    raise RuntimeError(f"sandbox job failed (attempt {fails})")


# ---- snapshots and rollback -------------------------------------------------------------------------------

def snapshot(label: str = "manual") -> dict:
    d = paths.snapshots_dir()
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9-]", "-", label.lower())[:30] or "manual"
    sid = f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}-{int(time.time() * 1000) % 1000:03d}"
    out = d / f"{sid}.zip"
    base = root()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _dn, files in os.walk(base):
            for f in files:
                full = Path(dp) / f
                z.write(full, full.relative_to(base).as_posix())
    audit("snapshot", sid, "allow", label)
    return {"ok": True, "id": sid, "path": str(out)}


def list_snapshots() -> list[str]:
    d = paths.snapshots_dir()
    return sorted(p.stem for p in d.glob("*.zip")) if d.exists() else []


def restore(snap_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", str(snap_id)):
        return {"ok": False, "error": "bad snapshot id"}
    src = paths.snapshots_dir() / f"{snap_id}.zip"
    if not src.exists():
        return {"ok": False, "error": "no such snapshot"}
    base = root()
    with zipfile.ZipFile(src) as z:   # check every member BEFORE touching the workspace
        for info in z.infolist():
            parts = Path(info.filename).parts
            if info.filename.startswith(("/", "\\")) or ".." in parts or Path(info.filename).is_absolute():
                return {"ok": False, "error": "snapshot has an unsafe path; nothing was changed"}
        pre = snapshot("pre-restore")
        for child in list(base.iterdir()):
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        z.extractall(base)
    audit("restore", snap_id, "allow", f"pre-restore copy {pre['id']}")
    return {"ok": True, "restored": snap_id, "pre_restore": pre["id"]}


# ---- status and prompt ---------------------------------------------------------------------------------------

def status() -> dict:
    s = settings()
    n = db.one("SELECT COUNT(*) c FROM sandbox_audit")
    return {"workspace": s["workspace"], "tier": s["tier"], "allowed_domains": s["allowed_domains"],
            "capabilities": sorted(s["capabilities"]), "snapshots": list_snapshots()[-5:],
            "audit_rows": int(n["c"]) if n else 0}


TIER_TEXT = {
    "T0": "no network",
    "T1": "outbound only to the owner's allowlisted domains",
    "T2": "broad outbound web reads, no credentials",
    "T3": "outbound web reads plus brokered keyed capabilities the owner enabled (you never see keys)",
}


def prompt_hint() -> str:
    s = settings()
    if not s["workspace"]:
        return ""
    return (f"Sandbox workspace (tier {s['tier']}: {TIER_TEXT[s['tier']]}). You have a private Linux workspace at /work. "
            "There is no preset tool list inside it: use ws_shell to run commands, ws_write and ws_read for files, and ws_job_* "
            "to schedule your own jobs. Build what you need to help the owner. Save useful procedures as SKILL.md folders "
            "with scripts under /work/skills so you get better over time. Messages to people, keys and payments are never "
            "yours to send; ask the owner. You cannot change your tier. If you need more access, say so and ask the owner.")
