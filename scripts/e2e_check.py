#!/usr/bin/env python3
"""Run a disposable fake-provider console smoke check without real accounts."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nano-agent-e2e-") as home:
        env = {**os.environ, "NANO_AGENT_HOME": home}
        os.environ["NANO_AGENT_HOME"] = home
        cli = [sys.executable, "-m", "nanoagent"]
        subprocess.run(cli + ["setup", "--non-interactive", "--provider", "fake", "--model", "fake-1", "--name", "E2E", "--skip-test", "--no-start"],
                       cwd=ROOT, env=env, check=True)
        from nanoagent import config

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        cfg = config.load()
        cfg["gateway"]["port"] = port
        config.save(cfg)
        subprocess.run(cli + ["start"], cwd=ROOT, env=env, check=True)
        try:
            from nanoagent import config, keystore

            cfg = config.load()
            base = f"http://{cfg['gateway']['host']}:{cfg['gateway']['port']}"
            token = keystore.get("owner.token")
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            for _ in range(60):
                try:
                    response = opener.open(base + "/healthz", timeout=2)
                    if response.status == 200:
                        break
                except OSError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("gateway did not become healthy")
            page = opener.open(base + "/console", timeout=3).read().decode()
            assert "nano Agent" in page and "console.js" in page
            req = urllib.request.Request(base + "/api/login", data=(f'{{"token":"{token}"}}').encode(),
                                         headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=3) as response:
                import json
                assert json.loads(response.read()).get("ok") is True
            me = opener.open(base + "/api/me", timeout=3).read()
            assert b"E2E" in me
            print("E2E OK: fake setup, gateway health, console, owner login and private API")
        finally:
            subprocess.run(cli + ["stop"], cwd=ROOT, env=env, check=False, stdout=subprocess.DEVNULL)
            os.environ.pop("NANO_AGENT_HOME", None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
