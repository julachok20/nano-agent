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
import time
from pathlib import Path

from . import __version__, config, i18n, keystore, paths
from .i18n import t


def _p(s: str = "") -> None:
    print(s)


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
    for _ in range(40):
        if _health(cfg):
            _p(t("cli.started", url=console_url(cfg)))
            _p(t("cli.token_hint"))
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.25)
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
    rc = wizard.run_interactive()
    if rc == 0:
        from . import doctor
        _p("")
        doctor.run(offline=True)
        if not a.no_start and wizard.Prompter().yes(t("setup.start_q"), True):
            return cmd_start(argparse.Namespace(foreground=False))
        _p(t("setup.next_steps"))
    return rc


def cmd_doctor(a) -> int:
    from . import doctor
    return doctor.run(offline=a.offline, as_json=a.json)


def cmd_token(_a) -> int:
    from .gateway import auth
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
    _p(t("cli.chat_hint"))
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if line in ("/quit", "/exit"):
            return 0
        if line:
            _p(asyncio.run(agent.run(line, session="cli")).text)


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
    s.set_defaults(fn=cmd_start)
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
    sp.add_parser("token", help="print the console login URL (contains your secret token)").set_defaults(fn=cmd_token)
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
        ap.print_help()
        return 0
    try:
        return int(a.fn(a) or 0)
    except KeyboardInterrupt:
        return 130
