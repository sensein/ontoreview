"""ontoreview-ui page, driven through NiceGUI's simulated user (no browser needed)."""

import asyncio
import json
import shutil
from pathlib import Path
import time

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
    (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)       # builds go straight through unless a test
    (tmp_path / "cfg" / "prefs.json").write_text('{"fix_review": false}')   # exercises the review step
    from ontoreview.ui import ORCID_DISMISSED, ORCID_HITS, SESSION
    SESSION.reset()                      # run state is process-wide (it outlives page switches)
    ORCID_HITS.clear()
    ORCID_DISMISSED.clear()
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
            runs = list(isolated.glob("site-*"))      # each run gets its own dated folder
            if runs and (runs[0] / "index.html").exists() and ui_core.HISTORY_FILE.exists():
                break
            await asyncio.sleep(0.1)
        from ontoreview.ui import SESSION
        for _ in range(100):                          # the toast can appear a tick before the results card
            if not SESSION.build["running"]:
                break
            await asyncio.sleep(0.1)
        await user.should_see("2 of 2 succeeded", retries=20)
        await user.should_see("Show in folder", retries=20)
        await user.should_see(marker="export-output")
        await user.should_see("Terms documented")
        await user.should_see("Issues")
        await user.should_see(ui.table)
        user.find(marker="new-build").click()             # clears the result; the run stays in history
        await user.should_see("No build yet")
        await user.should_not_see("Terms documented")

    (run_dir,) = isolated.glob("site-*")
    assert (run_dir / "vocab" / "colors" / "index.html").is_file() and not out.exists()
    history = json.loads(ui_core.HISTORY_FILE.read_text())
    assert history[0]["ok"] == 2 and history[0]["source"] == str(src)
    assert history[0]["output"] == str(run_dir)
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
        await user.should_see("Scientific interoperability")
        await user.should_see("Run history: re-run, change, export")
        await user.should_see("Interoperability page")
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
        await user.should_see("Building pizza.ttl", retries=20)
        await user.open("/history")                       # leave while it runs
        await user.should_see("Run history")
        for _ in range(100):
            runs = list(isolated.glob("out-*"))      # each run gets its own dated folder
            if runs and (runs[0] / "index.html").exists() and ui_core.HISTORY_FILE.exists():
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


@pytest.mark.anyio
async def test_history_shows_config_and_reruns(isolated, fixtures):
    s = ui_core.Settings(source=str(fixtures / "pizza.ttl"), output=str(isolated / "d"), oops="off", cdi=False)
    res = ui_core.run_task(s)
    entry = ui_core.record_run(s, res)
    assert res.output.name.startswith("d-") and (res.output / "standalone.html").is_file()
    async with user_simulation(root=build_page) as user:
        await user.open("/history")
        await user.should_see("1 of 1 runs shown")
        user.find(ui.table).trigger("rowClick", [{}, {"id": entry.id}, 0])      # click the row
        await user.should_see("Configuration")
        await user.should_see("Each run in its own folder")
        await user.should_see("Edit and run")
        user.find("Edit and run").click()
        await user.should_see("New build")
        await user.should_see("Settings from that run loaded", retries=20)
        await user.should_see("a new folder each run")


