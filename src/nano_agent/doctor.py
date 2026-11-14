"""`nano-agent doctor`: checks that everything is in place and says how to fix what is not.

Levels: ok, warn (works but worth fixing), fail (will not work), skip. Exit code 1 only when something fails.
`--offline` skips the model call, so it also works in CI without any key.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import socket
import sys

import httpx

from . import __version__, config, db, i18n, keystore, paths
from .i18n import t

ICON = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "-"}


def _port_state(host: str, port: int) -> str:
    """'ours' when our /healthz answers, 'free' when nothing listens, 'busy' when something else does."""
    try:
        r = httpx.get(f"http://{host}:{port}/healthz", timeout=1.5)
        if r.status_code == 200 and "version" in r.json():
            return "ours"
        return "busy"
    except Exception:
        pass
    with socket.socket() as s:
        s.settimeout(0.5)
        return "busy" if s.connect_ex((host, port)) == 0 else "free"


def checks(offline: bool = False) -> list[dict]:
    out: list[dict] = []

    def add(cid: str, level: str, detail: str = "", hint: str = ""):
        out.append({"id": cid, "name": t(f"doctor.{cid}"), "level": level, "detail": detail, "hint": hint})

    add("python", "ok" if sys.version_info >= (3, 11) else "fail", sys.version.split()[0], t("doctor.python.hint"))
    home = paths.home()
    add("home", "ok" if home.exists() else "fail", str(home), t("doctor.home.hint"))
    if not home.exists():
        return out
    cfg = config.load()
    has_model = bool(config.get(cfg, "models.chat"))
    add("config", "ok" if paths.config_path().exists() and has_model else "fail", str(paths.config_path()), t("doctor.config.hint"))
    add("secrets_file", "ok" if keystore.file_mode_ok() else "warn", t("doctor.secrets_file.detail"), t("doctor.secrets_file.hint"))
    pname, model = config.model_for(cfg, "chat")
    spec = cfg["providers"].get(pname or "", {})
    if spec and spec.get("kind") not in ("ollama", "fake") and not keystore.get(spec.get("key_ref", f"provider.{pname}")):
        from .providers.presets import PRESETS
        needs = PRESETS.get(pname, {}).get("needs_key", True)
        add("provider_key", "fail" if needs else "skip", pname, t("doctor.provider_key.hint"))
    else:
        add("provider_key", "ok" if spec else "fail", pname or "-", t("doctor.provider_key.hint"))
    if offline or not has_model:
        add("provider_ping", "skip", t("doctor.offline"))
    else:
        from .providers import make_provider
        try:
            ok, msg = asyncio.run(make_provider(cfg, pname).ping(model))
        except Exception as e:
            ok, msg = False, keystore.redact(e)
        add("provider_ping", "ok" if ok else "fail", f"{pname}/{model}: {msg}", t("doctor.provider_ping.hint"))
    try:
        r = db.one("PRAGMA quick_check")
        add("database", "ok" if r and r[0] == "ok" else "fail", str(paths.db_path()), t("doctor.database.hint"))
    except Exception as e:
        add("database", "fail", type(e).__name__, t("doctor.database.hint"))
    from . import tools
    failed = [p for p in tools.load_plugins() if "FAILED" in p]
    add("tools", "ok" if not failed else "warn", f"{len(tools.REGISTRY)} tools" + (f"; {', '.join(failed)}" if failed else ""), t("doctor.tools.hint"))
    miss = {k: v for k, v in i18n.missing_keys().items() if v}
    add("i18n", "ok" if not miss else "warn", json.dumps(miss)[:120] if miss else "en, th", "")
    g = cfg["gateway"]
    st = _port_state(g["host"], g["port"])
    add("port", {"ours": "ok", "free": "ok", "busy": "fail"}[st], f"{g['host']}:{g['port']} ({st})", t("doctor.port.hint"))
    if cfg["line"]["enabled"]:
        okk = bool(keystore.get("line.channel_secret") and keystore.get("line.channel_token"))
        add("line", "ok" if okk else "fail", t("doctor.line.detail"), t("doctor.line.hint"))
        add("line_paired", "ok" if cfg["line"]["owner_user_id"] else "warn", t("doctor.line_paired.detail"), t("doctor.line_paired.hint"))
    else:
        add("line", "skip", t("doctor.line.off"))
    if g["exposure"] != "local":
        add("exposure", "ok" if g["public_url"] else "warn", g["exposure"] + " " + (g["public_url"] or "-"), t("doctor.exposure.hint"))
    if cfg["sandbox"]["enabled"]:
        add("sandbox", "ok" if shutil.which("docker") else "fail", "docker", t("doctor.sandbox.hint"))
    if cfg["google"]["enabled"]:
        add("google", "ok" if (paths.home() / "google_token.json").exists() else "fail", "token", t("doctor.google.hint"))
    for mod, label in (("psutil", "system page (CPU/RAM)"), ("keyring", "OS keyring")):
        try:
            __import__(mod)
            add(f"opt_{mod}", "ok", label)
        except ImportError:
            add(f"opt_{mod}", "skip", label + " (optional, not installed)")
    return out


def run(offline: bool = False, as_json: bool = False) -> int:
    res = checks(offline)
    if as_json:
        print(json.dumps({"version": __version__, "checks": res}, indent=2))
    else:
        print(f"nano-agent {__version__} - {t('doctor.title')}\n")
        for c in res:
            line = f" {ICON[c['level']]} {c['name']}" + (f": {c['detail']}" if c["detail"] else "")
            print(line)
            if c["level"] in ("warn", "fail") and c["hint"]:
                print(f"     -> {c['hint']}")
    fails = [c for c in res if c["level"] == "fail"]
    if not as_json:
        print("\n" + (t("doctor.all_ok") if not fails else t("doctor.failed", n=len(fails))))
    return 1 if fails else 0
