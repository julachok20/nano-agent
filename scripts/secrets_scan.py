#!/usr/bin/env python3
"""Secrets and personal-data scan for the working tree AND the git history. Used by the test suite and CI.

    python scripts/secrets_scan.py            # scan the working tree (tracked + untracked, not ignored)
    python scripts/secrets_scan.py --history  # scan every line ever added in git history, plus author emails and messages

Findings print as `path:line: rule` and NEVER the matched value. Exit code 1 when anything is found.
A line containing `scan:allow` is skipped (use it only for obviously fake test values).
It complements `gitleaks` (CI runs both); this one also knows the personal identifiers that must never reach a public repo.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = {"scripts/secrets_scan.py"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "build", "dist", ".mypy_cache"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".whl", ".gz", ".pyc", ".db", ".sqlite"}
ALLOWED_EMAIL = re.compile(r"(@example\.(com|org|net)$|@users\.noreply\.github\.com$|^noreply@|@localhost$|^git@github\.com$|\.invalid$)", re.I)

RULES: list[tuple[str, re.Pattern]] = [
    ("api key (sk-)", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("groq key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")),
    ("slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{10,}")),
    ("aws key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{30,}")),
    ("long base64 secret (LINE token shape)", re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{120,}={0,2}(?![A-Za-z0-9+/])")),
    ("LIFF id", re.compile(r"\b\d{10}-[A-Za-z0-9]{8}\b")),
    ("LINE user id", re.compile(r"\bU[0-9a-f]{32}\b")),
    ("LINE basic id", re.compile(r"@\d{3}[a-z]{4}\b")),
    ("tailnet host", re.compile(r"[A-Za-z0-9-]+\.tail[0-9a-f]{4,}\.ts\.net", re.I)),
    ("personal identifier", re.compile(r"julachok|pgaslg|jul-sbw|spark-4a46|tail047979|970didqa|fdf288ca|2012404947|line-relay|line-assistant|\.hermes\b|assistant\.env", re.I)),
    ("owner project / school", re.compile(r"maus ?bot|postiz|saraburi|witthayakhom|สระบุรี|vllm-gemma", re.I)),
    ("home path of a real user", re.compile(r"/home/(?!user\b|you\b|me\b|\$|<)[a-z][a-z0-9_-]{2,}/|C:\\Users\\(?!you\b|user\b|<)[A-Za-z0-9_.-]{3,}\\", re.I)),
]
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
QUOTED = re.compile(r"[\"']([A-Za-z0-9_\-+/=]{32,})[\"']")


def entropy(s: str) -> float:
    return -sum((s.count(c) / len(s)) * math.log2(s.count(c) / len(s)) for c in set(s))


def scan_line(line: str) -> list[str]:
    if "scan:allow" in line:
        return []
    hits = [name for name, rx in RULES if rx.search(line)]
    for m in EMAIL.finditer(line):
        if not ALLOWED_EMAIL.search(m.group(0)):
            hits.append("email address")
            break
    for m in QUOTED.finditer(line):
        s = m.group(1)
        if entropy(s) > 4.6 and not re.fullmatch(r"[0-9a-f]+", s) and "/" not in s[:2]:
            hits.append("high-entropy string")
            break
    return hits


def scan_text(text: str, name: str = "<text>") -> list[tuple[str, int, str]]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for rule in scan_line(line):
            out.append((name, i, rule))
    return out


def tracked_files() -> list[Path]:
    try:
        r = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
        files = [ROOT / p for p in r.stdout.splitlines() if p]
    except Exception:
        files = [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]
    return [f for f in files if f.is_file() and f.suffix.lower() not in SKIP_EXT and not (set(f.relative_to(ROOT).parts) & SKIP_DIRS)]


def scan_tree(root_files: list[Path] | None = None) -> list[tuple[str, int, str]]:
    found = []
    for f in root_files if root_files is not None else tracked_files():
        rel = f.relative_to(ROOT).as_posix()
        if rel in SELF:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += scan_text(text, rel)
        for rule, rx in (("personal file name", re.compile(r"\.bak|\.env$|credentials|token.*\.json|secrets\.toml|\.sqlite|\.db$", re.I)),):
            if rx.search(f.name) and f.name not in (".env.example",):
                found.append((rel, 0, rule))
    return found


def scan_history() -> list[tuple[str, int, str]]:
    found: list[tuple[str, int, str]] = []
    try:
        meta = subprocess.run(["git", "log", "--all", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x01"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    except subprocess.CalledProcessError:
        return found
    for rec in meta.split("\x01"):
        parts = rec.strip().split("\x00")
        if len(parts) < 6:
            continue
        sha, ae, ce, msg = parts[0][:8], parts[2], parts[4], parts[5]
        for em in (ae, ce):
            if em and not ALLOWED_EMAIL.search(em):
                found.append((f"commit {sha}", 0, "author/committer email"))
        for rule in {r for ln in msg.splitlines() for r in scan_line(ln)}:
            found.append((f"commit {sha} message", 0, rule))
        if re.search(r"co-authored-by", msg, re.I):
            found.append((f"commit {sha} message", 0, "Co-Authored-By trailer"))
    log = subprocess.run(["git", "log", "--all", "-p", "--no-color", "--format=commit %h"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    commit, path = "?", "?"
    for ln in log.splitlines():
        if ln.startswith("commit "):
            commit = ln[7:]
        elif ln.startswith("+++ b/"):
            path = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++") and path not in SELF:
            for rule in scan_line(ln[1:]):
                found.append((f"{commit}:{path}", 0, rule))
    return sorted(set(found))


def main(argv: list[str]) -> int:
    findings = scan_history() if "--history" in argv else scan_tree()
    for path, line, rule in findings:
        print(f"{path}:{line}: {rule}")
    print(f"secrets scan ({'history' if '--history' in argv else 'tree'}): {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
