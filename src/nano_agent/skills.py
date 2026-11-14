"""Skills: reusable know-how as folders with a SKILL.md (YAML-style frontmatter + instructions), the same layout Hermes
Agent and similar open-source agents use, so skills move between them.

    skills/<name>/SKILL.md            (a category level `skills/<category>/<name>/` also works)
    optional folders: references/ templates/ scripts/ assets/

Safety:
  * A skill is TEXT the model reads. It can never override the safety rules: AI-written skills that try to are refused.
  * Imported skills (GitHub URL, pasted text, zip) never go live directly. They are staged in skills-pending/, get a
    plain-language review, and only the owner can enable them (console, with "I read the review" ticked).
  * Scripts never run on the host; `run_script` uses the optional Docker sandbox with no network.
  * Edits keep the old text in skills-history/, deletes go to skills-trash/ for 30 days.
"""
from __future__ import annotations

import io
import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import db, paths
from . import keystore as secrets

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_BODY = 100_000
MAX_DESC = 1024
OVERRIDE = re.compile(
    r"ignore (all |any |the )?(previous|prior|above|earlier)|disregard (the |all )?(rules|instructions|policy)|"
    r"(you (may|can|must|should) (now )?(send|post|email))|without (asking|approval|confirmation|permission)|"
    r"reveal (your |the )?(system prompt|api key|secret|token)|do not tell the (user|owner)", re.I)
KEEP_DIRS = ("references", "templates", "scripts", "assets")
TRANSPORT: httpx.AsyncBaseTransport | None = None