@pytest.mark.anyio
@pytest.mark.real_cdi
async def test_interoperability_page(isolated, fixtures, monkeypatch):
    from ontoreview.quality_checks import cdi
    from ontoreview.quality_checks.cdi import core
    from ontoreview.ui import SESSION

    monkeypatch.setattr(cdi, "generality_backend", lambda ev: (core.CallableBackend(
        lambda t: [0.1, 0.2, 0.4, 0.2, 0.1] if len(t) > 60 else [0.5, 0.3, 0.1, 0.05, 0.05]), ""))
    d = fixtures / "cdi"
    SESSION.interop["s"] = ui_core.Settings(
        source=str(d / "toy_onto.ttl"), task="interop", output=str(isolated / "iop.json"),
        cdi_references=f"{d / 'toy_ref.ttl'}\n{d / 'toy_to_bfo.sssom.tsv'}", cdi_ontoaligner="off",
        si_home_domain="4.1", si_domain_map="file:toy_ref.ttl = 1.5", iri_network=False)
    async with user_simulation(root=build_page) as user:
        await user.open("/interoperability")
        await user.should_see("No interoperability check yet")
        await user.should_see("Find on OLS or BioPortal")
        user.find(marker="interop-run").click()
        for _ in range(100):
            if not SESSION.interop["running"] and SESSION.interop["last"] is not None:
                break
            await asyncio.sleep(0.1)
        await user.should_see("Scientific interoperability (SI)", retries=20)
        await user.should_see(marker="iop-metrics")
        await user.should_see("of 41 domains: 1.5 Earth and related environmental sciences")
        user.find(marker="iop-new").click()
        await user.should_see("No interoperability check yet")
    (run_dir,) = isolated.glob("iop-*")                          # each run in its own folder, self-contained
    assert {"iop.json", "cdi.json", "si.json", "provenance.ttl"} <= {f.name for f in run_dir.iterdir()}
    rep = json.loads((run_dir / "iop.json").read_text())["toy_onto.ttl"]
    assert [x["tool"] for x in rep["external"]] == ["Cross-domain interoperability", "Scientific interoperability"]
    assert rep["findings"] == []                                  # interoperability only: no built-in rules
    assert json.loads(ui_core.HISTORY_FILE.read_text())[0]["task"] == "interop"


@pytest.mark.anyio
async def test_domain_rows_add_themselves(isolated):
    async with user_simulation(root=build_page) as user:
        await user.open("/settings")
        await user.should_see("Scientific interoperability")
        assert len(user.find(marker="si-domain-id").elements) == 1
        user.find(marker="si-domain-id").type("ols:emi")
        await user.should_see(marker="si-domain-id")
        assert len(user.find(marker="si-domain-id").elements) == 2     # a new empty row appeared


def test_interop_task_settings(fixtures):
    s = ui_core.Settings(source=str(fixtures / "pizza.ttl"), task="interop", si_references="ols:envo")
    ev = s.evaluation()
    assert (ev["robot"], ev["oops"], ev["ontocheck"], ev["iri_checks"], ev["reasoner"]) == ("off",) * 5
    assert ev["si_references"] == ["ols:envo"]
    assert "--interop-only" in s.cli() and "--si-ref ols:envo" in s.cli()
    assert s.default_output().endswith("interoperability.json")
    assert ui_core.task_kind("interop") == "check"
    off = ui_core.Settings(source=str(fixtures / "pizza.ttl"), task="interop", cdi=False, si=False)
    assert any("cross-domain or scientific" in p for p in off.validate())


def test_help_screenshots_exist():
    from ontoreview.ui import ASSETS, HELP
    for _, _, shot, *_ in HELP:
        for name in [n for n in ((shot,) if isinstance(shot, str) else shot) if n]:
            assert (ASSETS / "help" / name).is_file(), name


