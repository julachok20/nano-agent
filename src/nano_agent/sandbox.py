"""Optional code sandbox: run a short Python snippet in a throw-away Docker container with NO network, no secrets, a
read-only root, small memory and a hard timeout. Disabled unless Docker is installed and `[sandbox] enabled = true`.

The host never runs model-written code. If Docker is missing the tool says so; it does not fall back to the host.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from . import config

MAX_OUT = 6000


def available() -> tuple[bool, str]:
    cfg = config.load()["sandbox"]
    if not cfg.get("enabled"):
        return False, "The sandbox is switched off. Enable it with `nano-agent setup` (needs Docker)."
    if not shutil.which("docker"):
        return False, "Docker was not found on this machine."
    return True, ""


def docker_args(workdir: str, image: str) -> list[str]:
    return ["docker", "run", "--rm", "--network", "none", "--memory", "256m", "--cpus", "1", "--pids-limit", "64", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:size=16m", "-v", f"{workdir}:/work:ro",
            "-w", "/work", image, "python", "-I", "main.py"]


async def run_python(code: str, timeout: int | None = None) -> dict:
    ok, why = available()
    if not ok:
        return {"ok": False, "error": why}
    cfg = config.load()["sandbox"]
    timeout = min(int(timeout or cfg.get("timeout_s", 20)), 60)
    with tempfile.TemporaryDirectory(prefix="nano-sbx-") as d:
        Path(d, "main.py").write_text(code, encoding="utf-8")
        proc = await asyncio.create_subprocess_exec(*docker_args(d, cfg["image"]), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False, "error": f"timed out after {timeout} s"}
    return {"ok": proc.returncode == 0, "exit": proc.returncode, "stdout": out.decode("utf-8", "replace")[:MAX_OUT], "stderr": err.decode("utf-8", "replace")[:2000]}