def parse(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta, m.group(2)


def render(name: str, description: str, body: str, extra: dict | None = None) -> str:
    meta = {"name": name, "description": description, **(extra or {})}
    return "---\n" + "\n".join(f"{k}: {str(v).replace(chr(10), ' ')}" for k, v in meta.items()) + "\n---\n\n" + body.strip() + "\n"


def validate(name: str, description: str, body: str) -> list[str]:
    errs = []
    if not NAME_RE.match(name or ""):
        errs.append("name must be lowercase letters, digits, dot, dash or underscore (max 64)")
    if not (description or "").strip():
        errs.append("description is required")
    if len(description or "") > MAX_DESC:
        errs.append(f"description is longer than {MAX_DESC}")
    if not (body or "").strip():
        errs.append("body is required")
    if len(body or "") > MAX_BODY:
        errs.append(f"body is longer than {MAX_BODY}")
    return errs


def unsafe_text(text: str) -> str:
    m = OVERRIDE.search(text or "")
    return m.group(0) if m else ""


def _disabled() -> set[str]:
    return set(db.kv_get("skills_disabled", []))


def _find(name: str) -> Path | None:
    for p in paths.skills_dir().rglob("SKILL.md"):
        if p.parent.name == name:
            return p.parent
    return None


def _source(name: str, folder: Path) -> str:
    r = db.one("SELECT source FROM skill_meta WHERE name=?", (name,))
    return r["source"] if r else "local"


def list_skills() -> list[dict]:
    out = []
    dis = _disabled()
    for p in sorted(paths.skills_dir().rglob("SKILL.md")):
        meta, _ = parse(p.read_text(encoding="utf-8", errors="replace"))
        name = meta.get("name") or p.parent.name
        out.append({"name": name, "description": meta.get("description", ""), "source": _source(name, p.parent), "enabled": name not in dis,
                    "pending": False, "path": str(p.parent.relative_to(paths.skills_dir()))})
    for p in sorted(paths.skills_pending_dir().glob("*/SKILL.md")):
        meta, _ = parse(p.read_text(encoding="utf-8", errors="replace"))
        out.append({"name": p.parent.name, "description": meta.get("description", ""), "source": "import", "enabled": False, "pending": True, "path": p.parent.name})
    return out


def view(name: str) -> dict:
    d = _find(name) or (paths.skills_pending_dir() / name if (paths.skills_pending_dir() / name / "SKILL.md").exists() else None)
    if not d:
        return {"ok": False, "error": "no such skill"}
    text = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    files = sorted(str(f.relative_to(d)) for f in d.rglob("*") if f.is_file() and f.name != "SKILL.md")
    return {"ok": True, "name": name, "text": text, "files": files, "pending": d.parent == paths.skills_pending_dir()}


def index_text() -> str:
    rows = [s for s in list_skills() if s["enabled"] and not s["pending"]]
    if not rows:
        return ""
    return "Skills you can use (read one with skill_view before following it):\n" + "\n".join(f"- {s['name']}: {s['description'][:140]}" for s in rows[:40])


def _log(kind: str, title: str, undo: dict, source: str, reason: str = "") -> None:
    from . import learning
    learning.log(kind, title, reason, source, undo)


def create(name: str, description: str, body: str, origin: str = "owner") -> dict:
    errs = validate(name, description, body)
    if errs:
        return {"ok": False, "error": "; ".join(errs)}
    if origin == "ai" and (bad := unsafe_text(description + "\n" + body)):
        return {"ok": False, "error": f"refused: a skill cannot contain '{bad}'. Skills are instructions for tasks, never for changing the safety rules."}
    if _find(name) or (paths.skills_pending_dir() / name).exists():
        return {"ok": False, "error": "a skill with that name already exists"}
    d = paths.skills_dir() / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(render(name, description, body, {"created_by": origin}), encoding="utf-8")
    db.run("INSERT OR REPLACE INTO skill_meta(name,source,origin,ts) VALUES(?,?,?,?)", (name, origin, origin, time.time()))
    _log("skill", f"Created skill {name}", {"action": "skill_delete", "name": name}, origin)
    return {"ok": True, "name": name}


def update(name: str, body: str, description: str | None = None, origin: str = "owner") -> dict:
    d = _find(name)
    if not d:
        return {"ok": False, "error": "no such skill"}
    old = (d / "SKILL.md").read_text(encoding="utf-8")
    meta, _ = parse(old)
    desc = description if description is not None else meta.get("description", "")
    errs = validate(name, desc, body)
    if errs:
        return {"ok": False, "error": "; ".join(errs)}
    if origin == "ai" and (bad := unsafe_text(desc + "\n" + body)):
        return {"ok": False, "error": f"refused: a skill cannot contain '{bad}'."}
    h = paths.skills_history_dir() / name
    h.mkdir(parents=True, exist_ok=True)
    (h / f"{int(time.time())}.md").write_text(old, encoding="utf-8")
    extra = {k: v for k, v in meta.items() if k not in ("name", "description")}
    (d / "SKILL.md").write_text(render(name, desc, body, extra), encoding="utf-8")
    _log("skill", f"Edited skill {name}", {"action": "skill_restore", "name": name}, origin)
    return {"ok": True}


def restore_last(name: str) -> dict:
    h = sorted((paths.skills_history_dir() / name).glob("*.md")) if (paths.skills_history_dir() / name).exists() else []
    d = _find(name)
    if not h or not d:
        return {"ok": False, "error": "nothing to restore"}
    (d / "SKILL.md").write_text(h[-1].read_text(encoding="utf-8"), encoding="utf-8")
    h[-1].unlink()
    return {"ok": True}


def delete(name: str, origin: str = "owner") -> dict:
    d = _find(name)
    if not d:
        return {"ok": False, "error": "no such skill"}
    dest = paths.skills_trash_dir() / f"{name}-{int(time.time())}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d), str(dest))
    _log("skill", f"Deleted skill {name}", {"action": "skill_undelete", "name": name, "trash": dest.name}, origin)
    return {"ok": True}


def undelete(name: str, trash: str) -> dict:
    src = paths.skills_trash_dir() / trash
    if not src.exists() or _find(name):
        return {"ok": False, "error": "cannot restore"}
    shutil.move(str(src), str(paths.skills_dir() / name))
    return {"ok": True}


def purge_trash(days: int = 30) -> int:
    n = 0
    for p in paths.skills_trash_dir().glob("*"):
        if time.time() - p.stat().st_mtime > days * 86400:
            shutil.rmtree(p, ignore_errors=True)
            n += 1
    return n


def set_enabled(name: str, enabled: bool, by: str = "owner", ack: bool = False) -> dict:
    pend = paths.skills_pending_dir() / name
    if pend.exists():   # enabling an import: owner only, and only after reading the review
        if by != "owner" or not ack:
            return {"ok": False, "error": "an imported skill can only be enabled by the owner after reading its review"}
        if not enabled:
            return {"ok": True}
        dest = paths.skills_dir() / "imported" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return {"ok": False, "error": "a skill with that name is already enabled"}
        shutil.move(str(pend), str(dest))
        db.run("INSERT OR REPLACE INTO skill_meta(name,source,origin,ts) VALUES(?,?,?,?)", (name, "import", "owner", time.time()))
        return {"ok": True}
    if not _find(name):
        return {"ok": False, "error": "no such skill"}
    dis = _disabled()
    (dis.discard if enabled else dis.add)(name)
    db.kv_set("skills_disabled", sorted(dis))
    return {"ok": True}


# ---- import and review ---------------------------------------------------

_PATTERNS = {
    "shell": re.compile(r"subprocess|os\.system|os\.popen|\bsudo\b|rm\s+-rf|chmod\s|curl\s|wget\s|\bbash\b|\bsh\s+-c", re.I),
    "network": re.compile(r"requests\.|httpx|urllib|socket\.|https?://(?!github\.com|docs\.)", re.I),
    "files": re.compile(r"\bopen\(|pathlib|shutil|os\.remove|os\.listdir|write_text|\.ssh|\.env", re.I),
    "dynamic code": re.compile(r"\beval\(|\bexec\(|__import__|importlib|pickle\.loads", re.I),
}


def review_dir(d: Path) -> dict:
    findings, verdict = [], "ok"
    for f in [d / "SKILL.md", *sorted(d.rglob("*"))]:
        if not f.is_file() or f.stat().st_size > 400_000:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = f.relative_to(d)
        is_script = rel.parts[0] == "scripts" or f.suffix in (".py", ".sh", ".js")
        if (m := unsafe_text(text)):
            findings.append(f"{rel}: tries to override rules ('{m[:40]}')")
            verdict = "dangerous"
        if secrets.redact(text) != text:
            findings.append(f"{rel}: contains something that looks like a secret")
            verdict = "dangerous"
        for label, rx in _PATTERNS.items():
            if rx.search(text) and (is_script or label in ("network", "shell")):
                findings.append(f"{rel}: {label} use")
                verdict = "dangerous" if verdict == "dangerous" or (label in ("shell", "dynamic code") and is_script) else "caution"
        if is_script:
            findings.append(f"{rel}: is a script (never run on your machine; only in the sandbox if enabled)")
            verdict = "caution" if verdict == "ok" else verdict
    return {"verdict": verdict, "findings": findings}


def _stage(name: str, files: dict[str, bytes]) -> dict:
    if not NAME_RE.match(name) or "SKILL.md" not in files:
        return {"ok": False, "error": "not a valid skill"}
    if _find(name) or (paths.skills_pending_dir() / name).exists():
        return {"ok": False, "error": f"'{name}' already exists"}
    d = paths.skills_pending_dir() / name
    for rel, data in files.items():
        parts = Path(rel).parts
        if rel != "SKILL.md" and not (parts[0] in KEEP_DIRS or (len(parts) == 1 and rel.endswith((".md", ".txt")))):
            continue
        if ".." in parts or Path(rel).is_absolute() or len(data) > 1_000_000:
            continue
        t = d / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_bytes(data)
    rv = review_dir(d)
    db.run("INSERT OR REPLACE INTO skill_meta(name,source,origin,ts,review) VALUES(?,?,?,?,?)", (name, "import", "import", time.time(), rv["verdict"]))
    return {"ok": True, "name": name, "review": rv}


def import_text(text: str) -> dict:
    meta, _ = parse(text)
    name = meta.get("name", "")
    errs = validate(name, meta.get("description", ""), parse(text)[1])
    return {"ok": False, "error": "; ".join(errs)} if errs else _stage(name, {"SKILL.md": text.encode()})


def import_zip(data: bytes) -> list[dict]:
    out = []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [{"ok": False, "error": "not a zip file"}]
    infos = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith("/") and ".." not in Path(i.filename).parts]
    if len(infos) > 400 or sum(i.file_size for i in infos) > 30_000_000:
        return [{"ok": False, "error": "zip is too large"}]
    roots = sorted({str(Path(i.filename).parent) for i in infos if Path(i.filename).name == "SKILL.md"})
    for root in roots[:20]:
        files = {}
        for i in infos:
            p = Path(i.filename)
            try:
                rel = p.relative_to(root) if root != "." else p
            except ValueError:
                continue
            if (i.external_attr >> 16) & 0o170000 == 0o120000:   # symlink
                continue
            files[rel.as_posix()] = z.read(i)
        meta, _ = parse(files["SKILL.md"].decode("utf-8", "replace"))
        out.append(_stage(meta.get("name") or Path(root).name, files))
    return out or [{"ok": False, "error": "no SKILL.md found in the zip"}]


async def import_github(url: str) -> list[dict]:
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in ("github.com", "www.github.com"):
        return [{"ok": False, "error": "only https://github.com/... links are accepted"}]
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        return [{"ok": False, "error": "use https://github.com/<owner>/<repo>"}]
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = parts[3] if len(parts) > 3 and parts[2] in ("tree", "blob") else "HEAD"
    if not re.fullmatch(r"[\w.-]+", owner + repo) or not re.fullmatch(r"[\w./-]+", ref):
        return [{"ok": False, "error": "unexpected characters in the link"}]
    sub = "/".join(parts[4:]) if len(parts) > 4 and parts[2] in ("tree", "blob") else ""
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, transport=TRANSPORT) as c:
        r = await c.get(f"https://codeload.github.com/{owner}/{repo}/zip/{ref}")
    if r.status_code != 200 or len(r.content) > 15_000_000:
        return [{"ok": False, "error": f"could not download (HTTP {r.status_code})"}]
    res = import_zip(r.content)
    if sub:   # keep only skills under the sub path
        res = [x for x in res if x.get("name") and sub.rstrip("/").split("/")[-1] in (x["name"], "")] or res
    return res