@pytest.mark.anyio
async def test_deploy_dialog_from_results(isolated, fixtures, monkeypatch):
    from ontoreview.publish import github
    from ontoreview.publish.github import DeployResult

    calls = []

    def fake_deploy(site, remote, branch="main", message=None, enable_pages=True, **kw):
        calls.append((site, remote, branch))
        return DeployResult(remote, branch, "https://you.github.io/onto-docs/", "https://github.com/you/onto-docs",
                            commit="abc1234")
    monkeypatch.setattr(github, "deploy_site", fake_deploy)
    s = ui_core.Settings(source=str(fixtures / "pizza.ttl"), output=str(isolated / "d"), oops="off", cdi=False,
                         si=False)
    res = ui_core.run_task(s)
    ui_core.record_run(s, res)
    async with user_simulation(root=build_page) as user:
        await user.open("/history")
        await user.should_see("1 of 1 runs shown")
        entry = ui_core.load_history()[0]
        user.find(ui.table).trigger("deploy", {"id": entry.id})
        await user.should_see("Deploy to GitHub Pages")
        user.find(marker="deploy-remote").clear().type("https://github.com/you/onto-docs")
        await user.should_see("The site will be at https://you.github.io/onto-docs/")
        user.find(marker="deploy-go").click()
        await user.should_see("Deployed", retries=50)
        await user.should_see("Commit abc1234 on main")
    assert calls == [(str(res.output), "https://github.com/you/onto-docs", "main")]
    assert ui_core.load_history()[0].deploys[0]["pages_url"] == "https://you.github.io/onto-docs/"
    assert ui_core.Prefs.load().deploy_remote == "https://github.com/you/onto-docs"


@pytest.mark.anyio
async def test_help_search(isolated):
    async with user_simulation(root=build_page) as user:
        await user.open("/help")
        await user.should_see("Getting started")
        user.find(marker="help-search").type("github pages")
        await user.should_see("Deploy: GitHub Pages, Docker, any server")
        await user.should_not_see("How the comparison works")
        user.find(marker="help-search").clear().type("θ_s")
        await user.should_see("Scientific interoperability")
        user.find(marker="help-search").clear().type("zzzz-nothing")
        await user.should_see("No help topic mentions")


@pytest.mark.anyio
async def test_review_before_build_asks_required_metadata(isolated, fixtures, monkeypatch):
    monkeypatch.setenv("ONTOREVIEW_REQUIRE_METADATA", "1")
    import ontoreview.fixes.orcid as orcid
    monkeypatch.setattr(orcid, "search_orcid", lambda name, **kw: [
        {"orcid": "0000-0001-0000-0001", "name": name, "institutions": [], "url": "https://orcid.org/0000-0001-0000-0001"},
        {"orcid": "0000-0002-1825-0097", "name": name, "institutions": ["Royal Society"],
         "url": "https://orcid.org/0000-0002-1825-0097"}])
    src = isolated / "toy_onto.ttl"
    shutil.copy(fixtures / "cdi" / "toy_onto.ttl", src)
    original = src.read_bytes()
    ui_core.Settings(source=str(src), output=str(isolated / "docs"), oops="off", cdi=False, si=False,
                     separate_runs=False).save()
    ui_core.Prefs(ai_enabled=False, fix_review=True).save()
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("toy_onto.ttl")
        user.find(marker="run").click()
        await user.should_see("Found in this check", retries=50)      # the Quality issues page, before any docs
        await user.should_see("Required metadata")
        user.find(marker="issue-title").type("Soil sensing")
        user.find(marker="issue-accept").click()
        await user.should_see(marker="issue-description")
        user.find(marker="issue-description").type("Soil pH readings.")
        user.find(marker="issue-accept").click()
        await user.should_see(marker="issue-license")
        user.find(marker="issue-license").elements.pop().set_value("https://creativecommons.org/licenses/by/4.0/")
        user.find(marker="issue-accept").click()
        await user.should_see(marker="creator-name")
        user.find(marker="creator-name").type("Ada Lovelace")
        user.find(marker="orcid-find").click()                       # ORCID candidates for the name; user picks
        await user.should_see("Is one of these the creator?", retries=30)
        await user.should_see("Royal Society")
        user.find(marker="orcid-0000-0002-1825-0097").click()        # the second candidate
        assert user.find(marker="creator-orcid").elements.pop().value == "0000-0002-1825-0097"
        user.find(marker="creator-add").click()
        await user.should_see(marker="creator-name")
        names = sorted(user.find(marker="creator-name").elements, key=lambda e: e.id)
        names[-1].set_value("Grace Hopper")
        user.find(marker="issue-accept").click()
        await user.should_see("Apply 4 fixes & build docs", retries=20)
        user.find(marker="issues-apply").click()
        from ontoreview.ui import SESSION
        for _ in range(150):
            if (isolated / "docs" / "index.html").exists() and not SESSION.build["running"]:
                break
            await asyncio.sleep(0.1)
        await user.should_see("Terms documented", retries=30)
    assert src.read_bytes() == original                                   # the original is never changed
    fixed = isolated / "toy_onto-v1.ttl"
    assert fixed.is_file() and (isolated / "toy_onto-v1.fixes.json").is_file()
    html = (isolated / "docs" / "index.html").read_text()
    assert "Soil sensing" in html and "Fixes applied" in html
    assert "Ada Lovelace" in html and "Grace Hopper" in html
    entry = json.loads(ui_core.HISTORY_FILE.read_text())[0]
    assert entry["source"] == str(fixed) and entry["derived_from"] == "toy_onto.ttl" and entry["fixes_applied"] == 4
    assert ui_core.load_history()[0].fixed_note.startswith("Fixed version of toy_onto.ttl · 4 of ")


