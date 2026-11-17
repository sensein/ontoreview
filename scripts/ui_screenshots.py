"""Regenerate the screenshots on the app's Help page (src/ontoreview/ui_assets/help/*.png).

    uv run --extra ui --with playwright python scripts/ui_screenshots.py

Uses Playwright with the Chrome already installed on this machine (no browser download) and demo
ontologies copied to a temporary folder, so no personal paths end up in the images. Docker should be
running so the ROBOT step shows; nothing is uploaded to OOPS! (it is turned off for the demo).
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "src" / "ontoreview" / "ui_assets" / "help"
VIEW = {"width": 1440, "height": 900}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare(demo: Path) -> dict[str, Path]:
    (demo / "pizza").mkdir(parents=True)
    shutil.copy(FIX / "pizza-v2.ttl", demo / "pizza" / "pizza.ttl")
    shutil.copytree(FIX / "real", demo / "w3c-ontologies")
    cfg = demo / "config"
    cfg.mkdir()
    (cfg / "prefs.json").write_text(json.dumps({"open_when_done": False, "oops": "off"}))
    return {"pizza": demo / "pizza" / "pizza.ttl", "folder": demo / "w3c-ontologies", "settings": cfg / "ui.json"}


def wait_text(page: Page, text: str, timeout: float = 180_000) -> None:
    page.get_by_text(text, exact=False).first.wait_for(timeout=timeout)


def set_source(page: Page, path: Path) -> None:
    clear = page.get_by_label("Clear source")
    if clear.count():
        clear.first.click()
    box = page.get_by_placeholder("Type a path or URL and press Enter, or drop files here")
    box.fill(str(path))
    box.press("Enter")


def shoot(page: Page, name: str) -> None:
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / name))
    print("✓", name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    demo = Path(tempfile.mkdtemp(prefix="ontoreview-demo-", dir="/tmp" if os.name != "nt" else None))
    paths = prepare(demo)
    port = free_port()
    env = {**os.environ, "ONTOREVIEW_UI_SETTINGS": str(paths["settings"])}
    server = subprocess.Popen([sys.executable, "-m", "ontoreview.ui", "--port", str(port), "--no-browser"],
                              env=env, cwd=demo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            page = browser.new_page(viewport=VIEW, color_scheme="light")
            page.goto(url + "/")
            wait_text(page, "New build")
            set_source(page, paths["pizza"])
            wait_text(page, "Single ontology")
            page.wait_for_timeout(2500)            # sidebar environment status
            shoot(page, "build.png")

            page.get_by_role("button", name="Build docs").click()
            wait_text(page, "Terms documented")
            page.get_by_text("Issues", exact=True).first.scroll_into_view_if_needed()
            page.evaluate("window.scrollTo(0, 0)")
            shoot(page, "results.png")

            set_source(page, paths["folder"])
            wait_text(page, "Folder with")
            page.get_by_role("button", name="Build docs").click()
            wait_text(page, "of 5 succeeded")
            page.get_by_text("Ontologies", exact=True).first.scroll_into_view_if_needed()
            shoot(page, "folder.png")

            set_source(page, paths["pizza"])
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_role("button", name="Project config").click()
            page.get_by_text("New from template").click()
            wait_text(page, "Valid configuration")
            shoot(page, "config.png")
            page.keyboard.press("Escape")

            page.goto(url + "/history")
            wait_text(page, "runs shown")
            shoot(page, "history.png")

            page.goto(url + "/settings")
            wait_text(page, "Default output folder")
            page.get_by_role("tab", name="Quality checks").click()
            page.wait_for_timeout(1500)
            shoot(page, "settings.png")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        shutil.rmtree(demo, ignore_errors=True)


if __name__ == "__main__":
    main()
