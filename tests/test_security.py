"""Security properties as tests: secrets/personal-data scan over the tree and the git history, SSRF guard, sandbox flags,
the Google module can never send mail, and the LINE/console safety rules still hold in code."""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import httpx
import pytest

from nano_agent import sandbox
from nano_agent.tools import web

from .conftest import run

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src" / "nano_agent"
spec = importlib.util.spec_from_file_location("secrets_scan", ROOT / "scripts" / "secrets_scan.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


# ---------------------------------------------------------------- the scanner itself

# The patterns below are assembled at run time so this file does not contain a live-looking value.
LEAKS = {
    "sk key": "key = " + "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "google key": "x = " + "AIza" + "Sy" + "A" * 33,
    "github token": "t = " + "ghp_" + "a" * 36,
    "private key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "liff": "LIFF_ID=" + "2012" + "404947-" + "CbSaHDJC",
    "line user": "owner = " + "U" + "0123456789abcdef" * 2,
    "email": "mail me at " + "someone" + "@" + "gmail.com",
    "tailnet host": "url = https://" + "box.tail" + "0a1b2c.ts.net/x",
    "personal path": "~/" + "line-" + "assistant/app",
    "hermes home": "path ~/." + "hermes/config.yaml",
    "home path": "/home/" + "alice" + "/data",
    "bearer": "Authorization: Bearer " + "A" * 40,
    "long base64": "token=" + "Ab1/" * 40,
}


@pytest.mark.parametrize("name,line", sorted(LEAKS.items()))
def test_scanner_detects_each_kind_of_leak(name, line):
    assert scan.scan_line(line), f"scanner missed: {name}"


def test_scanner_allows_documentation_and_marked_fakes():
    ok = ["Run: nano-agent models set-key openai", "email noreply@example.com", "git@github.com:OWNER/nano-agent.git", "https://x.example.com/path",
          "key = 'abc'  # " + "sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2 scan:allow", "path ~/.nano-agent/config.toml", "/home/user/x", "co-author noreply@users.noreply.github.com"]
    for line in ok:
        assert scan.scan_line(line) == [], line


def test_findings_never_print_the_value(tmp_path, capsys, monkeypatch):
    f = tmp_path / "x.txt"
    f.write_text(LEAKS["sk key"] + "\n", encoding="utf-8")
    monkeypatch.setattr(scan, "ROOT", tmp_path)
    found = scan.scan_tree([f])
    assert found and "a1B2c3D4" not in repr(found)


# ---------------------------------------------------------------- the real repository

def test_working_tree_has_no_secrets_or_personal_data():
    assert scan.scan_tree() == []


def test_git_history_has_no_secrets_personal_data_or_coauthor_trailers():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    found = scan.scan_history()
    assert found == [], found


def test_history_scan_catches_a_secret_that_was_committed_and_later_deleted(tmp_path):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "dev@users.noreply.github.com")
    git("config", "user.name", "dev")
    (tmp_path / "a.txt").write_text(LEAKS["sk key"] + "\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "oops")
    (tmp_path / "a.txt").write_text("clean\n", encoding="utf-8")
    git("commit", "-qam", "remove it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = tmp_path
    hits = mod.scan_history()
    assert any("api key" in h[2] for h in hits)
    assert mod.scan_tree([tmp_path / "a.txt"]) == []   # the tree is clean, only the history shows it: exactly why we scan both


def test_history_scan_flags_real_author_emails_and_coauthor_lines(tmp_path):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "real.person@" + "gmail.com")
    git("config", "user.name", "dev")
    (tmp_path / "a.txt").write_text("x\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "feat\n\nCo-Authored-By: Bot <bot@" + "example.com>")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = tmp_path
    rules = {h[2] for h in mod.scan_history()}
    assert "author/committer email" in rules and "Co-Authored-By trailer" in rules


# ---------------------------------------------------------------- SSRF and web tools

@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:8099/api", "http://10.0.0.5/x", "http://192.168.1.10/", "http://169.254.169.254/latest/meta-data/",
                                 "http://[::1]/", "file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/", "http://0.0.0.0/"])
def test_web_fetch_blocks_private_and_odd_urls(url, monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["127.0.0.1"] if host == "localhost" else ["93.184.216.34"])
    r = run(web.web_fetch(url))
    assert r["ok"] is False and "blocked" in r["error"]


def test_web_fetch_blocks_a_public_name_that_resolves_to_a_private_address(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["10.1.2.3"])
    assert "blocked" in run(web.web_fetch("https://innocent.example.com/"))["error"]


