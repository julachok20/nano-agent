"""Installer and packaging: install.sh checks, and a real install of the built wheel into a clean venv on a fresh home."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
BASH = shutil.which("bash")


@pytest.mark.skipif(os.name == "nt" or not BASH, reason="POSIX installer runs on Unix or WSL")
def test_install_script_syntax_and_dry_run():
    assert subprocess.run([BASH, "-n", str(ROOT / "install.sh")]).returncode == 0
    p = subprocess.run([BASH, str(ROOT / "install.sh"), "--dry-run", "--method", "venv", "--from", "nanoagent==0.1.0"], capture_output=True, text=True,
                       env={**os.environ, "NANO_AGENT_ALLOW_ANY": "1"})
    if "native Windows" in p.stderr:
        pytest.skip("install.sh refuses native Windows by design (use WSL)")
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "Method:    venv" in out and "Will run:" in out and "No sudo" in out and "dry run: nothing was changed" in out and "nanoagent==0.1.0" in out


@pytest.mark.skipif(os.name == "nt" or not BASH, reason="POSIX installer runs on Unix or WSL")
def test_installer_uses_local_checkout_by_default_and_keeps_remote_fallback(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("NANO_AGENT_SPEC", "NANO_AGENT_FROM_PYPI", "NANO_AGENT_REPO")}
    local = subprocess.run([BASH, str(ROOT / "install.sh"), "--dry-run", "--method", "venv"],
                           cwd=tmp_path, capture_output=True, text=True, env=env)
    assert local.returncode == 0, local.stderr
    assert f"Source:    {ROOT.resolve()}" in local.stdout

    standalone = tmp_path / "install.sh"
    shutil.copyfile(ROOT / "install.sh", standalone)
    remote = subprocess.run([BASH, str(standalone), "--dry-run", "--method", "venv"],
                            cwd=tmp_path, capture_output=True, text=True, env=env)
    assert remote.returncode == 0, remote.stderr
    assert "Source:    https://codeload.github.com/julachok20/nano-agent/tar.gz/main" in remote.stdout

    streamed = subprocess.run([BASH, "-s", "--", "--dry-run", "--method", "venv"],
                              input=(ROOT / "install.sh").read_text(encoding="utf-8"),
                              cwd=tmp_path, capture_output=True, text=True, env=env)
    assert streamed.returncode == 0, streamed.stderr
    assert "Source:    https://codeload.github.com/julachok20/nano-agent/tar.gz/main" in streamed.stdout

    help_result = subprocess.run([BASH, "-s", "--", "--help"],
                                 input=(ROOT / "install.sh").read_text(encoding="utf-8"),
                                 cwd=tmp_path, capture_output=True, text=True, env=env)
    assert help_result.returncode == 0, help_result.stderr
    assert "Usage: bash install.sh [options]" in help_result.stdout


@pytest.mark.skipif(os.name == "nt" or not BASH, reason="POSIX installer runs on Unix or WSL")
def test_install_script_rejects_unknown_options_and_never_uses_sudo():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    import re
    assert not re.search(r"^\s*sudo\s", code, re.M)   # sudo only appears inside advice text printed to the user, never as a command
    assert ".bashrc" not in code and ".profile" not in code and ".zshrc" not in code
    p = subprocess.run([BASH, str(ROOT / "install.sh"), "--bogus"], capture_output=True, text=True)
    assert p.returncode != 0 and "unknown option" in p.stderr or "native Windows" in p.stderr


@pytest.mark.skipif(os.environ.get("NANO_SKIP_INSTALL_TEST") == "1", reason="NANO_SKIP_INSTALL_TEST=1")
def test_wheel_installs_into_a_clean_venv_and_runs_on_a_fresh_home(tmp_path):
    wheels = tmp_path / "wheels"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(wheels), "-q"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    whl = next(wheels.glob("nanoagent-*.whl"))
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    exe = ".exe" if os.name == "nt" else ""
    r = subprocess.run([str(bindir / f"python{exe}"), "-m", "pip", "install", "-q", "--disable-pip-version-check", str(whl)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    env = {k: v for k, v in os.environ.items() if not k.startswith("NANO_")}
    env["NANO_AGENT_HOME"] = str(tmp_path / "fresh-home")
    env["PYTHONIOENCODING"] = "utf-8"
    env["HOME"] = env["USERPROFILE"] = str(tmp_path)   # the pointer file must not land in a real home
    cli = str(bindir / f"nano-agent{exe}")

    def run(*a):
        return subprocess.run([cli, *a], capture_output=True, text=True, env=env, encoding="utf-8")
    v = run("--version")
    assert v.returncode == 0 and v.stdout.startswith("nano-agent 0.1")
    assert run("doctor", "--offline").returncode == 1   # fresh home, nothing configured: fails clearly
    s = run("setup", "--non-interactive", "--provider", "fake", "--model", "fake-1", "--skip-test", "--name", "CI")
    assert s.returncode == 0, s.stderr
    d = run("doctor", "--offline")
    assert d.returncode == 0 and "Everything needed is in place" in d.stdout, d.stdout
    # package data shipped in the wheel: translations and the console script
    code = "from nanoagent import i18n; from importlib import resources as r; print(i18n.t('ui.tab_home','th'), r.files('nanoagent').joinpath('gateway','static','console.js').is_file())"
    py = subprocess.run([str(bindir / f"python{exe}"), "-c", code], capture_output=True, text=True, env=env, encoding="utf-8")
    assert py.stdout.split() == ["หน้าหลัก", "True"], py.stdout + py.stderr
    assert not (Path(tmp_path) / ".nano-agent-home").exists()
