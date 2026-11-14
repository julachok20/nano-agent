"""Self-modification patches, with a HARD DENYLIST that is code, not a prompt.

The assistant may *propose* new tools or behaviour as small Python plugin files. It can never apply them.

  propose(...)  checks the denylist and an AST allowlist, stores the diff, runs the plugin in a throw-away subprocess
                (temp home, no secrets, 30 s) and reports READY or FAILED. Nothing live changes.
  apply(id)     owner-only (console route). Re-checks the denylist against the REAL files, backs them up, writes, re-runs the
                import test, and rolls back automatically if anything fails. The change is on the learning log with an undo.

What a patch may touch: only files under `plugins/` in the data folder. Everything else is refused: the nano Agent
package itself (drafts, gateway, agent, keystore, patching ... the safety core), config and secrets files, databases,
anything outside the folder, anything hidden. A patch may add a test file but never change an existing one.

Inside plugin code (checked on every added or removed line and by AST):
  * only these imports: json re math datetime typing statistics collections itertools functools textwrap decimal
    fractions string random, plus nano_agent.tools (the `tool` decorator), nano_agent.memory and nano_agent.tasks;
  * no eval/exec/compile/open/getattr/__import__, no dunder attribute access, no subprocess/os/sys/socket/ctypes/pickle;
  * no mention of sending APIs, approvals, secrets, environment variables or shell commands.
Defence in depth only: Python cannot be sandboxed from inside Python. The real gate is that the owner reads the diff and
taps Approve. Plugins run in the gateway process once approved.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import db, learning, paths

REFUSE = "This part must be changed by the owner by hand. The assistant cannot change it."
ALLOWED_PREFIXES = ("plugins/",)
ALLOWED_EXT = (".py", ".md", ".json", ".txt")
MAX_FILES, MAX_LINES, MAX_BYTES = 8, 400, 200_000
TTL = 24 * 3600

# Named explicitly so a reader (and a test) can see the protected core. The allow-list above already excludes them.
DENY_NAMES = {
    "drafts.py", "gateway", "agent.py", "keystore.py", "patching.py", "learning.py", "usermodel.py", "companion.py", "skills.py",
    "sandbox.py", "health.py", "scheduler.py", "outbox.py", "db.py", "config.py", "activity.py", "providers", "cli.py", "wizard.py",
    "auth.py", "line.py", "secrets.toml", "config.toml", "nano.db", "SECURITY.md",
}
DENY_NAME_RE = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.env|credentials[^/]*|token[^/]*\.json|[^/]*\.(db|sqlite|pem|key|p12)|secrets[^/]*|config\.toml)$", re.I)
ALLOWED_IMPORTS = {"json", "re", "math", "datetime", "typing", "statistics", "collections", "itertools", "functools", "textwrap",
                   "decimal", "fractions", "string", "random", "__future__"}
ALLOWED_NANO = {"nano_agent.tools", "nano_agent.memory", "nano_agent.tasks"}
BAD_NAMES = {"eval", "exec", "compile", "open", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "input", "breakpoint"}
FORBIDDEN_LINE = re.compile(
    r"api\.line\.me|/v2/bot|\bSENDERS\b|register_sender|\.approve\(|drafts\.|keystore|secrets|NANO_SECRET|\benviron\b|getenv|"
    r"subprocess|os\.system|os\.popen|shutil|\bsocket\b|ctypes|pickle|importlib|\bsudo\b|\bdocker\b|systemctl|\.ssh|"
    r"channel_secret|channel_token|api_key|owner_token|require_owner|verify_signature", re.I)


def norm_path(rel: str) -> str:
    r = (rel or "").strip().replace("\\", "/")
    if not r or r.startswith("/") or "\x00" in r or ":" in r.split("/")[0]:
        return ""
    n = posixpath.normpath(r)
    if n.startswith("..") or n == "." or any(part.startswith(".") for part in n.split("/")):
        return ""
    return n


def check_path(rel: str, exists_live: bool) -> str:
    """'' when the file may be patched, else the reason."""
    n = norm_path(rel)
    if not n:
        return "invalid file name"
    parts = n.split("/")
    if any(p in DENY_NAMES for p in parts) or DENY_NAME_RE.search(n) or n.startswith(("src/", "nano_agent/", "tests/", ".git")):
        return f"{REFUSE} ({n})"
    if not n.startswith(ALLOWED_PREFIXES) or not n.endswith(ALLOWED_EXT):
        return f"A patch may only write files under plugins/ (.py .md .json .txt) ({n})"
    if n.startswith("plugins/tests/") and exists_live:
        return f"An existing test cannot be edited; add a new test file instead ({n})"
    return ""


def readable(rel: str) -> bool:
    n = norm_path(rel)
    return bool(n) and not check_path(n, True).startswith(REFUSE) and n.startswith(ALLOWED_PREFIXES)


def changed_lines(old: str | None, new: str) -> tuple[list[str], list[str]]:
    rem, add = [], []
    for ln in difflib.unified_diff((old or "").splitlines(), new.splitlines(), lineterm="", n=0):
        if ln.startswith(("---", "+++", "@@")):
            continue
        (rem if ln.startswith("-") else add).append(ln[1:])
    return rem, add


def check_python(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error line {e.lineno}"]
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS and a.name not in ALLOWED_NANO:
                    bad.append(f"import {a.name} is not allowed")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or not (mod.split(".")[0] in ALLOWED_IMPORTS or mod in ALLOWED_NANO or mod == "nano_agent"):
                bad.append(f"from {mod} import ... is not allowed")
            elif mod == "nano_agent" and any(a.name not in ("tools", "memory", "tasks") for a in node.names):
                bad.append("from nano_agent import: only tools, memory, tasks")
        elif isinstance(node, ast.Name) and node.id in BAD_NAMES:
            bad.append(f"'{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            bad.append(f"attribute '{node.attr}' is not allowed")
    return sorted(set(bad))[:6]


def check_change(rel: str, old: str | None, new: str) -> list[str]:
    n = norm_path(rel)
    why = check_path(n, old is not None)
    if why:
        return [why]
    out: list[str] = []
    rem, add = changed_lines(old, new)
    for ln in rem + add:
        m = FORBIDDEN_LINE.search(ln)
        if m:
            out.append(f"{n}: a changed line mentions '{m.group(0)[:30]}' (sending, secrets, approvals or system commands). {REFUSE}")
            break
    if n.endswith(".py"):
        out += [f"{n}: {b}" for b in check_python(new)]
    if len(new.encode()) > MAX_BYTES:
        out.append(f"{n}: file is larger than {MAX_BYTES // 1000} KB")
    return out


def check_set(changes: list[dict]) -> list[dict]:
    bad = []
    if not changes or len(changes) > MAX_FILES:
        bad.append({"path": "", "reason": f"between 1 and {MAX_FILES} files per patch"})
    total = 0
    for c in changes[:MAX_FILES]:
        for r in check_change(c["path"], c.get("old"), c["new"]):
            bad.append({"path": norm_path(c["path"]) or str(c["path"])[:60], "reason": r})
        rem, add = changed_lines(c.get("old"), c["new"])
        total += len(rem) + len(add)
    if total > MAX_LINES:
        bad.append({"path": "", "reason": f"{total} changed lines; the limit is {MAX_LINES}"})
    return bad


# ---- live files and the throw-away test ------------------------------------

def _live(rel: str) -> Path:
    return paths.data_dir() / rel


def _read(rel: str) -> str | None:
    p = _live(rel)
    return p.read_text(encoding="utf-8") if p.is_file() else None


def build_changes(edits: list[dict]) -> tuple[list[dict], str]:
    """edits: [{path, old?, new}] -> exact changes. `old` (when given) must occur exactly once in the live file."""
    out = []
    for e in edits:
        rel = norm_path(e.get("path", ""))
        cur = _read(rel) if rel else None
        new = e.get("new", "")
        if cur is not None and e.get("old"):
            if cur.count(e["old"]) != 1:
                return [], f"{rel}: 'old' text must occur exactly once"
            new = cur.replace(e["old"], new)
        out.append({"path": rel or str(e.get("path", ""))[:80], "old": cur, "new": new})
    return out, ""


_HARNESS = r"""
import json, os, sys
sys.path[:0] = json.loads(sys.argv[2])
os.environ["NANO_AGENT_HOME"] = sys.argv[1]
from nano_agent import tools
res = tools.load_plugins()
bad = [r for r in res if "FAILED" in r]
print(json.dumps({"loaded": res, "tools": sorted(tools.REGISTRY), "ok": not bad}))
"""


def run_test(files: dict[str, str]) -> dict:
    """Import the plugin files in a subprocess with a temp home: no real data, no secrets in the environment."""
    import nano_agent

    pkg_root = str(Path(nano_agent.__file__).resolve().parents[1])
    with tempfile.TemporaryDirectory(prefix="nano-patch-") as home:
        for rel, text in files.items():
            if rel.endswith(".py") and rel.startswith("plugins/"):
                t = Path(home) / "data" / rel
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_text(text, encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""), "NANO_ACTIVITY_OFF": "1"}
        try:
            p = subprocess.run([sys.executable, "-I", "-c", _HARNESS, home, json.dumps([pkg_root])], capture_output=True, text=True, timeout=30, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "detail": "timed out"}
    if p.returncode != 0:
        return {"ok": False, "detail": (p.stderr.strip().splitlines() or ["failed"])[-1][:200]}
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "detail": "no result"}
    return {"ok": bool(r["ok"]), "detail": "imports cleanly" if r["ok"] else "; ".join(x for x in r["loaded"] if "FAILED" in x)}


# ---- proposals --------------------------------------------------------------

def _files_after(changes: list[dict]) -> dict[str, str]:
    files = {}
    for p in sorted(paths.plugins_dir().rglob("*.py")):
        files["plugins/" + p.relative_to(paths.plugins_dir()).as_posix()] = p.read_text(encoding="utf-8")
    for c in changes:
        files[c["path"]] = c["new"]
    return files


def propose(title: str, summary: str, edits: list[dict]) -> dict:
    changes, err = build_changes(edits)
    if err:
        return {"ok": False, "error": err}
    bad = check_set(changes)
    if bad:
        return {"ok": False, "refused": bad, "error": bad[0]["reason"]}
    diff = "".join("".join(difflib.unified_diff((c["old"] or "").splitlines(True), c["new"].splitlines(True), f"a/{c['path']}", f"b/{c['path']}")) for c in changes)
    test = run_test(_files_after(changes))
    pid = db.run("INSERT INTO patches(ts,title,status,summary,files,diff,test_result,code) VALUES(?,?,?,?,?,?,?,?)",
                 (time.time(), title[:120], "ready" if test["ok"] else "failed", summary[:600], json.dumps([c["path"] for c in changes]), diff[:60000],
                  json.dumps(test), json.dumps(changes)))
    from . import outbox
    if test["ok"]:
        outbox.notify_owner(f"The assistant proposes a change: {title[:80]}. Review it in the console (Settings > Learning) and approve or reject.", "patch")
    return {"ok": True, "id": pid, "status": "ready" if test["ok"] else "failed", "test": test,
            "message": "Proposal saved. It is NOT applied. Only the owner can approve it in the console."}


def get(pid: int) -> dict | None:
    r = db.one("SELECT * FROM patches WHERE id=?", (int(pid),))
    return dict(r) if r else None


def list_patches(limit: int = 20) -> list[dict]:
    return [{k: r[k] for k in ("id", "ts", "title", "status", "summary", "files", "test_result", "applied_ts")} for r in db.q("SELECT * FROM patches ORDER BY id DESC LIMIT ?", (limit,))]


def reject(pid: int) -> dict:
    db.run("UPDATE patches SET status='rejected' WHERE id=? AND status IN ('ready','failed')", (int(pid),))
    return {"ok": True}


def _sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def apply(pid: int) -> dict:
    """Owner-only. Atomic claim, re-check against real files, backup, write, test, rollback on any failure."""
    p = get(pid)
    if not p:
        return {"ok": False, "error": "no such patch"}
    if time.time() - p["ts"] > TTL:
        db.run("UPDATE patches SET status='expired' WHERE id=? AND status='ready'", (pid,))
        return {"ok": False, "error": "this proposal expired; ask for a new one"}
    with db.tx() as c:
        n = c.execute("UPDATE patches SET status='applying' WHERE id=? AND status='ready'", (int(pid),)).rowcount
    if not n:
        return {"ok": False, "error": f"patch is {p['status']}, not ready"}
    changes = json.loads(p["code"])
    for c in changes:   # stale check + denylist again, against the real files
        if _sha(_read(c["path"])) != _sha(c["old"]):
            db.run("UPDATE patches SET status='stale' WHERE id=?", (pid,))
            return {"ok": False, "error": f"{c['path']} changed since the proposal; ask for a new one"}
    bad = check_set(changes)
    if bad:
        db.run("UPDATE patches SET status='refused' WHERE id=?", (pid,))
        return {"ok": False, "error": bad[0]["reason"]}
    bdir = paths.patches_dir() / str(pid) / "backup"
    bdir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    try:
        for c in changes:
            live = _live(c["path"])
            if live.exists():
                (bdir / c["path"].replace("/", "__")).write_text(c["old"] or "", encoding="utf-8")
            else:
                created.append(c["path"])
            live.parent.mkdir(parents=True, exist_ok=True)
            live.write_text(c["new"], encoding="utf-8")
        test = run_test(_files_after([]))
        if not test["ok"]:
            raise RuntimeError("test after applying failed: " + test["detail"])
    except Exception as e:
        _restore(changes, bdir, created)
        db.run("UPDATE patches SET status='rolled_back', test_result=? WHERE id=?", (json.dumps({"ok": False, "detail": str(e)[:200]}), pid))
        return {"ok": False, "error": f"rolled back automatically: {str(e)[:150]}"}
    try:
        from . import tools
        tools.load_plugins()
    except Exception:
        pass
    db.run("UPDATE patches SET status='applied', applied_ts=? WHERE id=?", (time.time(), pid))
    learning.log("patch", f"Applied patch #{pid}: {p['title']}", p["summary"], "owner", {"action": "patch_undo", "patch_id": pid})
    return {"ok": True, "status": "applied"}


def _restore(changes: list[dict], bdir: Path, created: list[str]) -> None:
    for c in changes:
        live = _live(c["path"])
        b = bdir / c["path"].replace("/", "__")
        if c["path"] in created:
            live.unlink(missing_ok=True)
        elif b.exists():
            live.write_text(b.read_text(encoding="utf-8"), encoding="utf-8")


def undo(pid: int) -> dict:
    p = get(pid)
    if not p or p["status"] != "applied":
        return {"ok": False, "error": "patch is not applied"}
    changes = json.loads(p["code"])
    for c in changes:   # refuse if the file changed again after the patch
        if _sha(_read(c["path"])) != _sha(c["new"]):
            return {"ok": False, "error": f"{c['path']} changed after the patch; restore it by hand"}
    created = [c["path"] for c in changes if c["old"] is None]
    _restore(changes, paths.patches_dir() / str(pid) / "backup", created)
    db.run("UPDATE patches SET status='undone' WHERE id=?", (pid,))
    try:
        from . import tools
        tools.load_plugins()
    except Exception:
        pass
    shutil.rmtree(paths.patches_dir() / str(pid) / "backup", ignore_errors=True)
    return {"ok": True}