def test_web_fetch_rechecks_every_redirect(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34"] if host == "ok.example.com" else ["169.254.169.254"])

    def handler(req):
        return httpx.Response(302, headers={"location": "http://metadata.example.net/secret"})
    web.TRANSPORT = httpx.MockTransport(handler)
    try:
        assert "blocked" in run(web.web_fetch("https://ok.example.com/"))["error"]
    finally:
        web.TRANSPORT = None


def test_web_fetch_extracts_text_and_search_parses_results(monkeypatch):
    monkeypatch.setattr(web, "_resolve", lambda host: ["93.184.216.34"])
    html = "<html><head><title>Hi</title><style>p{}</style></head><body><script>evil()</script><p>Hello <b>world</b></p></body></html>"
    ddg = '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa">Example A</a><a class="result__snippet">About A</a>'
    web.TRANSPORT = httpx.MockTransport(lambda req: httpx.Response(200, text=ddg if "duckduckgo" in str(req.url) else html, headers={"content-type": "text/html"}))
    try:
        r = run(web.web_fetch("https://example.org/"))
        assert r["ok"] and r["title"] == "Hi" and "Hello world" in r["text"] and "evil" not in r["text"]
        s = run(web.web_search("example"))
        assert s["results"][0] == {"title": "Example A", "url": "https://example.org/a", "snippet": "About A"}
    finally:
        web.TRANSPORT = None


# ---------------------------------------------------------------- invariants in code

def test_sandbox_container_is_locked_down_and_off_by_default():
    args = sandbox.docker_args("/tmp/w", "python:3.12-slim")
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL", "no-new-privileges", "--pids-limit", "--memory"):
        assert flag in args
    assert args[args.index("--network") + 1] == "none" and ":/work:ro" in " ".join(args)
    ok, why = sandbox.available()
    assert ok is False and "switched off" in why
    assert run(sandbox.run_python("print(1)"))["ok"] is False


def test_google_module_can_never_send_mail():
    code = (SRC / "tools" / "google.py").read_text(encoding="utf-8")
    assert not re.search(r"messages\(\)\s*\.\s*send|\.send\(|drafts\(\)\s*\.\s*send", code), "Gmail sending must never be called"
    assert "gmail.send" not in code and "https://mail.google.com/" not in code
    assert "sendUpdates=\"none\"" in code   # calendar events never notify guests


def test_there_is_no_tool_or_route_that_sends_without_approval():
    from nano_agent import tools
    names = " ".join(tools.REGISTRY)
    assert not re.search(r"send_|push_|direct", names), names
    for t in tools.REGISTRY.values():
        assert t.safety in ("read", "write", "prepare", "external")
    src = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "tools").glob("*.py"))
    assert "SENDERS[" not in src and "send_text" not in src and "approve(" not in src   # tools can reach neither the senders nor approval


def test_approve_is_only_called_from_owner_authenticated_paths():
    callers = []
    for p in SRC.rglob("*.py"):
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"drafts\.approve\(", ln):
                callers.append(f"{p.relative_to(SRC).as_posix()}:{i}")
    assert sorted(c.split(":")[0] for c in callers) == ["gateway/app.py", "gateway/line.py"], callers


def test_secrets_are_never_logged_by_the_cli_or_gateway_code():
    for p in SRC.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"print\([^)]*(api_key|channel_token|channel_secret)\b", text), p
        assert not re.search(r"logging\.[a-z]+\([^)]*(api_key|token)", text), p


def test_no_telemetry_or_unexpected_hosts_in_source():
    hosts = set()
    for p in SRC.rglob("*.py"):
        hosts |= set(re.findall(r"https?://([A-Za-z0-9.\-]+)", p.read_text(encoding="utf-8")))
    allowed = {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "openrouter.ai", "api.groq.com", "api.together.xyz", "api.deepseek.com",
               "api.line.me", "static.line-scdn.net", "codeload.github.com", "github.com", "html.duckduckgo.com", "www.googleapis.com", "localhost", "127.0.0.1",
               "platform.openai.com", "console.anthropic.com", "aistudio.google.com", "console.groq.com", "api.together.ai", "platform.deepseek.com", "developers.line.biz",
               "liff.line.me", "example.com", "OWNER", "YOUR-PUBLIC-URL", "duckduckgo.com", "developers.cloudflare.com", "docs", "schemas", "mail.google.com", "x", "....trycloudflare.com"}
    hosts = {h for h in hosts if not h.endswith(".line.me") and not h.endswith(".line-scdn.net")}
    assert hosts - allowed == set(), hosts - allowed
