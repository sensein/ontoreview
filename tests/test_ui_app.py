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
        await user.should_see("1. What to document")
        user.find(marker="source").type(str(src))
        await user.should_see("Folder with 2 ontologies.")
        user.find(marker="output").type(str(out))
        await user.should_see(f"ontoreview build {src} -o {out}")
        user.find(marker="run").click()
        for _ in range(100):                          # the build runs in a worker thread
            if (out / "index.html").exists() and ui_core.HISTORY_FILE.exists():
                break
            await asyncio.sleep(0.1)
        await user.should_see("2 of 2 succeeded")
        await user.should_see("Open folder")
        await user.should_see("Previous runs")
        await user.should_see("1 of 1 shown")
        await user.should_see(ui.table)

    assert (out / "vocab" / "colors" / "index.html").is_file()
    history = json.loads(ui_core.HISTORY_FILE.read_text())
    assert history[0]["ok"] == 2 and history[0]["source"] == str(src)
    assert json.loads(ui_core.SETTINGS_FILE.read_text())["source"] == str(src)   # remembered for next time


@pytest.mark.anyio
async def test_missing_source_is_reported(isolated):
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        user.find(marker="source").clear()
        user.find(marker="run").click()
        await user.should_see("Choose an ontology file or a folder of ontologies.")
