"""The constitution: CONSTITUTION.md, injected into every agent prompt (N9).

It is guidance the model reads, not enforcement (enforcement is the supervisor and the kill switch, see SECURITY.md).
The copy inside the package must match the repository's CONSTITUTION.md (a test checks it). The agent cannot change it:
no tool writes package files (patching.py denylists the whole package), and `verify()` refuses to run the model
when the text no longer matches the digest pinned here, so a changed file fails closed.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# Pinned digest of constitution.md. Changing the constitution means changing this constant on purpose, in a reviewed commit.
PINNED_SHA256 = "a84e7e26cdc52b5e9cf135b2a5b90e87b9aefb1879e015bc0911e5af443fd3bb"

PRECEDENCE = "Order of precedence: (1) the owner's stop, pause or rollback, (2) this constitution, (3) the current goal. A goal never outranks a stop or this text."


def path() -> Path:
    return Path(__file__).with_name("constitution.md")


def text() -> str:
    return path().read_text(encoding="utf-8")


def digest(raw: str | None = None) -> str:
    # Line endings never change the pin: an autocrlf checkout must not make the agent refuse to run.
    text_ = (raw if raw is not None else text()).replace(chr(13) + chr(10), chr(10))
    return hashlib.sha256(text_.encode("utf-8")).hexdigest()


def verify() -> bool:
    try:
        return digest() == PINNED_SHA256
    except OSError:
        return False


def prompt_block() -> str:
    return f"CONSTITUTION (binding on every action; {PRECEDENCE})\n{text().strip()}"
