"""`nano-agent setup`: the terminal wizard, plus the non-interactive path used by CI and scripts.

Both paths end in `apply(answers)`, which writes config.toml and the 0600 secrets file. The interactive path only asks;
it never writes anything until the end, and Ctrl+C leaves the machine untouched.

API keys are read with getpass (never echoed), from an environment variable you name (`--api-key-env`), from a file, or
from stdin. There is deliberately no `--api-key VALUE` flag: command lines are visible to other users in the process list.
"""
from __future__ import annotations

import asyncio
import getpass
import os
import shutil
import sys
import zoneinfo

from . import __version__, branding, config, db, i18n, keystore, paths
from .i18n import t
from .providers import make_provider
from .providers.presets import ORDER, PRESETS


class Prompter:
    def __init__(self, input_fn=input, secret_fn=getpass.getpass, out=print):
        self.input, self.secret_fn, self.out = input_fn, secret_fn, out

    def say(self, text: str = "") -> None:
        self.out(text)

    def ask(self, q: str, default: str = "") -> str:
        v = self.input(f"{q}" + (f" [{default}]" if default else "") + ": ").strip()
        return v or default

    def secret(self, q: str) -> str:
        return self.secret_fn(f"{q}: ").strip()

    def yes(self, q: str, default: bool = True) -> bool:
        v = self.input(f"{q} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        return default if not v else v[0] in ("y", "ย")

    def choose(self, q: str, options: list[tuple[str, str]], default: str) -> str:
        self.say(q)
        for i, (_, label) in enumerate(options, 1):
            self.say(f"  {i}) {label}")
        keys = [k for k, _ in options]
        while True:
            v = self.input(f"  > [{keys.index(default) + 1}]: ").strip()
            if not v:
                return default
            if v.isdigit() and 1 <= int(v) <= len(keys):
                return keys[int(v) - 1]
            if v in keys:
                return v
            self.say("  ?")


class TerminalUI(Prompter):
    """Small dependency-free full-screen setup UI with keyboard menus."""

    sections = ("Welcome", "General", "AI model", "Access", "Integrations", "Finish")

    def __init__(self, input_fn=input, secret_fn=getpass.getpass, out=print):
        super().__init__(input_fn, secret_fn, out)
        self.section = "Welcome"
        self.message = ""
        self._tty = sys.stdin.isatty() and sys.stdout.isatty() and os.environ.get("TERM") != "dumb" and "NO_COLOR" not in os.environ

    def _frame(self, title: str, body: list[str], footer: str = "↑↓ Select   Enter Continue   Ctrl+C Quit") -> None:
        if not self._tty:
            self.say(title)
            for line in body:
                self.say(line)
            return
        size = shutil.get_terminal_size((90, 28))
        columns = size.columns
        orange = branding.ORANGE
        white = branding.WHITE
        muted = branding.MUTED
        green = "\x1b[38;2;125;185;150m"
        reset = branding.RESET
        panel = branding.card(title, body, width=columns)
        masthead = branding.banner("SETUP", version=__version__, width=columns)
        if len(masthead) + len(panel) + 6 > size.lines:
            masthead = branding.banner("SETUP", version=__version__, width=columns, compact=True)
        lines = masthead
        active = self.sections.index(self.section) if self.section in self.sections else 0
        progress = f"{green}{'●' * active}{orange}◉{muted}{'○' * (len(self.sections) - active - 1)}{reset}"
        hot = "\x1b[48;2;255;112;32m\x1b[1;38;2;18;20;22m"
        lines.extend(["", f"  {progress}  {hot} {active + 1:02d} / {len(self.sections):02d} {reset}  "
                      f"{white}{self.section}{reset}", "",
                      *panel, "",
                      f"  {muted}{footer[:max(0, columns - 4)]}{reset}", ""])
        sys.stdout.write("\x1b[2J\x1b[H" + "\n".join(lines) + "\n")
        sys.stdout.flush()

    def say(self, text: str = "") -> None:
        self.message = text
        if not self._tty:
            super().say(text)

    def intro(self) -> bool:
        self.section = "Welcome"
        self._frame("Your private AI, ready when you are", [
            "A few choices, then your assistant is ready.",
            "Nothing is saved until you finish setup.",
            "Use ↑ / ↓ to choose, Enter to continue, Ctrl+C to quit.",
        ], "Enter → Start setup     q → Quit")
        if self._tty:
            return self._read_key().lower() != "q"
        return True

    @staticmethod
    def _read_key() -> str:
        if os.name == "nt":
            import msvcrt
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                return "\x1b[" + msvcrt.getwch()
            if key == "\x03":
                raise KeyboardInterrupt
            return key
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = sys.stdin.read(1)
            if key == "\x03":
                raise KeyboardInterrupt
            if key == "\x1b":
                key += sys.stdin.read(2)
            return key
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def ask(self, q: str, default: str = "") -> str:
        if not self._tty:
            return super().ask(q, default)
        self._frame(self.section, [q, "Type a value and press Enter."], "Enter → Save this field     Ctrl+C → Quit")
        value = self.input(f"  {q}" + (f" [{default}]" if default else "") + ": ").strip()
        return value or default

    def secret(self, q: str) -> str:
        if not self._tty:
            return super().secret(q)
        self._frame(self.section, [q, "Input is hidden while you type."], "Enter → Save securely     Ctrl+C → Quit")
        return self.secret_fn(f"  {q}: ").strip()

    def yes(self, q: str, default: bool = True) -> bool:
        if not self._tty:
            return super().yes(q, default)
        selected = 0 if default else 1
        options = [(True, "Yes"), (False, "No")]
        while True:
            hot, reset = "\x1b[48;2;255;112;32m\x1b[1;38;2;15;15;15m", "\x1b[0m"
            body = [q, "", *[((hot + "  › " + label + "  " + reset) if i == selected else "    " + label) for i, (_, label) in enumerate(options)]]
            self._frame(self.section, body, "↑/↓ Move     Enter → Select     Ctrl+C → Quit")
            key = self._read_key()
            if key in ("\x1b[A", "\x1b[B", "k", "j"):
                selected = 1 - selected
            elif key in ("\r", "\n", " "):
                return options[selected][0]

    def choose(self, q: str, options: list[tuple[str, str]], default: str) -> str:
        if not self._tty:
            return super().choose(q, options, default)
        selected = next((i for i, (key, _) in enumerate(options) if key == default), 0)
        while True:
            hot, reset = "\x1b[48;2;255;112;32m\x1b[1;38;2;15;15;15m", "\x1b[0m"
            page_size = max(1, shutil.get_terminal_size((90, 28)).lines - 18)
            start = selected // page_size * page_size
            end = min(start + page_size, len(options))
            body = [q, ""] + [((hot + "  › " + label + "  " + reset) if i == selected else "    " + label)
                               for i, (_, label) in enumerate(options) if start <= i < end]
            self._frame(self.section, body, f"{start + 1}-{end}/{len(options)}   ↑/↓ Move   Enter Select   Ctrl+C Quit")
            key = self._read_key()
            if key in ("\x1b[A", "k"):
                selected = (selected - 1) % len(options)
            elif key in ("\x1b[B", "j"):
                selected = (selected + 1) % len(options)
            elif key in ("\r", "\n", " "):
                return options[selected][0]


def detect_timezone() -> str:
    for cand in (os.environ.get("TZ", ""),):
        if cand in zoneinfo.available_timezones():
            return cand
    try:
        with open("/etc/timezone", encoding="utf-8") as f:
            name = f.read().strip()
            if name in zoneinfo.available_timezones():
                return name
    except OSError:
        pass
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            name = link.split("zoneinfo/", 1)[1]
            if name in zoneinfo.available_timezones():
                return name
    except OSError:
        pass
    return "UTC"


def exposure_hint(kind: str, port: int) -> list[str]:
    """Plain commands to run yourself. nano Agent never changes your network or runs sudo."""
    if kind == "tailscale":
        return [f"tailscale serve --bg {port}        # private to your tailnet (HTTPS at https://<machine>.<tailnet>.ts.net)",
                f"tailscale funnel --bg {port}       # only if LINE must reach the webhook over the internet"]
    if kind == "cloudflare":
        return [f"cloudflared tunnel --url http://127.0.0.1:{port}    # quick tunnel; prints a https://....trycloudflare.com URL",
                "# for a permanent URL create a named tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/"]
    if kind == "domain":
        return [f"# reverse-proxy your domain to http://127.0.0.1:{port} with HTTPS (Caddy example):",
                f"#   example.com {{ reverse_proxy 127.0.0.1:{port} }}"]
    return []


def collect(p: Prompter, *, quick: bool = False) -> dict:
    a: dict = {}
    p.say(t("setup.intro", "en") + "\n")
    if isinstance(p, TerminalUI):
        p.section = "General"
    a["language"] = p.choose(t("setup.lang_q", "en"), [("en", "English"), ("th", "ไทย (Thai)")], "en")
    L = a["language"]
    i18n.set_language(L)
    a["owner_name"] = "" if quick else p.ask(t("setup.name_q"), "")
    a["timezone"] = detect_timezone() if quick else p.ask(t("setup.tz_q"), detect_timezone())
    p.say("")
    if isinstance(p, TerminalUI):
        p.section = "AI model"
    a["provider"] = p.choose(t("setup.provider_q"), [(k, PRESETS[k]["label"]) for k in ORDER], "openai")
    pre = PRESETS[a["provider"]]
    a["base_url"] = p.ask(t("setup.base_url_q"), pre["base_url"]) if a["provider"] in ("custom", "vllm", "lmstudio", "ollama") else pre["base_url"]
    if pre["needs_key"] or a["provider"] in ("custom", "vllm", "lmstudio"):
        env_name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY",
                    "groq": "GROQ_API_KEY", "together": "TOGETHER_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(a["provider"], "")
        if env_name and os.environ.get(env_name) and p.yes(t("setup.key_env", env=env_name)):
            a["api_key"] = os.environ[env_name]
        else:
            if pre["key_url"]:
                p.say(t("setup.key_where", url=pre["key_url"]))
            a["api_key"] = p.secret(t("setup.key_q", name=pre["label"]) + (" " + t("setup.key_optional") if not pre["needs_key"] else ""))
    a["chat_model"] = p.ask(t("setup.model_q"), pre["chat"])
    a["fast_model"] = (pre["fast"] or a["chat_model"]) if quick else p.ask(t("setup.fast_q"), pre["fast"] or a["chat_model"])
    if quick:
        a["exposure"] = "local"
        a["home"] = str(paths.home())
        a["line_later"] = True
        a["voice"] = {"enabled": True}
        return a
    p.say("")
    if isinstance(p, TerminalUI):
        p.section = "Access"
    a["exposure"] = p.choose(t("setup.exposure_q"), [("local", t("setup.exp_local")), ("tailscale", t("setup.exp_tailscale")),
                                                      ("cloudflare", t("setup.exp_cloudflare")), ("domain", t("setup.exp_domain"))], "local")
    if a["exposure"] != "local":
        a["public_url"] = p.ask(t("setup.public_url_q"), "")
    cur = str(paths.home())
    a["home"] = p.ask(t("setup.home_q"), cur)
    p.say("")
    if isinstance(p, TerminalUI):
        p.section = "Integrations"
    line = p.choose(t("setup.line_q"), [("later", t("setup.line_later_opt")), ("now", t("setup.line_now_opt")), ("no", t("setup.line_no_opt"))], "later")
    if line == "now":
        p.say(t("line.guide"))
        a["line"] = {"enabled": True, "channel_secret": p.secret(t("setup.line_secret_q")), "channel_token": p.secret(t("setup.line_token_q")),
                     "liff_id": p.ask(t("setup.line_liff_q"), "")}
    elif line == "later":
        a["line_later"] = True
    if p.yes(t("setup.google_q"), False):
        a["google"] = True
    a["voice"] = {"enabled": p.yes(t("setup.voice_q"), True)}
    if shutil.which("docker"):
        a["sandbox"] = p.yes(t("setup.sandbox_q"), False)
    else:
        p.say(t("setup.sandbox_nodocker"))
    return a


def apply(a: dict) -> dict:
    """Write config.toml and secrets from an answers dict. Returns a summary (no secret values)."""
    if a.get("home"):
        new_home = os.path.abspath(os.path.expanduser(a["home"]))
        if new_home != str(paths.home()):
            os.environ["NANO_AGENT_HOME"] = new_home
            if not os.environ.get("NANO_AGENT_KEEP_POINTER_UNSET"):
                try:
                    paths.pointer_file().write_text(new_home, encoding="utf-8")
                except OSError:
                    pass
    paths.ensure_dirs()
    db.reset_cache()
    cfg = config.load()
    g = cfg["general"]
    g["language"] = a.get("language", g["language"])
    g["owner_name"] = a.get("owner_name", g["owner_name"])
    g["timezone"] = a.get("timezone") or g["timezone"]
    prov = a.get("provider")
    if prov:
        pre = PRESETS[prov]
        cfg["providers"][prov] = {"kind": pre["kind"], "base_url": a.get("base_url") or pre["base_url"], "key_ref": f"provider.{prov}"}
        cfg["models"]["chat"] = f"{prov}/{a['chat_model']}"
        cfg["models"]["fast"] = f"{prov}/{a.get('fast_model') or a['chat_model']}"
        if a.get("api_key"):
            keystore.set_(f"provider.{prov}", a["api_key"])
    if a.get("exposure"):
        cfg["gateway"]["exposure"] = a["exposure"]
        cfg["gateway"]["public_url"] = a.get("public_url", "") or ""
    if "line" in a:
        ln = a["line"]
        cfg["line"]["enabled"] = bool(ln.get("enabled", True))
        cfg["line"]["liff_id"] = ln.get("liff_id", "")
        if ln.get("owner_user_id"):
            cfg["line"]["owner_user_id"] = ln["owner_user_id"]
        if ln.get("channel_secret"):
            keystore.set_("line.channel_secret", ln["channel_secret"])
        if ln.get("channel_token"):
            keystore.set_("line.channel_token", ln["channel_token"])
    if a.get("google"):
        cfg["google"]["enabled"] = False   # becomes true after `nano-agent google auth`
    if "voice" in a:
        cfg["voice"]["enabled"] = bool(a["voice"].get("enabled"))
        for k in ("stt_url", "tts_url"):
            if a["voice"].get(k):
                cfg["voice"][k] = a["voice"][k]
    if "sandbox" in a:
        cfg["sandbox"]["enabled"] = bool(a["sandbox"])
    config.save(cfg)
    from .gateway import auth
    auth.owner_token()   # creates the owner's console token on first setup
    return {"home": str(paths.home()), "provider": prov, "model": cfg["models"]["chat"], "line": cfg["line"]["enabled"], "exposure": cfg["gateway"]["exposure"]}


def from_args(args, env=os.environ) -> dict:
    """Non-interactive answers. Required: --provider and --model. Key from --api-key-env / --api-key-file / --api-key-stdin."""
    prov = args.provider
    if prov not in PRESETS:
        raise SystemExit(f"unknown provider '{prov}'. Choose one of: {', '.join(ORDER)}")
    pre = PRESETS[prov]
    a: dict = {"language": args.language or "en", "owner_name": args.name or "", "timezone": args.timezone or detect_timezone(), "provider": prov,
               "base_url": args.base_url or pre["base_url"], "chat_model": args.model or pre["chat"], "fast_model": args.fast_model or args.model or pre["fast"],
               "exposure": args.exposure or "local"}
    if args.public_url:
        a["public_url"] = args.public_url
    if args.home:
        a["home"] = args.home
    key = ""
    if args.api_key_env:
        key = env.get(args.api_key_env, "")
        if not key:
            raise SystemExit(f"environment variable {args.api_key_env} is empty or not set")
    elif args.api_key_file:
        key = open(args.api_key_file, encoding="utf-8").read().strip()
    elif args.api_key_stdin:
        key = sys.stdin.readline().strip()
    if pre["needs_key"] and not key and not env.get(f"NANO_SECRET_PROVIDER_{prov.upper()}"):
        raise SystemExit("this provider needs an API key: use --api-key-env VAR, --api-key-file FILE or --api-key-stdin")
    if key:
        a["api_key"] = key
    if args.line_secret_env or args.line_token_env:
        a["line"] = {"enabled": True, "channel_secret": env.get(args.line_secret_env or "", ""), "channel_token": env.get(args.line_token_env or "", ""), "liff_id": args.liff_id or ""}
    a["voice"] = {"enabled": not args.no_voice}
    if args.sandbox:
        a["sandbox"] = True
    return a


def test_model(role: str = "chat") -> tuple[bool, str]:
    cfg = config.load()
    pname, model = config.model_for(cfg, role)
    if not pname:
        return False, "no model configured"
    prov = make_provider(cfg, pname)
    return asyncio.run(prov.ping(model))


def run_interactive(p: Prompter | None = None) -> int:
    p = p or TerminalUI()
    try:
        quick = False
        if isinstance(p, TerminalUI):
            if not p.intro():
                p.say(t("setup.aborted"))
                return 130
            quick = p.choose(t("setup.mode_q"), [("quick", t("setup.mode_quick")),
                                                 ("custom", t("setup.mode_custom"))], "quick") == "quick"
        a = collect(p, quick=quick)
        if isinstance(p, TerminalUI):
            p.section = "Finish"
            p._frame("Review your setup", [
                f"Name: {a.get('owner_name') or 'Not set'}",
                f"Language: {a.get('language', 'en')} · Time zone: {a.get('timezone', 'UTC')}",
                f"Model: {a.get('provider', 'Not set')} / {a.get('chat_model', '')}",
                f"Console access: {a.get('exposure', 'local')}",
                f"LINE: {'Enabled' if a.get('line', {}).get('enabled') else 'Not connected'} · Voice: {'On' if a.get('voice', {}).get('enabled') else 'Off'}",
                "Your API key is hidden and is not shown in this review.",
            ], "Enter → Save settings     Ctrl+C → Cancel")
            if not p.yes("Save these settings?", True):
                p.say(t("setup.aborted"))
                return 130
    except (KeyboardInterrupt, EOFError):
        p.say("\n" + t("setup.aborted"))
        return 130
    s = apply(a)
    i18n.set_language(a["language"])
    p.say("\n" + t("setup.saved", home=s["home"]))
    ok, msg = test_model()
    p.say(t("setup.test_ok", msg=msg) if ok else t("setup.test_fail", msg=msg))
    if not ok:
        p.say(t("setup.test_later"))
    if a.get("line_later"):
        p.say(t("setup.line_later_hint"))
    if a.get("exposure", "local") != "local":
        p.say(t("setup.exposure_cmds"))
        for ln in exposure_hint(a["exposure"], config.load()["gateway"]["port"]):
            p.say("  " + ln)
    if isinstance(p, TerminalUI):
        lines = [f"Workspace: {s['home']}", f"Model: {s['model']}",
                 ("Model connection: ready" if ok else "Model connection: needs attention — run nano-agent models test"),
                 "Settings   nano-agent config set <key> <value>",
                 "Models     nano-agent models --help",
                 "LINE       nano-agent line --help",
                 "Google     nano-agent google --help"]
        p.section = "Finish"
        p._frame("Setup complete", lines, "Next → Start the assistant and open your console")
    return 0
