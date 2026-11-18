"""ontoreview-ui page, driven through NiceGUI's simulated user (no browser needed)."""

import asyncio
import json
import shutil

import pytest

pytest.importorskip("nicegui")

from nicegui import ui  # noqa: E402
from nicegui.testing.user_simulation import user_simulation  # noqa: E402

from ontoreview import ui_core  # noqa: E402
from ontoreview.ui import build_page  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_core, "SETTINGS_FILE", tmp_path / "cfg" / "ui.json")
    monkeypatch.setattr(ui_core, "HISTORY_FILE", tmp_path / "cfg" / "history.json")
    from ontoreview.ui import SESSION
    SESSION.reset()                      # run state is process-wide (it outlives page switches)
    return tmp_path


@pytest.mark.anyio
async def test_run_folder_from_the_ui(isolated, fixtures):
    src = isolated / "ontos"
    (src / "vocab").mkdir(parents=True)
    shutil.copy(fixtures / "pizza.ttl", src / "pizza.ttl")
    shutil.copy(fixtures / "colors-skos.ttl", src / "vocab" / "colors.ttl")
    out = isolated / "site"

    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("New build")
        await user.should_see("No build yet")
        user.find(marker="source").type(str(src)).trigger("keydown.enter")
        await user.should_see("Folder with 2 ontologies.")
        user.find(marker="output").type(str(out))
        await user.should_see(f"ontoreview build {src} -o {out}")
        user.find(marker="run").click()
        for _ in range(100):                          # the build runs in a worker thread
            if (out / "index.html").exists() and ui_core.HISTORY_FILE.exists():
                break
            await asyncio.sleep(0.1)
        await user.should_see("2 of 2 succeeded")
        await user.should_see("Show in folder")
        await user.should_see("Terms documented")
        await user.should_see("Issues")
        await user.should_see(ui.table)

    assert (out / "vocab" / "colors" / "index.html").is_file()
    history = json.loads(ui_core.HISTORY_FILE.read_text())
    assert history[0]["ok"] == 2 and history[0]["source"] == str(src)
    assert json.loads(ui_core.SETTINGS_FILE.read_text())["source"] == str(src)   # remembered for next time


@pytest.mark.anyio
async def test_missing_source_is_reported(isolated):
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        user.find(marker="run").click()
        await user.should_see("Choose an ontology file or a folder of ontologies.")


@pytest.mark.anyio
async def test_pages_render(isolated, fixtures):
    s = ui_core.Settings(source=str(fixtures / "pizza.ttl"), output=str(isolated / "d"))
    ui_core.record_run(s, ui_core.run_task(s))
    ui_core.Settings(source=str(fixtures / "pizza.ttl"), output=str(isolated / "d"), task="check",
                     fail_on="warning", languages="en, es").save()       # saved form state used to crash the page
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("pizza.ttl")
        await user.should_see("Run checks")
        await user.open("/history")
        await user.should_see("Run history")
        await user.should_see("1 of 1 runs shown")     # badges are drawn client-side, inside the table slot
        await user.open("/settings")
        await user.should_see("Your defaults for every build")
        await user.should_see("Default output folder")
        user.find(marker="save-settings").click()
        await user.should_see("Settings saved")
        await user.open("/about")
        await user.should_see("Developed by CAIR-Nepal")
        await user.open("/help")
        await user.should_see("Getting started")
        await user.should_see("Project config (ontoreview.toml)")
        await user.should_see("How the comparison works")
        await user.should_see("System info")
    assert ui_core.Prefs.path().is_file()


def test_choose_port():
    import socket

    from ontoreview.ui import DEFAULT_PORT, choose_port, port_free

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert not port_free("127.0.0.1", taken)
        with pytest.raises(SystemExit, match="already in use"):
            choose_port("127.0.0.1", taken)
    assert DEFAULT_PORT <= choose_port("127.0.0.1", None) < DEFAULT_PORT + 50


@pytest.mark.anyio
async def test_drop_upload_endpoint(isolated, fixtures):
    import httpx2
    from nicegui import core

    from ontoreview import ui as ui_mod

    async with user_simulation(root=build_page) as user:
        await user.open("/")
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(core.app), base_url="http://test") as c:
            url = ui_mod.UPLOAD_URL + "?batch=00112233aabbccdd"
            ok = {"X-Upload-Token": ui_mod.UPLOAD_TOKEN}
            body = (fixtures / "pizza.ttl").read_bytes()
            assert (await c.post(url, content=body, headers={"X-Upload-Token": "wrong", "X-Path": "a.ttl"})).status_code == 403
            assert (await c.post(url, content=body, headers={**ok, "X-Path": "..%2F..%2Fevil.ttl"})).status_code == 400
            assert (await c.post(url, content=b"x", headers={**ok, "X-Path": "run.sh"})).status_code == 400
            for rel in ("myonto%2Fpizza.ttl", "myonto%2Fvocab%2Fcolors.ttl"):
                r = await c.post(url, content=body, headers={**ok, "X-Path": rel})
                assert r.status_code == 200, r.text
    root = ui_core.uploads_dir() / "00112233aabbccdd"
    assert (root / "myonto" / "vocab" / "colors.ttl").is_file()
    assert ui_core.upload_source("00112233aabbccdd") == str(root / "myonto")
    assert not (isolated / "evil.ttl").exists()


@pytest.mark.anyio
async def test_sidebar_shows_environment(isolated, monkeypatch):
    monkeypatch.setattr(ui_core, "robot_status", lambda prefs: {"state": "ok", "label": "ROBOT · Docker ready"})
    import ontoreview.ui as ui_mod
    monkeypatch.setattr(ui_mod, "robot_status", ui_core.robot_status)
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("ROBOT · Docker ready", retries=30)
        await user.should_see("OOPS! · not checked")