@pytest.mark.anyio
async def test_draft_with_ai_shows_that_it_is_working(isolated, fixtures, monkeypatch):
    """Clicking Draft with AI must visibly change state (working → done), not look like nothing happened."""
    monkeypatch.setenv("ONTOREVIEW_REQUIRE_METADATA", "1")
    import ontoreview.fixes.ai as ai_mod

    class Slow:
        name = "api"
        model = "stub-model"

        def describe(self):
            return {"source": "api", "provider": "stub", "model": self.model}

        def generate(self, system, user, schema):
            if "description" not in user:            # the automatic definition drafts: answer at once
                return {"definition": "A thing that is measured.", "choices": []}
            time.sleep(0.8)
            return {"description": "Soil pH readings from field sensors."}
    monkeypatch.setattr(ai_mod, "pick_source", lambda *a, **k: Slow())
    src = isolated / "toy_onto.ttl"
    shutil.copy(fixtures / "cdi" / "toy_onto.ttl", src)
    ui_core.Settings(source=str(src), output=str(isolated / "docs"), oops="off", cdi=False, si=False,
                     separate_runs=False).save()
    ui_core.Prefs(ai_enabled=True, fix_review=True).save()
    monkeypatch.setattr(ai_mod, "ai_suggestions", lambda *a, **k: [])
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("toy_onto.ttl")
        user.find(marker="run").click()
        await user.should_see("Required metadata", retries=50)
        user.find(marker="issue-title").type("Soil sensing")
        user.find(marker="issue-accept").click()
        await user.should_see(marker="issue-ai-draft")
        from ontoreview.ui import SESSION  # noqa: F401
        await asyncio.sleep(1.0)                     # let the automatic drafts finish first
        user.find(marker="issue-ai-draft").click()
        await user.should_see("Drafting…")
        await user.should_see("AI working…", retries=10)
        await user.should_see("Drafted · review it", retries=40)
        assert user.find(marker="issue-description").elements.pop().value.startswith("Soil pH readings")


