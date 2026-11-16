"""Settings: ~/.nano-agent/config.toml (no secrets in it; secrets live in secrets.py).

`load()` always returns a complete dict (defaults merged under the file), so callers never check for missing keys.
`dumps()` is a tiny TOML writer for the value types we use, so the project needs no extra dependency.
"""
from __future__ import annotations

import copy
import os
import re
import tomllib
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "general": {
        "language": "en",          # en | th
        "owner_name": "",
        "timezone": "UTC",         # IANA name, e.g. Asia/Bangkok
        "secrets_backend": "file",  # file | keyring
    },
    "models": {"chat": "", "fast": "", "vision": ""},   # "<provider>/<model>"
    "providers": {},   # name -> {kind, base_url, key_ref}
    "agent": {"max_steps": 8, "temperature": 0.4, "max_tool_chars": 6000},
    "gateway": {
        "host": "127.0.0.1",
        "port": 8099,
        "exposure": "local",   # local | tailscale | cloudflare | domain
        "public_url": "",
    },
    "line": {"enabled": False, "liff_id": "", "owner_user_id": ""},
    "google": {"enabled": False},
    "voice": {"enabled": False, "stt_url": "", "tts_url": "", "tts_voice": "alloy"},
    # `enabled` / `timeout_s` belong to the short run_code tool. The workspace (N8) is separate and OFF by default.
    "sandbox": {
        "enabled": False, "image": "python:3.12-slim", "timeout_s": 20,
        "workspace": False,          # N8: one persistent Docker workspace the agent can build tools and skills in
        "tier": "T0",                # T0 closed | T1 allowlist | T2 web | T3 brokered; the agent cannot change it
        "allowed_domains": [],       # T1 only: domains the sandbox may fetch (host edge checks every request)
        "capabilities": [],          # T3 only: "name=domain" brokered capabilities; "messaging" and "payments" are off unless listed
        "cpu": 1.0, "memory_mb": 512, "disk_mb": 512, "run_timeout_s": 120,
        "lease_s": 120, "session_h": 2,
        "tripwire_blocked": 5, "tripwire_window_min": 10,
    },
    "web": {"search": "duckduckgo", "search_url": ""},   # duckduckgo | searxng
    "companion": {"level": "buddy", "enabled": True},
    "learning": {"enabled": True},
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "providers":
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load() -> dict:
    p = paths.config_path()
    if not p.exists():
        return copy.deepcopy(DEFAULTS)
    with open(p, "rb") as f:
        data = tomllib.load(f)
    return _merge(DEFAULTS, data)


def get(cfg: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_(cfg: dict, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = cfg
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def _key(k: str) -> str:
    """Bare TOML keys only allow A-Za-z0-9_-; anything else (a dot in a provider name) must be quoted."""
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dumps(cfg: dict) -> str:
    lines: list[str] = []

    def emit(prefix: str, d: dict) -> None:
        scalars = {k: v for k, v in d.items() if not isinstance(v, dict)}
        tables = {k: v for k, v in d.items() if isinstance(v, dict)}
        if prefix and (scalars or not tables):
            lines.append(f"[{prefix}]")
        for k, v in scalars.items():
            lines.append(f"{_key(k)} = {_scalar(v)}")
        if scalars or (prefix and not tables):
            lines.append("")
        for k, v in tables.items():
            emit(f"{prefix}.{_key(k)}" if prefix else _key(k), v)

    emit("", cfg)
    return "\n".join(lines).rstrip() + "\n"


def save(cfg: dict) -> None:
    paths.ensure_dirs()
    p = paths.config_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(dumps(cfg), encoding="utf-8")
    os.replace(tmp, p)


def split_model(ref: str) -> tuple[str, str]:
    """'main/gpt-4o-mini' -> ('main', 'gpt-4o-mini'). Model ids may contain slashes (OpenRouter), only the first splits."""
    if "/" not in ref:
        return "", ref
    prov, model = ref.split("/", 1)
    return prov, model


def model_for(cfg: dict, role: str = "chat") -> tuple[str, str]:
    """(provider name, model id) for a role; 'fast' and 'vision' fall back to 'chat'."""
    ref = get(cfg, f"models.{role}", "") or get(cfg, "models.chat", "")
    return split_model(ref)


def tz(cfg: dict | None = None):
    from zoneinfo import ZoneInfo

    name = get(cfg or load(), "general.timezone", "UTC") or "UTC"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")
