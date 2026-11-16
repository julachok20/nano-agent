"""Where nano Agent keeps its files. One home directory, overridable with NANO_AGENT_HOME."""
from __future__ import annotations

import os
from pathlib import Path


def pointer_file() -> Path:
    """`nano-agent setup` writes the chosen data directory here when it is not the default (the env var still wins)."""
    return Path.home() / ".nano-agent-home"


def home() -> Path:
    env = os.environ.get("NANO_AGENT_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    try:
        ptr = pointer_file().read_text(encoding="utf-8").strip()
        if ptr:
            return Path(ptr).expanduser()
    except OSError:
        pass
    return Path.home() / ".nano-agent"


def config_path() -> Path:
    return home() / "config.toml"


def secrets_path() -> Path:
    return home() / "secrets.toml"


def data_dir() -> Path:
    return home() / "data"


def db_path() -> Path:
    return data_dir() / "nano.db"


def skills_dir() -> Path:
    return data_dir() / "skills"


def skills_pending_dir() -> Path:
    return data_dir() / "skills-pending"


def skills_trash_dir() -> Path:
    return data_dir() / "skills-trash"


def skills_history_dir() -> Path:
    return data_dir() / "skills-history"


def patches_dir() -> Path:
    return data_dir() / "patches"


def plugins_dir() -> Path:
    """The only code area the agent may propose patches for (see patching.py)."""
    return data_dir() / "plugins"


def backups_dir() -> Path:
    return data_dir() / "backups"


def logs_dir() -> Path:
    return home() / "logs"


def pid_path() -> Path:
    return home() / "nano-agent.pid"


def sandbox_dir() -> Path:
    """Sandbox workspace, snapshots and forensic bundles (N8). Created on first use, not by ensure_dirs."""
    return home() / "sandbox"


def workspace_dir() -> Path:
    """The only host folder the sandbox sees: bind-mounted as /work."""
    return sandbox_dir() / "workspace"


def snapshots_dir() -> Path:
    return sandbox_dir() / "snapshots"


def supervisor_dir() -> Path:
    """Supervisor state (lease, control queue, forensics). Kept apart from the workspace; in production run the
    supervisor under its own OS user (NANO_SUPERVISOR_HOME points at a folder that user owns)."""
    env = os.environ.get("NANO_SUPERVISOR_HOME", "").strip()
    return Path(env).expanduser() if env else home() / "supervisor"


def ensure_dirs() -> None:
    for d in (home(), data_dir(), skills_dir(), skills_pending_dir(), backups_dir(), logs_dir(), plugins_dir()):
        d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(home(), 0o700)
    except OSError:
        pass
