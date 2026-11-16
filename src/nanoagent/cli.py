"""The `nano-agent` command line.

    setup  start  stop  status  logs  doctor  chat  token  update  uninstall
    models list|add|set-key|use|test        skills list|add|enable        line guide|pair|status        google auth        config show|set        mcp
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
import webbrowser
from pathlib import Path

from . import __version__, branding, config, i18n, keystore, paths
from .i18n import t


def _p(s: str = "") -> None:
    print(s)


def _brand(section: str = "CONSOLE") -> None:
    """Small terminal welcome; keep redirected output and scripts quiet."""
    if not sys.stdout.isatty():
        return
    columns = shutil.get_terminal_size((80, 24)).columns
    print("\n".join(["", *branding.banner(section, version=__version__, width=columns), ""]))


def _open_console() -> None:
    url = console_url(with_token=True)
    _p("Opening your private console in the browser…")
    if os.environ.get("WSL_DISTRO_NAME") and shutil.which("explorer.exe"):
        try:
            subprocess.Popen(["explorer.exe", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    if not webbrowser.open(url):
        _p("Could not open a browser automatically. Run `nano-agent token` for your sign-in link.")


# ---------------------------------------------------------------- daemon

def _pid() -> int | None:
    try:
        pid = int(paths.pid_path().read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            return pid if str(pid) in out else None
        os.kill(pid, 0)
        return pid
    except (OSError, ProcessLookupError):
        return None


def _health(cfg: dict) -> bool:
    import httpx
    try:
        return httpx.get(f"http://{cfg['gateway']['host']}:{cfg['gateway']['port']}/healthz", timeout=1.5).status_code == 200
    except Exception:
        return False


def console_url(cfg: dict | None = None, with_token: bool = False) -> str:
    cfg = cfg or config.load()
    g = cfg["gateway"]
    base = (g["public_url"] or f"http://{g['host']}:{g['port']}").rstrip("/") + "/console"
    return base + ("#token=" + (keystore.get("owner.token") or "") if with_token else "")


def cmd_start(a) -> int:
    cfg = config.load()
    if not paths.config_path().exists():
        _p(t("cli.need_setup"))
        return 1
    if (pid := _pid()) and _health(cfg):
        _p(t("cli.already_running", pid=pid))
        if getattr(a, "open", False):
            _open_console()
        return 0
    if a.foreground:
        from .gateway import app
        app.serve()
        return 0
    paths.ensure_dirs()
    log = open(paths.logs_dir() / "gateway.log", "ab")
    kw: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen([sys.executable, "-m", "nanoagent", "serve"], **kw)
    paths.pid_path().write_text(str(proc.pid))
    if sys.stdout.isatty() and getattr(a, "show_brand", True):
        _brand()
        _p("  Starting your local assistant…")
    for attempt in range(40):
        if _health(cfg):
            _p(t("cli.started", url=console_url(cfg)))
            if getattr(a, "open", False):
                _open_console()
            else:
                _p(t("cli.token_hint"))
            return 0
        if proc.poll() is not None:
            break
        if sys.stdout.isatty():
            frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
            print(f"\r  {frames[attempt % len(frames)]} Loading console and checking services…", end="", flush=True)
        time.sleep(0.25)
    if sys.stdout.isatty():
        print()
    _p(t("cli.start_failed", log=str(paths.logs_dir() / "gateway.log")))
    return 1


def cmd_stop(_a) -> int:
    pid = _pid()
    if not pid:
        _p(t("cli.not_running"))
        return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(40):
                time.sleep(0.25)
                if not _pid():
                    break
    finally:
        paths.pid_path().unlink(missing_ok=True)
    _p(t("cli.stopped"))
    return 0


def cmd_status(a) -> int:
    cfg = config.load()
    pid = _pid()
    ok = _health(cfg)
    info = {"running": bool(pid and ok), "pid": pid, "console": console_url(cfg), "model": cfg["models"]["chat"] or None, "line": cfg["line"]["enabled"],
            "line_paired": bool(cfg["line"]["owner_user_id"]), "home": str(paths.home()), "version": __version__}
    if a.json:
        _p(json.dumps(info, indent=2))
    else:
        _p(f"nano-agent {__version__}: " + (t("cli.status_running", pid=pid) if info["running"] else t("cli.status_stopped")))
        _p(f"  {t('cli.status_console')}: {info['console']}\n  {t('cli.status_model')}: {info['model'] or '-'}\n  LINE: " + ("paired" if info["line_paired"] else "on, not paired" if info["line"] else "off") + f"\n  {t('cli.status_home')}: {info['home']}")
    return 0 if info["running"] else 3


def cmd_logs(a) -> int:
    f = paths.logs_dir() / "gateway.log"
    if not f.exists():
        _p(t("cli.no_logs"))
        return 1
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-a.n:]
    for ln in lines:
        _p(keystore.redact(ln))
    if a.follow:
        with open(f, encoding="utf-8", errors="replace") as fh:
            fh.seek(0, 2)
            try:
                while True:
                    ln = fh.readline()
                    if ln:
                        print(keystore.redact(ln.rstrip()))
                    else:
                        time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    return 0


# ---------------------------------------------------------------- setup and friends

def cmd_setup(a) -> int:
    from . import wizard
    if a.non_interactive:
        ans = wizard.from_args(a)
        s = wizard.apply(ans)
        i18n.set_language(ans["language"])
        _p(t("setup.saved", home=s["home"]))
        if not a.skip_test:
            ok, msg = wizard.test_model()
            _p((t("setup.test_ok", msg=msg) if ok else t("setup.test_fail", msg=msg)))
            if not ok and a.strict:
                return 2
        return 0
    with wizard.setup_screen():
        rc = wizard.run_interactive()
        if rc == 0:
            from . import doctor
            ui = wizard.TerminalUI()
            checks = doctor.checks(offline=True)
            if ui._tty:
                ui.section = "Finish"
                passed = sum(c["level"] == "ok" for c in checks)
                issues = [f"!  {c['name']}: {c['detail']}" for c in checks if c["level"] in ("warn", "fail")]
                ui._frame("Setup complete", [f"{passed} system checks passed.",
                                             *(issues or ["Your assistant is ready."])],
                          "Enter → Open console and chat" if not a.no_start else "Enter → Close setup")
                ui._read_key()
            else:
                doctor.run(offline=True)
    if rc == 0:
        if not a.no_start:
            return cmd_launch(argparse.Namespace(no_browser=False, no_chat=False))
        if not ui._tty:
            _p(t("setup.next_steps"))
    return rc


def cmd_doctor(a) -> int:
    from . import doctor
    return doctor.run(offline=a.offline, as_json=a.json)


def cmd_token(a) -> int:
    from .gateway import auth
    if a.rotate:
        keystore.delete("owner.token")   # old browser sessions stop working at once: the session cookie is derived from the token
        _p(t("cli.token_rotated"))
    auth.owner_token()
    _p(t("cli.token_warn"))
    _p(console_url(with_token=True))
    return 0


def cmd_chat(a) -> int:
    from .agent import Agent
    if not config.get(config.load(), "models.chat"):
        _p(t("cli.need_setup"))
        return 1
    agent = Agent()
    if a.text:
        _p(asyncio.run(agent.run(" ".join(a.text), session="cli")).text)
        return 0
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        _brand("CHAT")
        for row in branding.card("Terminal chat", ["Your assistant is ready.", "",
                                                    "/dashboard  Open the web console",
                                                    "/help  Show commands   /quit  Leave chat"],
                                 width=shutil.get_terminal_size((80, 24)).columns):
            _p(row)
        _p()
    else:
        _p(t("cli.chat_hint"))
    while True:
        try:
            prompt = "\x1b[1;38;2;255;112;32myou › \x1b[0m" if interactive else "> "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            if interactive:
                _p("\n  Chat closed. The dashboard keeps running; use nano-agent stop to stop it.")
            return 0
        if line in ("/quit", "/exit"):
            return 0
        if line == "/dashboard":
            _open_console()
            continue
        if line == "/help":
            _p("  /dashboard  Open the web console\n  /quit       Leave terminal chat\n  /help       Show these commands")
            continue
        if line:
            try:
                reply = asyncio.run(agent.run(line, session="cli")).text
                if interactive:
                    _p("\n\x1b[1;38;2;255;112;32mnano Agent ›\x1b[0m")
                    width = max(40, shutil.get_terminal_size((80, 24)).columns - 4)
                    _p("\n".join(textwrap.fill(part, width=width, replace_whitespace=False) if part else ""
                                 for part in reply.split("\n")) + "\n")
                else:
                    _p(reply)
            except Exception:
                _p("  Could not get a response. Run nano-agent doctor to check the model connection.")


def cmd_launch(a) -> int:
    """Open the dashboard and enter terminal chat in one command."""
    if not config.get(config.load(), "models.chat"):
        if not sys.stdin.isatty():
            _p("No model is configured yet. Run nano-agent setup in a terminal.")
            return 1
        _p("No model is configured yet. Starting setup…")
        return cmd_setup(argparse.Namespace(non_interactive=False, no_start=False))
    rc = cmd_start(argparse.Namespace(foreground=False, open=not a.no_browser,
                                      show_brand=a.no_chat or not sys.stdin.isatty()))
    if rc or a.no_chat or not sys.stdin.isatty():
        return rc
    return cmd_chat(argparse.Namespace(text=[]))


def cmd_update(_a) -> int:
    prefix = sys.prefix.replace("\\", "/")
    if "/pipx/" in prefix:
        cmd = ["pipx", "upgrade", "nano-agent"]
    elif "/uv/tools/" in prefix:
        cmd = ["uv", "tool", "upgrade", "nano-agent"]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "nano-agent"]
    _p(t("cli.update_running", cmd=" ".join(cmd)))
    rc = subprocess.call(cmd)
    if rc == 0:
        _p(t("cli.update_restart"))
    return rc


def cmd_uninstall(a) -> int:
    home = paths.home()
    _p(t("cli.uninstall_plan", home=str(home)))
    cmd_stop(a)
    if a.purge:
        if not a.yes and input(t("cli.uninstall_confirm", home=str(home)) + " ").strip() != "delete":
            _p(t("cli.aborted"))
            return 1
        shutil.rmtree(home, ignore_errors=True)
        paths.pointer_file().unlink(missing_ok=True)
        _p(t("cli.purged"))
    else:
        _p(t("cli.keep_data", home=str(home)))
    _p(t("cli.uninstall_pkg"))
    return 0


# ---------------------------------------------------------------- models, skills, line, google, config

def cmd_models(a) -> int:
    from .providers import make_provider
    from .providers.presets import PRESETS
    cfg = config.load()
    if a.sub == "list":
        for n, p in cfg["providers"].items():
            _p(f"{n}: {p['kind']} {p['base_url']}  key: {keystore.mask(keystore.get(p.get('key_ref', 'provider.' + n)))}")
        for r in ("chat", "fast", "vision"):
            _p(f"model {r}: {cfg['models'][r] or '-'}")
        return 0
    if a.sub == "add":
        if a.provider not in PRESETS:
            _p("unknown provider; choose: " + ", ".join(PRESETS))
            return 2
        pre = PRESETS[a.provider]
        name = a.name or a.provider
        cfg["providers"][name] = {"kind": pre["kind"], "base_url": a.base_url or pre["base_url"], "key_ref": f"provider.{name}"}
        key = os.environ.get(a.api_key_env, "") if a.api_key_env else (sys.stdin.readline().strip() if a.api_key_stdin else (__import__("getpass").getpass("API key (hidden, leave empty for none): ") if pre["needs_key"] else ""))
        if key:
            keystore.set_(f"provider.{name}", key)
        if a.model:
            cfg["models"][a.role] = f"{name}/{a.model}"
        elif not cfg["models"]["chat"] and pre["chat"]:
            cfg["models"]["chat"] = f"{name}/{pre['chat']}"
        config.save(cfg)
        _p(t("cli.model_added", name=name))
        return 0
    if a.sub == "set-key":
        if a.name not in cfg["providers"]:
            _p("no such provider: " + a.name)
            return 2
        key = os.environ.get(a.api_key_env, "") if a.api_key_env else (sys.stdin.readline().strip() if a.api_key_stdin else __import__("getpass").getpass("API key (hidden): ").strip())
        if not key:
            _p("no key given")
            return 2
        keystore.set_(cfg["providers"][a.name].get("key_ref", f"provider.{a.name}"), key)
        _p(t("cli.key_saved", name=a.name, masked=keystore.mask(key)))
        return 0
    if a.sub == "use":
        if "/" not in a.ref:
            _p("use the form provider/model, e.g. openai/gpt-4o")
            return 2
        cfg["models"][a.role] = a.ref
        config.save(cfg)
        return 0
    if a.sub == "test":
        roles = ["chat", "fast", "vision"] if a.all else [a.role]
        bad = 0
        for r in roles:
            pname, model = config.model_for(cfg, r)
            if not pname or not model:
                _p(f"{r}: not configured")
                continue
            try:
                ok, msg = asyncio.run(make_provider(cfg, pname).ping(model))
            except Exception as e:
                ok, msg = False, keystore.redact(e)
            bad += 0 if ok else 1
            _p(f"{'✓' if ok else '✗'} {r}: {pname}/{model} - {msg}")
        return 1 if bad else 0
    return 2


def cmd_skills(a) -> int:
    from . import skills
    if a.sub == "list":
        for s in skills.list_skills():
            _p(f"{'[pending] ' if s['pending'] else ''}{s['name']}{'' if s['enabled'] else ' (off)'}: {s['description'][:80]}")
        return 0
    if a.sub == "add":
        src = a.source
        if src == "-":
            res = [skills.import_text(sys.stdin.read())]
        elif src.startswith("https://"):
            res = asyncio.run(skills.import_github(src))
        else:
            pth = Path(src).expanduser()
            if pth.is_dir():
                import io
                import zipfile
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as z:
                    for f in pth.rglob("*"):
                        if f.is_file():
                            z.write(f, f.relative_to(pth.parent).as_posix() if (pth / "SKILL.md").exists() else f.relative_to(pth).as_posix())
                res = skills.import_zip(buf.getvalue())
            elif pth.suffix == ".zip":
                res = skills.import_zip(pth.read_bytes())
            else:
                res = [skills.import_text(pth.read_text(encoding="utf-8"))]
        for r in res:
            _p(("staged: " + r["name"] + f" (review: {r['review']['verdict']})") if r.get("ok") else "failed: " + r.get("error", ""))
        _p(t("cli.skills_pending_hint"))
        return 0
    if a.sub == "enable":
        d = paths.skills_pending_dir() / a.name
        if d.exists():
            rv = skills.review_dir(d)
            _p(f"review: {rv['verdict']}\n" + "\n".join("  - " + f for f in rv["findings"]))
            if not a.yes and input(t("cli.skill_ack") + " ").strip().lower() not in ("y", "yes"):
                return 1
        r = skills.set_enabled(a.name, True, by="owner", ack=True)
        _p("ok" if r["ok"] else r["error"])
        return 0 if r["ok"] else 1
    return 2


def cmd_line(a) -> int:
    from .gateway import line
    cfg = config.load()
    if a.sub == "guide":
        _p(t("line.guide"))
        _p(t("line.webhook_url", url=(cfg["gateway"]["public_url"] or "https://YOUR-PUBLIC-URL").rstrip("/") + "/webhook/line"))
        return 0
    if a.sub == "setup":
        import getpass
        _p(t("line.guide"))
        sec = getpass.getpass(t("setup.line_secret_q") + ": ").strip()
        tok = getpass.getpass(t("setup.line_token_q") + ": ").strip()
        liff = input(t("setup.line_liff_q") + ": ").strip()
        cfg["line"]["enabled"], cfg["line"]["liff_id"] = True, liff
        keystore.set_("line.channel_secret", sec)
        keystore.set_("line.channel_token", tok)
        config.save(cfg)
        _p(t("line.saved"))
        return 0
    if a.sub == "pair":
        if not cfg["line"]["enabled"]:
            _p(t("line.not_enabled"))
            return 1
        cfg["line"]["owner_user_id"] = ""
        config.save(cfg)
        _p(t("line.pair", code=line.new_pair_code()))
        return 0
    if a.sub == "status":
        _p(f"enabled: {cfg['line']['enabled']}  paired: {bool(cfg['line']['owner_user_id'])}  secret: {keystore.mask(keystore.get('line.channel_secret'))}  token: {keystore.mask(keystore.get('line.channel_token'))}")
        return 0
    return 2


def cmd_google(a) -> int:
    from .tools import google
    ok, why = google.available()
    if a.sub == "auth":
        try:
            google.auth_flow(a.client_secret)
        except ImportError:
            _p("Install the Google extra first: pip install 'nano-agent[google]'")
            return 1
        _p("Google connected (calendar events + Gmail drafts only; nothing is ever sent).")
        return 0
    _p("connected" if ok else why)
    return 0 if ok else 1


def cmd_config(a) -> int:
    cfg = config.load()
    if a.sub == "show":
        _p(config.dumps(cfg))
        _p("# secrets are in " + str(paths.secrets_path()) + " and are never shown: " + ", ".join(keystore.names()))
        return 0
    cur = config.get(cfg, a.key)
    if cur is None and "." not in a.key:
        _p("use section.key, e.g. gateway.port")
        return 2
    val: object = a.value
    if isinstance(cur, bool):
        val = a.value.lower() in ("1", "true", "yes", "on")
    elif isinstance(cur, int):
        val = int(a.value)
    config.set_(cfg, a.key, val)
    config.save(cfg)
    return 0


def cmd_serve(_a) -> int:
    from .gateway import app
    app.serve()
    return 0


def cmd_mcp(_a) -> int:
    from .tools import mcp_server
    mcp_server.main()
    return 0


# ---------------------------------------------------------------- sandbox workspace (N8 to N10)

def _out(r: dict) -> int:
    _p(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    return 0 if r.get("ok", True) else 1


def cmd_sandbox(a) -> int:
    from . import sandbox_ws as ws
    from . import supervisor as sv
    from .sandbox_runtime import DockerRuntime
    if a.sub == "status":
        st = sv.read_state()
        return _out({"config": ws.status(), "supervisor": {k: st[k] for k in ("state", "lease_until", "session_until", "trip", "reviewed", "freeze_ms", "kill_latency_ms")},
                     "audit_chain_ok": ws.verify_chain()[0]})
    if a.sub == "enable":
        ok, why = DockerRuntime().available()
        if not ok:
            _p(why)
            return 1
        if not a.yes:
            _p(t("sandbox.notice"))
            _p(t("sandbox.enable_again"))
            return 1
        cfg = config.load()
        cfg["sandbox"]["workspace"] = True
        config.save(cfg)
        ws.plant_canaries()
        _p(t("sandbox.enabled", tier=ws.settings()["tier"]))
        return 0
    if a.sub == "disable":
        cfg = config.load()
        cfg["sandbox"]["workspace"] = False
        config.save(cfg)
        _p(t("sandbox.disabled"))
        return 0
    if a.sub == "tier":
        cfg = config.load()
        cfg["sandbox"]["tier"] = a.tier
        cfg["sandbox"]["allowed_domains"] = [d.strip() for d in (a.domains or "").split(",") if d.strip()]
        config.save(cfg)
        _p(t("sandbox.tier_set", tier=a.tier))
        return 0
    if a.sub == "snapshot":
        return _out(ws.snapshot(a.label))
    if a.sub == "restore" and a.list:
        return _out({"ok": True, "snapshots": ws.list_snapshots()})
    if a.sub == "restore":
        return _out(sv.command("rollback", a.snapshot))
    if a.sub == "review":
        r = sv.command("review")
        return _out(r) if not r.get("ok") else _out({**r, "note": t("sandbox.review_note")})
    if a.sub == "supervise":
        sup = sv.Supervisor(runtime=DockerRuntime())
        _p(t("sandbox.supervising"))
        try:
            sup.run_forever(every=a.every)
        except KeyboardInterrupt:
            return 130
        return 0
    cmd = {"start": "session_start", "pause": "pause", "resume": "resume", "stop": "stop", "kill": "kill"}[a.sub]
    return _out(sv.command(cmd))


def cmd_kill(_a) -> int:
    from . import supervisor as sv
    return _out(sv.command("kill"))


def cmd_redteam(a) -> int:
    from . import providers, redteam
    from . import sandbox_ws as ws
    from .sandbox_runtime import DockerRuntime
    cfg = config.load()
    ok, why = DockerRuntime().available()
    if not ok:
        _p(why)
        return 1
    prov, model = None, config.model_for(cfg, "chat")[1]
    if a.provider:
        prov = providers.make_provider(cfg, a.provider)
    elif cfg["models"]["chat"]:
        prov, model = providers.for_role(cfg, "chat")
    if prov is None:
        _p(t("sandbox.redteam_needs_model"))
        return 1
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = paths.home() / "redteam" / stamp
    card = redteam.run_suite(provider=prov, tier=a.tier or ws.settings()["tier"], runtime=DockerRuntime(), model=model, evidence_dir=out_dir)
    jp, mp = redteam.write_reports(card, out_dir)
    _p(mp.read_text(encoding="utf-8"))
    _p(t("sandbox.report_written", path=str(jp)))
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nano-agent", description="nano Agent: a small, private, open-source personal AI assistant.")
    ap.add_argument("--version", action="version", version=f"nano-agent {__version__}")
    sp = ap.add_subparsers(dest="cmd")

    s = sp.add_parser("setup", help="interactive setup wizard (or --non-interactive)")
    s.add_argument("--non-interactive", action="store_true")
    s.add_argument("--language", choices=["en", "th"])
    s.add_argument("--name")
    s.add_argument("--timezone")
    s.add_argument("--provider")
    s.add_argument("--model")
    s.add_argument("--fast-model")
    s.add_argument("--base-url")
    k = s.add_mutually_exclusive_group()
    k.add_argument("--api-key-env", metavar="VAR", help="read the API key from this environment variable")
    k.add_argument("--api-key-file", metavar="FILE")
    k.add_argument("--api-key-stdin", action="store_true")
    s.add_argument("--exposure", choices=["local", "tailscale", "cloudflare", "domain"])
    s.add_argument("--public-url")
    s.add_argument("--home")
    s.add_argument("--line-secret-env", metavar="VAR")
    s.add_argument("--line-token-env", metavar="VAR")
    s.add_argument("--liff-id")
    s.add_argument("--no-voice", action="store_true")
    s.add_argument("--sandbox", action="store_true")
    s.add_argument("--skip-test", action="store_true", help="do not call the model at the end")
    s.add_argument("--strict", action="store_true", help="non-zero exit if the model test fails")
    s.add_argument("--no-start", action="store_true")
    s.set_defaults(fn=cmd_setup)

    s = sp.add_parser("start", help="start the gateway in the background")
    s.add_argument("--foreground", action="store_true")
    s.add_argument("--open", action="store_true", help="open the signed-in private console in your browser")
    s.set_defaults(fn=cmd_start)
    s = sp.add_parser("launch", help="open the dashboard and enter terminal chat")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--no-chat", action="store_true")
    s.set_defaults(fn=cmd_launch)
    sp.add_parser("stop", help="stop the gateway").set_defaults(fn=cmd_stop)
    s = sp.add_parser("status")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sp.add_parser("logs")
    s.add_argument("-n", type=int, default=50)
    s.add_argument("-f", "--follow", action="store_true")
    s.set_defaults(fn=cmd_logs)
    s = sp.add_parser("doctor", help="check the installation")
    s.add_argument("--offline", action="store_true", help="skip the model call")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_doctor)
    s = sp.add_parser("token", help="print the console login URL (contains your secret token)")
    s.add_argument("--rotate", action="store_true", help="create a new token and log out every browser")
    s.set_defaults(fn=cmd_token)
    s = sp.add_parser("chat", help="talk to the assistant in the terminal")
    s.add_argument("text", nargs="*")
    s.set_defaults(fn=cmd_chat)
    sp.add_parser("update", help="upgrade nano Agent").set_defaults(fn=cmd_update)
    s = sp.add_parser("uninstall", help="stop and (optionally) delete your data")
    s.add_argument("--purge", action="store_true", help="also delete the data folder")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(fn=cmd_uninstall)

    m = sp.add_parser("models", help="manage AI providers and models")
    ms = m.add_subparsers(dest="sub", required=True)
    ms.add_parser("list")
    x = ms.add_parser("add")
    x.add_argument("provider")
    x.add_argument("--name")
    x.add_argument("--base-url")
    x.add_argument("--model")
    x.add_argument("--role", default="chat", choices=["chat", "fast", "vision"])
    x.add_argument("--api-key-env", metavar="VAR")
    x.add_argument("--api-key-stdin", action="store_true")
    x = ms.add_parser("set-key")
    x.add_argument("name")
    x.add_argument("--api-key-env", metavar="VAR")
    x.add_argument("--api-key-stdin", action="store_true")
    x = ms.add_parser("use")
    x.add_argument("role", choices=["chat", "fast", "vision"])
    x.add_argument("ref", help="provider/model")
    x = ms.add_parser("test", help="one tiny call that checks the key, URL and model")
    x.add_argument("--role", default="chat", choices=["chat", "fast", "vision"])
    x.add_argument("--all", action="store_true")
    m.set_defaults(fn=cmd_models)

    m = sp.add_parser("skills")
    ms = m.add_subparsers(dest="sub", required=True)
    ms.add_parser("list")
    x = ms.add_parser("add", help="import a skill from a folder, zip, SKILL.md, github URL or - (stdin); it stays off until you enable it")
    x.add_argument("source")
    x = ms.add_parser("enable")
    x.add_argument("name")
    x.add_argument("--yes", action="store_true")
    m.set_defaults(fn=cmd_skills)

    m = sp.add_parser("line", help="LINE connector helpers")
    ms = m.add_subparsers(dest="sub", required=True)
    for n in ("guide", "setup", "pair", "status"):
        ms.add_parser(n)
    m.set_defaults(fn=cmd_line)
    m = sp.add_parser("google", help="optional Google connection")
    ms = m.add_subparsers(dest="sub", required=True)
    x = ms.add_parser("auth")
    x.add_argument("--client-secret", required=True)
    ms.add_parser("status")
    m.set_defaults(fn=cmd_google)
    m = sp.add_parser("config")
    ms = m.add_subparsers(dest="sub", required=True)
    ms.add_parser("show")
    x = ms.add_parser("set")
    x.add_argument("key")
    x.add_argument("value")
    m.set_defaults(fn=cmd_config)
    m = sp.add_parser("sandbox", help="sandbox workspace: enable, tiers, supervisor, kill switch, snapshots")
    ms = m.add_subparsers(dest="sub", required=True)
    ms.add_parser("status")
    x = ms.add_parser("enable", help="turn the workspace on (needs Docker); prints the first-run notice")
    x.add_argument("--yes", action="store_true", help="accept the notice")
    x.add_argument("--tier", choices=["T0", "T1", "T2", "T3"])
    ms.add_parser("disable")
    x = ms.add_parser("tier", help="set the tier (owner only; the agent cannot change it)")
    x.add_argument("tier", choices=["T0", "T1", "T2", "T3"])
    x.add_argument("--domains", default="", help="comma-separated allowlist for T1")
    for n in ("start", "pause", "resume", "stop", "kill", "review"):
        ms.add_parser(n)
    x = ms.add_parser("snapshot")
    x.add_argument("--label", default="manual")
    x = ms.add_parser("restore")
    x.add_argument("snapshot", nargs="?", default="")
    x.add_argument("--list", action="store_true")
    x = ms.add_parser("supervise", help="run the supervisor loop (lease, tripwires); keep it running while the sandbox works")
    x.add_argument("--every", type=float, default=2.0)
    m.set_defaults(fn=cmd_sandbox)
    sp.add_parser("kill", help="kill switch: stop and remove the sandbox container now").set_defaults(fn=cmd_kill)
    m = sp.add_parser("redteam", help="run the red-team scenarios against the sandbox")
    ms = m.add_subparsers(dest="sub", required=True)
    x = ms.add_parser("run")
    x.add_argument("--tier", choices=["T0", "T1", "T2", "T3"])
    x.add_argument("--provider", help="configured provider name (default: your chat model)")
    m.set_defaults(fn=cmd_redteam)
    sp.add_parser("serve", help="run the gateway in the foreground").set_defaults(fn=cmd_serve)
    sp.add_parser("mcp", help="MCP stdio server (needs the mcp extra)").set_defaults(fn=cmd_mcp)
    return ap


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print("nano-agent needs Python 3.11 or newer.", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        if (argv is None or not argv) and sys.stdin.isatty() and sys.stdout.isatty():
            return cmd_launch(argparse.Namespace(no_browser=False, no_chat=False))
        ap.print_help()
        return 0
    try:
        return int(a.fn(a) or 0)
    except KeyboardInterrupt:
        return 130
