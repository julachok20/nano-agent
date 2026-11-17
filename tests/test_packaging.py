"""Every non-Python file inside the package must be listed in pyproject's package-data.

A file that exists in the source tree but is not packaged works in tests (they import from src/) and then breaks every
real install. The constitution file once went missing this way, and the agent refused to run: "the constitution file
no longer matches its pinned digest".
"""
from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "nanoagent"
IGNORED_SUFFIXES = (".py", ".pyc")


def _patterns() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["setuptools"]["package-data"]["nanoagent"]


def test_every_data_file_is_packaged():
    patterns = _patterns()
    missing = []
    for path in sorted(PKG.rglob("*")):
        if not path.is_file() or path.suffix in IGNORED_SUFFIXES or "__pycache__" in path.parts or ".bak" in path.name:
            continue
        rel = path.relative_to(PKG).as_posix()
        if not any(fnmatch.fnmatchcase(rel, p) for p in patterns):
            missing.append(rel)
    assert not missing, f"not in package-data, so missing from real installs: {missing}"


def test_constitution_is_packaged():
    assert "constitution.md" in _patterns()