@pytest.mark.anyio
async def test_config_editor_saves_and_applies(isolated, fixtures):
    src = isolated / "proj"
    src.mkdir()
    shutil.copy(fixtures / "pizza.ttl", src / "pizza.ttl")
    ui_core.Settings(source=str(src / "pizza.ttl")).save()
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("pizza.ttl")
        user.find(marker="cfg-note_add").click()
        await user.should_see("Valid configuration")
        user.find(marker="config-save-use").click()
        await user.should_see("Loaded")
    saved = (src / "ontoreview.toml").read_text()
    assert 'source = "pizza.ttl"' in saved and "[evaluation]" in saved


@pytest.mark.anyio
async def test_help_links_navigate(isolated):
    async with user_simulation(root=build_page) as user:
        await user.open("/help")
        await user.should_see("Open Run history")
        user.find("Open Run history").click()
        await user.should_see("Every build and check you've run")


@pytest.mark.anyio
async def test_compare_versions_from_the_ui(isolated, fixtures):
    src = isolated / "proj"
    src.mkdir()
    shutil.copy(fixtures / "pizza-v2.ttl", src / "pizza.ttl")
    ui_core.Settings(source=str(src / "pizza.ttl")).save()
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        user.find(marker="fmt-diff").click()
        await user.should_see("Previous version")
        user.find(marker="previous").type(str(fixtures / "pizza.ttl"))
        user.find(marker="run").click()
        for _ in range(100):
            if (src / "changes.md").exists():
                break
            await asyncio.sleep(0.1)
        await user.should_see("Changes found")
        await user.should_see("Open HTML report")
    assert (src / "changes.json").is_file() and (src / "changes.html").is_file()


@pytest.mark.anyio
async def test_compare_page_runs_automatically(isolated, fixtures):
    out = isolated / "report" / "pizza-changes.md"
    async with user_simulation(root=build_page) as user:
        await user.open("/compare")
        await user.should_see("Nothing compared yet")
        user.find(marker="compare-output").type(str(out))
        user.find(marker="compare-old").type(str(fixtures / "pizza.ttl")).trigger("keydown.enter")
        await user.should_see("Nothing compared yet")                 # one side only: waits
        user.find(marker="compare-new").type(str(fixtures / "pizza-v2.ttl")).trigger("keydown.enter")
        for _ in range(100):                                          # both sides: runs on its own
            if out.with_suffix(".html").exists():
                break
            await asyncio.sleep(0.1)
        await user.should_see("Changes found")
        await user.should_see("Download HTML")
    html = out.with_suffix(".html").read_text()
    assert "<table>" in html and "Calzone" in html and out.with_suffix(".json").is_file() and out.is_file()
    entry = json.loads(ui_core.HISTORY_FILE.read_text())[0]
    assert entry["task"] == "diff" and "added" in entry["summary"]


def _slow_run_task(monkeypatch, delay=1.0):
    """run_task that is still busy while the test navigates away."""
    import time

    import ontoreview.ui as ui_mod
    real = ui_core.run_task

    def slow(settings):
        time.sleep(delay)
        return real(settings)
    monkeypatch.setattr(ui_mod, "run_task", slow)


@pytest.mark.anyio
async def test_build_survives_switching_pages(isolated, fixtures, monkeypatch):
    _slow_run_task(monkeypatch)
    src = isolated / "proj"
    src.mkdir()
    shutil.copy(fixtures / "pizza.ttl", src / "pizza.ttl")
    out = isolated / "out"
    ui_core.Settings(source=str(src / "pizza.ttl"), output=str(out)).save()
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("pizza.ttl")
        user.find(marker="run").click()
        await user.should_see("Building pizza.ttl")
        await user.open("/history")                       # leave while it runs
        await user.should_see("Run history")
        for _ in range(100):
            if (out / "index.html").exists() and ui_core.HISTORY_FILE.exists():
                break
            await asyncio.sleep(0.1)
        await user.open("/")                              # come back: the finished result is shown
        await user.should_see("Terms documented")
        await user.should_see("Show in folder")
    assert json.loads(ui_core.HISTORY_FILE.read_text())[0]["ok"] == 1


@pytest.mark.anyio
async def test_compare_survives_switching_pages(isolated, fixtures, monkeypatch):
    _slow_run_task(monkeypatch)
    out = isolated / "report" / "changes.md"
    async with user_simulation(root=build_page) as user:
        await user.open("/compare")
        user.find(marker="compare-output").type(str(out))
        user.find(marker="compare-old").type(str(fixtures / "pizza.ttl")).trigger("keydown.enter")
        user.find(marker="compare-new").type(str(fixtures / "pizza-v2.ttl")).trigger("keydown.enter")
        await user.should_see("Comparing")
        await user.open("/settings")                      # leave while it runs
        await user.should_see("Default output folder")
        for _ in range(100):
            if out.with_suffix(".html").exists():
                break
            await asyncio.sleep(0.1)
        await user.open("/compare")
        await user.should_see("Changes found")


@pytest.mark.anyio
async def test_sidebar_shows_running_task(isolated, fixtures, monkeypatch):
    from ontoreview.ui import SESSION

    async with user_simulation(root=build_page) as user:
        await user.open("/help")
        SESSION.build["running"] = True
        await user.should_see(kind=ui.spinner, retries=20)
        SESSION.build["running"] = False
