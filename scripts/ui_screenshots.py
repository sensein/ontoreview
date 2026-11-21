"""Regenerate the screenshots on the app's Help page (src/ontoreview/ui_assets/help/*.png).

    uv run --extra ui --with playwright python scripts/ui_screenshots.py            # all
    uv run --extra ui --extra cdi --with playwright python scripts/ui_screenshots.py --only cdi   # or si, docs, fixes
(docs: the generated example site for the README, in guide/images; run build_examples.py first)

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
    (demo / "pizza" / "releases").mkdir()
    shutil.copy(FIX / "pizza.ttl", demo / "pizza" / "releases" / "pizza-1.0.ttl")
    shutil.copytree(FIX / "real", demo / "w3c-ontologies")
    cfg = demo / "config"
    cfg.mkdir()
    # cross-domain interoperability gets its own server and screenshots (cdi_shots); keep the others fast
    (cfg / "prefs.json").write_text(json.dumps({"open_when_done": False, "oops": "off", "cdi": False, "si": False,
                                                 "deploy_remote": "https://github.com/you/pizza-docs"}))
    (demo / "soil").mkdir()
    for f in ("toy_onto.ttl", "toy_ref.ttl", "toy_to_bfo.sssom.tsv"):
        shutil.copy(FIX / "cdi" / f, demo / "soil" / f)
    (demo / "soil" / "toy_onto.ttl").rename(demo / "soil" / "soil.ttl")
    return {"soil": demo / "soil" / "soil.ttl", "soil_refs": [demo / "soil" / "toy_ref.ttl", demo / "soil" / "toy_to_bfo.sssom.tsv"],
            "pizza": demo / "pizza" / "pizza.ttl", "previous": demo / "pizza" / "releases" / "pizza-1.0.ttl", "folder": demo / "w3c-ontologies", "settings": cfg / "ui.json"}


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


def serve(settings: Path, demo: Path, review: bool = False) -> tuple[subprocess.Popen, str]:
    port = free_port()
    # most shots show build results: skip the Quality issues review step (fixes_shots shows it)
    prefs = settings.with_name("prefs.json")
    data = json.loads(prefs.read_text()) if prefs.exists() else {}
    prefs.write_text(json.dumps({**data, "fix_review": review}))
    # a term database of its own: no personal paths or earlier runs in the images
    env = {**os.environ, "ONTOREVIEW_UI_SETTINGS": str(settings), "ONTOREVIEW_IRI_DB": str(demo / "iri.sqlite3"),
           "ONTOREVIEW_REQUIRE_METADATA": "1" if review else "0"}
    server = subprocess.Popen([sys.executable, "-m", "ontoreview.ui", "--port", str(port), "--no-browser"],
                              env=env, cwd=demo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.2)
    return server, f"http://127.0.0.1:{port}"


def fixes_shots(browser, demo: Path, paths: dict) -> None:
    """The Quality issues page: required metadata, and AI suggestions from a local Ollama model (soil toy
    ontology). Needs Ollama running with ONTOREVIEW_SHOT_MODEL (default qwen3.5:9b); nothing leaves the machine."""
    cfg = demo / "config-fixes"
    cfg.mkdir()
    model = os.environ.get("ONTOREVIEW_SHOT_MODEL", "qwen3.5:9b")
    (cfg / "prefs.json").write_text(json.dumps({"open_when_done": False, "oops": "off", "robot_enabled": False,
                                                 "cdi": False, "si": False, "ai_enabled": True,
                                                 "ai_priority": "ollama", "ai_ollama_model": model}))
    server, url = serve(cfg / "ui.json", demo, review=True)
    try:
        page = browser.new_page(viewport=VIEW, color_scheme="light")
        page.goto(url + "/")
        wait_text(page, "New build")
        set_source(page, paths["soil"])
        wait_text(page, "Single ontology")
        page.get_by_role("button", name="Build docs").click()
        wait_text(page, "Found in this check")
        wait_text(page, "Required metadata")
        page.wait_for_timeout(1500)
        shoot(page, "fixes.png")
        wait_text(page, "(AI draft)", timeout=600_000)             # the local model drafts definitions
        page.get_by_text("(AI draft)", exact=False).first.click()
        wait_text(page, "Made by")
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
        shoot(page, "fixes-ai.png")
        sugg = page.get_by_text("(AI suggestion)", exact=False)
        try:
            sugg.first.wait_for(timeout=300_000)                   # ranked domains / ranges
            sugg.first.click()
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(600)
            shoot(page, "fixes-ai-domain.png")
        except Exception:  # noqa: BLE001 - the model may suggest none
            print("· no domain/range suggestion this time")
        page.close()
    finally:
        server.terminate()


def cdi_shots(browser, demo: Path, paths: dict) -> None:
    """Settings card and results of the cross-domain interoperability score (soil toy ontology)."""
    cfg = demo / "config-cdi"
    cfg.mkdir()
    refs = "\n".join(["ols", *map(str, paths["soil_refs"])])
    (cfg / "prefs.json").write_text(json.dumps({"open_when_done": False, "oops": "off", "robot_enabled": False,
                                                 "cdi": True, "cdi_references": refs, "cdi_domains": "agriculture"}))
    server, url = serve(cfg / "ui.json", demo)
    try:
        page = browser.new_page(viewport=VIEW, color_scheme="light")
        page.goto(url + "/settings")
        wait_text(page, "Default output folder")
        page.get_by_role("tab", name="Quality checks").click()
        page.get_by_text("Score cross-domain interoperability").first.wait_for()
        page.get_by_text("Cross-domain interoperability", exact=True).first.evaluate(
            "e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, -60)
        shoot(page, "cdi-settings.png")
        page.goto(url + "/")
        wait_text(page, "New build")
        set_source(page, paths["soil"])
        wait_text(page, "Single ontology")
        page.get_by_role("button", name="Build docs").click()
        wait_text(page, "Terms documented", timeout=900_000)      # first run downloads the language models
        page.get_by_text("CDI score", exact=True).first.evaluate("e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, -90)
        shoot(page, "cdi-results.png")
        page.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


def si_shots(browser, demo: Path, paths: dict) -> None:
    """Scientific interoperability: Settings card, the Interoperability page before and after a run, the SI
    metrics, and the Run history configuration dialog (soil toy ontology, file references, offline)."""
    cfg = demo / "config-si"
    cfg.mkdir()
    refs = "\n".join(map(str, paths["soil_refs"]))
    (cfg / "prefs.json").write_text(json.dumps({
        "open_when_done": False, "oops": "off", "robot_enabled": False, "cdi": True, "si": True,
        "cdi_references": refs, "cdi_ontoaligner": "off", "si_home_domain": "4.1", "si_theta_s": 0.25,
        "si_domain_map": "file:toy_ref.ttl = 1.5\nsssom:toy_to_bfo.sssom.tsv = 1.6"}))
    server, url = serve(cfg / "ui.json", demo)
    try:
        page = browser.new_page(viewport=VIEW, color_scheme="light")
        page.goto(url + "/settings")
        wait_text(page, "Default output folder")
        page.get_by_role("tab", name="Quality checks").click()
        page.get_by_text("Score scientific interoperability").first.wait_for()
        page.get_by_text("Scientific interoperability", exact=True).first.evaluate(
            "e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, -60)
        shoot(page, "si-settings.png")

        page.goto(url + "/interoperability")
        wait_text(page, "No interoperability check yet")
        box = page.get_by_label("Ontology path or URL")
        box.fill(str(paths["soil"]))
        box.press("Enter")
        page.get_by_label("Find an ontology").first.fill("environment")
        page.get_by_label("Find an ontology").first.press("Enter")
        try:
            wait_text(page, "Environment Ontology", timeout=30_000)        # live OLS search; skipped offline
        except Exception:  # noqa: BLE001
            pass
        page.evaluate("window.scrollTo(0, 0)")
        shoot(page, "interop.png")
        page.get_by_role("button", name="Run checks").click()
        page.get_by_role("button", name="New check").first.wait_for(timeout=900_000)   # the finished result
        page.get_by_role("button", name="New check").first.evaluate("e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, -120)
        shoot(page, "interop-results.png")
        page.get_by_text("Scientific interoperability", exact=True).last.evaluate(
            "e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, -40)
        shoot(page, "si-results.png")

        page.goto(url + "/history")
        wait_text(page, "runs shown")
        page.locator("tbody tr").first.click()
        wait_text(page, "Edit and run")
        shoot(page, "history-config.png")
        page.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


GUIDE = ROOT / "guide" / "images"


def docs_shots(browser) -> None:
    """The generated documentation (examples/site/cdi-sosa) for the README: run build_examples.py first."""
    site = ROOT / "examples" / "site" / "cdi-sosa" / "index.html"
    if not site.is_file():
        print("skip docs shots: run scripts/build_examples.py first")
        return
    GUIDE.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport=VIEW, color_scheme="light")
    page.goto(site.as_uri())
    page.wait_for_timeout(800)
    page.screenshot(path=str(GUIDE / "docs-overview.png"))
    for anchor, name, off in (("#graph", "docs-graph.png", -20), ("#quality", "docs-quality.png", -20),
                              ("#quality-scientific-interoperability", "docs-si.png", -30),
                              ("#provenance", "docs-provenance.png", -20)):
        page.locator(anchor).first.evaluate("e => e.scrollIntoView({block: 'start'})")
        page.mouse.wheel(0, off)
        page.wait_for_timeout(1200 if anchor == "#graph" else 400)
        page.screenshot(path=str(GUIDE / name))
        print("✓", name)
    page.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    demo = Path(tempfile.mkdtemp(prefix="ontoreview-demo-", dir="/tmp" if os.name != "nt" else None))
    paths = prepare(demo)
    if only == "docs":
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome")
            docs_shots(browser)
            browser.close()
        shutil.rmtree(demo, ignore_errors=True)
        return
    if only == "fixes":
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                fixes_shots(browser, demo, paths)
                browser.close()
        finally:
            shutil.rmtree(demo, ignore_errors=True)
        return
    if only in ("cdi", "si"):
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                (cdi_shots if only == "cdi" else si_shots)(browser, demo, paths)
                browser.close()
        finally:
            shutil.rmtree(demo, ignore_errors=True)
        return
    server, url = serve(paths["settings"], demo)
    try:
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

            page.goto(url + "/compare")
            wait_text(page, "Nothing compared yet")
            for side, path in (("old", paths["previous"]), ("new", paths["pizza"])):
                box = page.get_by_label(f"{side} version path or URL")
                box.fill(str(path))
                box.press("Enter")
            wait_text(page, "Changes found")
            shoot(page, "compare.png")
            page.get_by_text("Changes", exact=True).first.scroll_into_view_if_needed()
            page.mouse.wheel(0, 260)
            shoot(page, "compare-table.png")
            report = browser.new_page(viewport={"width": 1100, "height": 760}, color_scheme="light")
            report.goto((paths["pizza"].parent / "changes.html").as_uri())
            shoot(report, "compare-report.png")
            report.close()

            page.goto(url + "/")
            wait_text(page, "New build")
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
            page.get_by_label("Deploy to GitHub Pages").first.click()      # the dialog only; nothing is pushed
            wait_text(page, "The site will be at")
            shoot(page, "deploy.png")
            page.keyboard.press("Escape")

            page.goto(url + "/settings")
            wait_text(page, "Default output folder")
            page.get_by_role("tab", name="Quality checks").click()
            page.wait_for_timeout(1500)
            shoot(page, "settings.png")
            cdi_shots(browser, demo, paths)
            si_shots(browser, demo, paths)
            docs_shots(browser)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        shutil.rmtree(demo, ignore_errors=True)


if __name__ == "__main__":
    main()