@pytest.mark.anyio
async def test_several_reviews_wait_and_each_builds_its_own_ontology(isolated, fixtures):
    """Start a build for A (it waits in Quality issues), then for B: both wait; applying B builds B, not A,
    and A is still there to finish later."""
    from ontoreview.ui import SESSION
    a, b = isolated / "alpha.ttl", isolated / "beta.ttl"
    shutil.copy(fixtures / "cdi" / "toy_onto.ttl", a)
    shutil.copy(fixtures / "cdi" / "toy_onto.ttl", b)
    ui_core.Prefs(ai_enabled=False, fix_review=True).save()
    async with user_simulation(root=build_page) as user:
        for src in (a, b):
            ui_core.Settings(source=str(src), output=str(isolated / f"docs-{src.stem}"), oops="off", cdi=False,
                             si=False, separate_runs=False).save()
            await user.open("/")
            await user.should_see(src.name)
            user.find(marker="run").click()
            await user.should_see("Found in this check", retries=50)
        await user.should_see(marker="reviews-all")
        assert set(SESSION.reviews) == {str(a.resolve()), str(b.resolve())}
        assert SESSION.fixes["session"].source.name == "beta.ttl"
        user.find(marker="issues-skip").click()                      # build the one shown: beta
        for _ in range(150):
            if (isolated / "docs-beta" / "index.html").exists() and not SESSION.build["running"]:
                break
            await asyncio.sleep(0.1)
        assert (isolated / "docs-beta" / "index.html").exists()
        assert not (isolated / "docs-alpha").exists()                 # alpha was not built
        status = {Path(k).name: e["status"] for k, e in SESSION.reviews.items()}
        assert status == {"alpha.ttl": "open", "beta.ttl": "skipped"}  # alpha still waits; beta is listed as built
        await user.open("/issues")                                     # the list, like Run history
        await user.should_see(marker="review-row-alpha.ttl")
        await user.should_see("Built from the original", retries=10)
        user.find(marker="review-open").click()                        # come back to alpha later
        await user.should_see("Found in this check", retries=50)
        await user.should_see(marker="reviews-all")
    # a restart keeps the waiting review (re-checked when opened)
    SESSION.reset()
    assert {Path(k).name: e["status"] for k, e in SESSION.reviews.items()} == {"alpha.ttl": "open",
                                                                                "beta.ttl": "skipped"}
    entry = json.loads(ui_core.HISTORY_FILE.read_text())[0]
    assert entry["source"] == str(b)


def test_saved_review_is_restored_with_its_decisions(isolated, fixtures):
    """After a restart, a waiting review is re-checked and the fixes accepted before are accepted again."""
    from ontoreview.fixes import FixSession
    from ontoreview.ui import SESSION, restore_review
    src = isolated / "toy_onto.ttl"
    shutil.copy(fixtures / "cdi" / "toy_onto.ttl", src)
    job = ui_core.Settings(source=str(src), output=str(isolated / "docs"))
    sess = FixSession(str(src))
    sess.precheck()
    title = next(x for x in sess.suggestions if x.rule == "OB001" or "title" in x.title.lower())
    sess.accept(title.id, values={"title": "Soil sensing"})
    e = SESSION.add_review(sess, job)
    e["dec"][title.id] = {"opt": 0, "values": {"title": "Soil sensing"}, "text": "", "status": "accepted"}
    SESSION.persist()
    SESSION.reset()                                                  # as after an app restart
    e = SESSION.reviews[str(src.resolve())]
    assert e["session"] is None and e["status"] == "open"
    restore_review(e)
    assert title.id in e["session"].accepted


@pytest.mark.anyio
async def test_picking_another_ontology_clears_the_previous_result(isolated, fixtures):
    """The result panel belongs to the ontology that was built: picking another one empties it."""
    from ontoreview.ui import SESSION
    a, b = isolated / "pizza.ttl", isolated / "colors.ttl"
    shutil.copy(fixtures / "pizza.ttl", a)
    shutil.copy(fixtures / "colors-skos.ttl", b)
    ui_core.Settings(source=str(a), output=str(isolated / "site"), oops="off", cdi=False, si=False).save()
    async with user_simulation(root=build_page) as user:
        await user.open("/")
        await user.should_see("pizza.ttl")
        user.find(marker="run").click()
        for _ in range(150):
            if SESSION.build["last"] is not None and not SESSION.build["running"]:
                break
            await asyncio.sleep(0.1)
        await user.should_see("Terms documented", retries=20)
        user.find(marker="source-clear").click()                       # pick another ontology
        user.find(marker="source").type(str(b)).trigger("keydown.enter")
        await user.should_see("colors.ttl")
        await user.should_see("No build yet", retries=10)
        await user.should_not_see("Terms documented")
