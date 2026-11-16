"""The container seam for the sandbox workspace (N8). Everything Docker-specific lives here, behind a tiny interface.

    DockerRuntime  the real runtime. Argument lists are unit-tested; the calls need a running Docker daemon.
    LocalRuntime   TEST DOUBLE ONLY. Runs commands as ordinary host processes in the workspace folder. It is NOT
                   isolation and is never chosen from config: tests and the red-team test mode pass it in explicitly.

Hard rules encoded in `docker_run_args`: no network (`--network none`), no privileged mode, no host network, no Docker
socket, all capabilities dropped, no-new-privileges, non-root user, memory, CPU and process limits, and the workspace as
the only host mount.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class RuntimeUnavailable(Exception):
    """The runtime cannot run right now (Docker missing, daemon down, container frozen)."""


@dataclass
class ExecResult:
    exit: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    frozen: bool = False


def docker_run_args(name: str, image: str, workspace: Path, cpu: float, memory_mb: int, pids: int = 128) -> list[str]:
    return ["docker", "run", "-d", "--name", name,
            "--network", "none",
            "--cpus", str(cpu), "--memory", f"{int(memory_mb)}m", "--memory-swap", f"{int(memory_mb)}m", "--pids-limit", str(pids),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "1000:1000",
            "--tmpfs", "/tmp:size=64m",
            "-v", f"{Path(workspace).resolve()}:/work", "-w", "/work",
            image, "sleep", "infinity"]


def _clean_env() -> dict[str, str]:
    """Host-side commands get a minimal environment: no provider keys, no tokens."""
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT")}
    keep["PYTHONIOENCODING"] = "utf-8"
    return keep


class DockerRuntime:
    name = "docker"

    def __init__(self, docker: str = "docker"):
        self.docker = docker

    def _run(self, args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
        return subprocess.run([self.docker, *args], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")

    def available(self) -> tuple[bool, str]:
        if not shutil.which(self.docker):
            return False, "Docker was not found on this machine. Install Docker Desktop or use WSL, then run `nano-agent sandbox enable` again. The sandbox stays OFF."
        try:
            r = self._run(["info", "--format", "{{.ServerVersion}}"], timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return False, "Docker is installed but did not answer. Start Docker and try again. The sandbox stays OFF."
        if r.returncode != 0:
            return False, "Docker is installed but not running. Start Docker and try again. The sandbox stays OFF."
        return True, ""

    def is_running(self, name: str) -> bool:
        try:
            r = self._run(["inspect", "-f", "{{.State.Running}}", name], timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0 and r.stdout.strip() == "true"

    def ensure(self, name: str, image: str, workspace: Path, cpu: float, memory_mb: int) -> None:
        if self.is_running(name):
            return
        self._run(["rm", "-f", name], timeout=30)   # a stopped leftover with the same name
        r = self._run(docker_run_args(name, image, workspace, cpu, memory_mb)[1:], timeout=300)
        if r.returncode != 0:
            raise RuntimeUnavailable("could not start the sandbox container: " + (r.stderr or "unknown error").strip()[:200])

    def exec(self, name: str, command: str, timeout_s: int, watch: Callable[[], bool] | None = None) -> ExecResult:
        # `timeout -s KILL` inside the container so a runaway process dies there, not only on the host side.
        args = ["exec", "-w", "/work", name, "timeout", "-s", "KILL", str(int(timeout_s)), "sh", "-c", command]
        try:
            r = self._run(args, timeout=timeout_s + 10)
        except subprocess.TimeoutExpired:
            return ExecResult(exit=-9, timed_out=True, stderr="timed out")
        # `watch` is not polled here: a lease lapse pauses the container, which freezes the exec until the host timeout.
        return ExecResult(exit=r.returncode, stdout=r.stdout, stderr=r.stderr, timed_out=r.returncode in (137, 124))

    def pause(self, name: str) -> None:
        self._run(["pause", name], timeout=30)

    def unpause(self, name: str) -> None:
        self._run(["unpause", name], timeout=30)

    def kill(self, name: str) -> None:
        self._run(["rm", "-f", name], timeout=30)

    def ping(self, name: str) -> bool:
        return self.is_running(name)

    def stats_mb(self, name: str) -> float:
        try:
            r = self._run(["stats", "--no-stream", "--format", "{{.MemUsage}}", name], timeout=20)
            return float(r.stdout.split("/")[0].strip().rstrip("MiB").strip() or 0)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return 0.0


class LocalRuntime:
    """TEST DOUBLE. Host processes, no isolation. See the module docstring."""
    name = "local-test"

    def __init__(self) -> None:
        self.workspace: Path | None = None
        self.paused = False
        self.killed = False
        self.fail_ping = False
        self.mem_mb = 10.0
        self.exec_count = 0

    def available(self) -> tuple[bool, str]:
        return True, ""

    def is_running(self, name: str) -> bool:
        return self.workspace is not None and not self.killed

    def ensure(self, name: str, image: str, workspace: Path, cpu: float, memory_mb: int) -> None:
        """A killed container is replaced by a fresh one. A frozen (paused) one is NOT thawed here: only resume does that."""
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        if self.killed:
            self.killed, self.paused = False, False

    def exec(self, name: str, command: str, timeout_s: int, watch: Callable[[], bool] | None = None) -> ExecResult:
        """`watch()` is polled while the command runs; returning False freezes the process (lease lapse)."""
        if self.paused or self.killed or self.workspace is None:
            raise RuntimeUnavailable("container is not running")
        self.exec_count += 1
        proc = subprocess.Popen(command, shell=True, cwd=str(self.workspace), env=_clean_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        deadline = time.monotonic() + timeout_s
        while proc.poll() is None:
            if watch is not None and not watch():
                proc.kill()
                out, err = proc.communicate()
                self.paused = True
                return ExecResult(exit=-1, stdout=out or "", stderr=err or "", frozen=True)
            if time.monotonic() > deadline:
                proc.kill()
                out, err = proc.communicate()
                return ExecResult(exit=-9, stdout=out or "", stderr=(err or "") + "\ntimed out", timed_out=True)
            time.sleep(0.05)
        out, err = proc.communicate()
        return ExecResult(exit=proc.returncode, stdout=out or "", stderr=err or "")

    def pause(self, name: str) -> None:
        self.paused = True

    def unpause(self, name: str) -> None:
        self.paused = False

    def kill(self, name: str) -> None:
        self.killed = True
        self.paused = False

    def ping(self, name: str) -> bool:
        return not self.fail_ping and not self.killed

    def stats_mb(self, name: str) -> float:
        return self.mem_mb


__all__ = ["DockerRuntime", "LocalRuntime", "ExecResult", "RuntimeUnavailable", "docker_run_args"]
