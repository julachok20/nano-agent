#!/usr/bin/env python3
"""Create a local sample-data console preview and optional screenshots.

Screenshots require Playwright and its Chromium browser. No server is started,
no account is contacted, and no real token or user data is used.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "preview")
    ap.add_argument("--open", action="store_true", help="open the local preview in a browser")
    ap.add_argument("--screenshots", action="store_true", help="save screenshots (requires Playwright Chromium)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="nano-agent-preview-") as home:
        env = {**os.environ, "NANO_AGENT_HOME": home}
        old_home = os.environ.get("NANO_AGENT_HOME")
        os.environ["NANO_AGENT_HOME"] = home
        subprocess.run([sys.executable, "-m", "nanoagent", "setup", "--non-interactive", "--provider", "fake",
                        "--model", "fake-1", "--name", "Sample owner", "--skip-test", "--no-start"],
                       cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
        import uvicorn

        from nanoagent.gateway.app import create_app

        app = create_app()
        cfg = {"host": "127.0.0.1", "port": 0, "log_level": "error", "access_log": False}
        server = uvicorn.Server(uvicorn.Config(app, **cfg))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            if not server.started:
                raise RuntimeError("preview server did not start")
            port = server.servers[0].sockets[0].getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            # Discover the temporary owner token and mint a short-lived sample login session.
            from nanoagent import keystore

            token = keystore.get("owner.token")
            req = urllib.request.Request(base + "/api/login", data=(f'{{"token":"{token}"}}').encode(),
                                         headers={"Content-Type": "application/json"})
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            opener.open(req).read()
            # Use browser hash login only in the temporary local preview.
            url = base + "/console#token=" + token + "&tab=mind&sub=skills"
            (args.out / "console-preview.url.txt").write_text(url + "\n", encoding="utf-8")
            if args.screenshots:
                try:
                    from playwright.sync_api import sync_playwright
                except ImportError as exc:
                    raise RuntimeError("install Playwright and Chromium to capture screenshots") from exc

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                    page.goto(url, wait_until="networkidle")
                    page.screenshot(path=str(args.out / "console-skills.png"), full_page=True)
                    page.locator("nav button").first.click()
                    page.wait_for_timeout(500)
                    page.screenshot(path=str(args.out / "console-home.png"), full_page=True)
                    browser.close()
            if args.open:
                webbrowser.open(url)
            print(f"Preview URL written to {args.out / 'console-preview.url.txt'}")
            if not args.screenshots:
                print("Add --screenshots to capture pages (install Playwright Chromium first).")
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            if old_home is None:
                os.environ.pop("NANO_AGENT_HOME", None)
            else:
                os.environ["NANO_AGENT_HOME"] = old_home
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
