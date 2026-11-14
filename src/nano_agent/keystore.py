"""API keys and other secrets: a 0600 file (default) or the OS keyring. Never printed, never logged.

Names are dotted strings: `provider.main`, `line.channel_secret`, `line.channel_token`, `owner.token`.
For CI and containers, an environment variable `NANO_SECRET_<NAME>` (dots become underscores, upper case) wins over
the store, so a pipeline can inject a key without writing a file.

Every log line and every error shown to a user goes through `redact()`, which replaces stored secret values and
anything that looks like a key.
"""
from __future__ import annotations

import os
import re
import tomllib
from typing import Optional

from . import config, paths

_KEY_LIKE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,}|sk-ant-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{20,}|gsk_[A-Za-z0-9]{16,}|"
    r"xox[abp]-[A-Za-z0-9\-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._\-]{16,}|"
    r"(?:api[_-]?key|token|secret|password)\s*[=:]\s*[\"']?[A-Za-z0-9._\-]{8,})",
    re.I,
)


def _env_name(name: str) -> str:
    return "NANO_SECRET_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def _backend() -> str:
    try:
        return config.get(config.load(), "general.secrets_backend", "file")
    except Exception:
        return "file"


def _keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:
        return None


def _read_file() -> dict[str, str]:
    p = paths.secrets_path()
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        return {str(k): str(v) for k, v in tomllib.load(f).get("secrets", {}).items()}


def _write_file(d: dict[str, str]) -> None:
    paths.ensure_dirs()
    p = paths.secrets_path()
    body = "[secrets]\n" + "".join(
        f'"{k}" = "{v.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"\n' for k, v in sorted(d.items())
    )
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, p)


def get(name: str, default: Optional[str] = None) -> Optional[str]:
    env = os.environ.get(_env_name(name))
    if env:
        return env
    if _backend() == "keyring" and (kr := _keyring()):
        v = kr.get_password("nano-agent", name)
        if v:
            return v
    return _read_file().get(name, default)


def set_(name: str, value: str) -> None:
    if _backend() == "keyring" and (kr := _keyring()):
        kr.set_password("nano-agent", name, value)
        d = _read_file()
        if name in d:  # do not leave a stale plaintext copy behind
            del d[name]
            _write_file(d)
        _index_add(name)
        return
    d = _read_file()
    d[name] = value
    _write_file(d)


def delete(name: str) -> None:
    if _backend() == "keyring" and (kr := _keyring()):
        try:
            kr.delete_password("nano-agent", name)
        except Exception:
            pass
    d = _read_file()
    if name in d:
        del d[name]
        _write_file(d)


def _index_add(name: str) -> None:
    """The keyring cannot list its entries; keep the NAMES (never values) in the file so `names()` works."""
    d = _read_file()
    d.setdefault(f"_index.{name}", "1")
    _write_file(d)


def names() -> list[str]:
    out = set()
    for k in _read_file():
        out.add(k[len("_index."):] if k.startswith("_index.") else k)
    return sorted(out)


def mask(value: Optional[str]) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "****"
    return value[:3] + "…" + value[-3:]


def file_mode_ok() -> bool:
    """True when the secrets file is private (POSIX). Windows has no mode bits: reported as OK."""
    p = paths.secrets_path()
    if not p.exists() or os.name == "nt":
        return True
    return (p.stat().st_mode & 0o077) == 0


def redact(text: object) -> str:
    s = str(text)
    try:
        values = [v for k, v in _read_file().items() if not k.startswith("_index.") and len(v) >= 8]
    except Exception:
        values = []
    for v in values:
        s = s.replace(v, "***")
    return _KEY_LIKE.sub("***", s)


class RedactingFilter:
    """logging.Filter that masks secrets in every record before it is formatted."""

    def filter(self, record) -> bool:  # noqa: A003
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True
