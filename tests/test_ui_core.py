"""The logic behind ontoreview-ui (no NiceGUI needed)."""

import json
import shutil

import pytest

from ontoreview.ui_core import (
    Settings,
    browse,
    describe_source,
    existing_output,
    forget_run,
    issues_text,
    load_history,
    record_run,
    run_task,
    task_kind,
)


@pytest.fixture
def folder(tmp_path, fixtures):
    src = tmp_path / "ontos"
    (src / "vocab").mkdir(parents=True)
    shutil.copy(fixtures / "pizza.ttl", src / "pizza.ttl")
    shutil.copy(fixtures / "colors-skos.ttl", src / "vocab" / "colors.ttl")
    return src


def test_cli_and_overrides_for_a_file(fixtures, tmp_path):
    s = Settings(source=str(fixtures / "pizza.ttl"), output=str(tmp_path / "out"), languages="en, es",
                 competency_questions=str(fixtures / "cq" / "pizza-cq.yaml"), robot="off", oops="off")
    cmd = s.cli()
    assert cmd.startswith("ontoreview build ") and "--lang en,es" in cmd and "--cq " in cmd
    assert "--robot off" in cmd and "--no-oops" in cmd
    ov = s.overrides()
    assert ov["languages"] == ["en", "es"] and ov["evaluation"] == {"robot": "off", "oops": "off", "oops_timeout": 90}
    assert ov["competency_questions"][0].endswith("pizza-cq.yaml")


def test_folder_drops_per_ontology_options(folder, fixtures):
    s = Settings(source=str(folder), competency_questions=str(fixtures / "cq" / "pizza-cq.yaml"),
                 previous_version=str(fixtures / "pizza.ttl"))
    assert s.is_folder and "competency_questions" not in s.overrides() and "previous_version" not in s.overrides()
    assert "--cq" not in s.cli() and s.default_output().endswith("docs")
    assert describe_source(str(folder)) == "Folder with 2 ontologies."


def test_validate():
    assert Settings().validate() == ["Choose an ontology file or a folder of ontologies."]
    assert "not found" in Settings(source="/nope/x.ttl").validate()[0]


def test_toml_roundtrip(fixtures, tmp_path):
    s = Settings(source=str(fixtures / "pizza.ttl"), output=str(tmp_path / "d"), layout="multi",
                 languages="en, pt", base_url="https://w3id.org/x", oops="off", reason=True)
    f = tmp_path / "ontoreview.toml"
    f.write_text(s.to_toml())
    back = Settings.from_toml(f)
    assert (back.source, back.layout, back.languages, back.base_url, back.oops, back.reason) == \
        (s.source, "multi", "en, pt", "https://w3id.org/x", "off", True)
    from ontoreview.config import load_config
    assert load_config(f).layout == "multi"          # the file is a valid ontoreview.toml


@pytest.mark.parametrize("task, page", [("site", "index.html"), ("single", None), ("markdown", "index.md"),
                                        ("myst", "index.md"), ("check", None)])
def test_run_task_file(fixtures, tmp_path, task, page):
    out = tmp_path / ("out.json" if task == "check" else "out.html" if task == "single" else "out")
    res = run_task(Settings(source=str(fixtures / "pizza.ttl"), output=str(out), task=task, separate_runs=False))
    assert res.ok == 1 and res.rows[0].terms > 0
    if page:
        assert (out / page).is_file()
    elif task == "single":
        assert out.is_file()
    else:
        data = json.loads(out.read_text())
        assert "pizza.ttl" in data and "summary" in data["pizza.ttl"]


@pytest.mark.parametrize("task, page", [("site", "index.html"), ("markdown", "index.md"), ("check", None)])
def test_run_task_folder(folder, tmp_path, task, page):
    out = tmp_path / "out"
    res = run_task(Settings(source=str(folder), output=str(out), task=task, separate_runs=False))
    assert res.ok == 2
    if page:
        assert (out / page).is_file() and (out / "vocab" / "colors" / page).is_file()
    else:
        assert set(json.loads((out / "quality.json").read_text())) == {"pizza.ttl", "vocab/colors.ttl"}


def test_history(folder, tmp_path):
    hist = tmp_path / "history.json"
    s = Settings(source=str(folder), output=str(tmp_path / "site"), separate_runs=False)
    res = run_task(s)
    e1 = record_run(s, res, path=hist)
    e2 = record_run(Settings(source="/gone.ttl", output=str(tmp_path / "missing"), task="markdown"), None,
                    "Source not found", path=hist)
    entries = load_history(hist)
    assert [e.id for e in entries] == [e2.id, e1.id]                     # newest first
    assert entries[1].exists and not entries[0].exists and entries[0].failed
    assert entries[1].ok == 2 and entries[1].settings["source"] == str(folder)
    assert [e.id for e in entries if e.matches("site")] == [e1.id]
    assert [e.id for e in entries if e.matches(task="markdown")] == [e2.id]
    forget_run(e2.id, path=hist)
    assert [e.id for e in load_history(hist)] == [e1.id]


def test_existing_output(folder, tmp_path):
    out = tmp_path / "site"
    assert existing_output(out) is None
    run_task(Settings(source=str(folder), output=str(out), separate_runs=False))
    info = existing_output(out)
    assert info["kind"] == "folder" and info["count"] == 2 and info["index"].endswith("index.html")
    run_task(Settings(source=str(folder / "pizza.ttl"), output=str(tmp_path / "one"), separate_runs=False))
    assert existing_output(tmp_path / "one")["kind"] == "single"


def test_browse(folder):
    lst = browse(folder)
    assert lst.dirs == ["vocab"] and lst.files == ["pizza.ttl"] and lst.parent == str(folder.parent.resolve())
    assert browse(folder / "pizza.ttl").path == str(folder.resolve())   # a file lists its folder


def test_settings_persist(tmp_path):
    f = tmp_path / "ui.json"
    Settings(source="x.ttl", task="myst").save(f)
    assert Settings.load(f).task == "myst"
    f.write_text("{broken")
    assert Settings.load(f) == Settings()


def test_safe_relpath_rejects_unsafe_names():
    from ontoreview.ui_core import safe_relpath

    assert str(safe_relpath("onto/sub/pizza.ttl")) == "onto/sub/pizza.ttl"
    assert str(safe_relpath("onto\\win\\a.owl")) == "onto/win/a.owl"
    for bad in ("../etc/passwd.ttl", "a/../../b.ttl", ".hidden/x.ttl", "C:/x.ttl", "notes.txt", "x.exe", ""):
        assert safe_relpath(bad) is None, bad


def test_upload_target_and_source(tmp_path, monkeypatch, fixtures):
    from ontoreview import ui_core

    monkeypatch.setattr(ui_core, "SETTINGS_FILE", tmp_path / "cfg" / "ui.json")
    assert ui_core.upload_target("not-hex!", "a.ttl") is None
    batch = "0123456789abcdef"
    # one file dropped -> that file
    t = ui_core.upload_target(batch, "pizza.ttl")
    t.parent.mkdir(parents=True)
    t.write_bytes((fixtures / "pizza.ttl").read_bytes())
    assert ui_core.upload_source(batch) == str(t)
    # one folder dropped -> that folder
    b2 = "fedcba9876543210"
    for rel in ("myonto/core.ttl", "myonto/vocab/colors.ttl"):
        f = ui_core.upload_target(b2, rel)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("")
    assert ui_core.upload_source(b2).endswith("myonto")
    # several things dropped -> the batch folder
    (ui_core.uploads_dir() / b2 / "other.ttl").write_text("")
    assert ui_core.upload_source(b2) == str(ui_core.uploads_dir() / b2)


def test_config_template_is_valid_and_validator_reports_problems(tmp_path):
    from ontoreview.config import CONFIG_TEMPLATE, load_config, validate_config_text

    text = CONFIG_TEMPLATE.format(source="pizza.ttl")
    assert validate_config_text(text, tmp_path) == []
    (tmp_path / "ontoreview.toml").write_text(text)
    cfg = load_config(tmp_path / "ontoreview.toml")
    assert cfg.source == "pizza.ttl" and cfg.evaluation.robot == "auto" and cfg.evaluation.oops == "auto"
    assert validate_config_text('layout = "wide"')[0].startswith("layout:")
    assert validate_config_text("source = ")[0].startswith("TOML syntax")



def test_compare_versions(fixtures, tmp_path):
    s = Settings(source=str(fixtures / "pizza-v2.ttl"), previous_version=str(fixtures / "pizza.ttl"),
                 task="diff", output=str(tmp_path / "changes.md"))
    assert s.cli().startswith("ontoreview diff ") and "pizza.ttl" in s.cli() and "--format markdown" in s.cli()
    res = run_task(s)
    from ontoreview.ui_core import change_counts

    sm = change_counts(res.changes)
    assert sm == {"added": 1, "removed": 1, "modified": 2}      # modified includes the ontology's version change
    assert (tmp_path / "changes.md").read_text().startswith("# Changelog")
    assert (tmp_path / "changes.json").is_file()
    e = record_run(s, res, path=tmp_path / "h.json")
    assert issues_text(e) == f"{sm['added']} added · {sm['removed']} removed · {sm['modified']} modified"
    assert task_kind("diff") == "diff"


def test_compare_versions_needs_a_previous_file(fixtures, folder):
    assert "Choose the previous version" in " ".join(Settings(source=str(fixtures / "pizza.ttl"), task="diff").validate())
    assert "not a folder" in " ".join(Settings(source=str(folder), task="diff", previous_version=str(fixtures / "pizza.ttl")).validate())


def test_each_run_in_its_own_folder(fixtures, tmp_path):
    from ontoreview.ui_core import export_output, run_config_rows, run_folder

    assert run_folder(tmp_path / "docs", now=0).name.startswith("docs-19")
    one = run_folder(tmp_path / "pizza.html")
    assert one.name == "pizza.html" and one.parent.name.startswith("pizza-")
    s = Settings(source=str(fixtures / "pizza.ttl"), output=str(tmp_path / "docs"), oops="off", cdi=False)
    a, b = run_task(s), run_task(s)
    assert a.output != b.output and a.output.parent == tmp_path           # never overwritten
    for r in (a, b):                                                       # self-contained: standalone copy inside
        assert (r.output / "index.html").is_file() and (r.output / "standalone.html").is_file()
    z = export_output(a.output, tmp_path / "exports")
    import zipfile
    names = zipfile.ZipFile(z).namelist()
    assert f"{a.output.name}/index.html" in names and f"{a.output.name}/standalone.html" in names
    e = record_run(s, a, path=tmp_path / "h.json")
    assert e.output == str(a.output)
    rows = dict(run_config_rows(e.settings))
    assert rows["Task"] == "Website"
    assert rows["Each run in its own folder"] == "on" and rows["OOPS!"] == "off"
    assert export_output(tmp_path / "h.json") == tmp_path / "h.json"        # a single file is exported as is


def test_setup_plan_offers_what_was_found():
    from ontoreview.ui_core import LOCAL_OOPS_URL, Prefs, setup_plan

    base = {"robot_local": "", "docker_installed": True, "docker_running": True, "robot_image": "obolibrary/robot",
            "robot_image_present": False, "oops_container": "", "oops_local_url": LOCAL_OOPS_URL,
            "oops_endpoint": "https://oops.linkeddata.es/rest", "ollama": False, "ollama_url": "http://localhost:11434",
            "ollama_models": [], "cdi_extras": False, "keys": []}
    ids = {s["id"]: s for s in setup_plan(base, Prefs()) if s["kind"] == "action"}
    assert ids["pull_robot"]["default"] and not ids["local_oops"]["default"]
    stopped = setup_plan(base | {"docker_running": False}, Prefs())
    assert not [s for s in stopped if s["kind"] == "action"]
    assert any("not running" in s["label"] for s in stopped)
    local = {s["id"] for s in setup_plan(base | {"robot_local": "/usr/bin/robot"}, Prefs())}
    assert "use_local_robot" in local and "pull_robot" not in local


def test_apply_setup_pulls_robot_and_starts_oops(monkeypatch):
    import ontoreview.quality_checks.robot as robot
    import ontoreview.ui_core as core

    calls = []

    class FakePopen:
        def __init__(self, cmd, **kw):
            calls.append(cmd)
            self.stdout = iter(["done\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(robot, "_docker", lambda: "docker")
    monkeypatch.setattr("subprocess.Popen", FakePopen)
    monkeypatch.setattr(core, "_http_ok", lambda url, timeout=3: True)
    prefs = core.Prefs(robot_mode="local", reasoner="off", ai_priority="hf,api")
    found = {"robot_image": "obolibrary/robot", "oops_container": "", "ollama_url": "http://localhost:11434",
             "ollama_models": ["llama3:8b"], "robot_local": ""}
    log = []
    problems = core.apply_setup({"pull_robot", "local_oops", "use_ollama"}, prefs, found, log.append)
    assert problems == []
    assert ["docker", "pull", "obolibrary/robot"] in calls
    assert any(c[:2] == ["docker", "run"] and core.LOCAL_OOPS_IMAGE in c for c in calls)
    assert prefs.robot_mode == "docker" and prefs.reasoner == "hermit"
    assert prefs.oops_endpoint == core.LOCAL_OOPS_URL
    assert prefs.ai_priority.startswith("ollama,") and prefs.ai_ollama_model == "llama3:8b"


def test_apply_setup_keeps_public_oops_when_local_does_not_answer(monkeypatch):
    import ontoreview.quality_checks.robot as robot
    import ontoreview.ui_core as core

    class FakePopen:
        def __init__(self, cmd, **kw):
            self.stdout = iter([])

        def wait(self):
            return 0

    monkeypatch.setattr(robot, "_docker", lambda: "docker")
    monkeypatch.setattr("subprocess.Popen", FakePopen)
    monkeypatch.setattr(core, "_http_ok", lambda url, timeout=3: False)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    prefs = core.Prefs()
    problems = core.apply_setup({"local_oops"}, prefs, {"oops_container": "Exited (0)"})
    assert prefs.oops_endpoint == core.Prefs.oops_endpoint and "did not answer" in problems[0]


def test_every_docs_format_shows_the_same_check_steps():
    from ontoreview.ui import _plan
    from ontoreview.ui_core import Settings

    plans = {t: _plan(Settings(source="a.ttl", task=t, robot="auto", oops="auto")) for t in
             ("site", "single", "markdown", "myst")}
    keys = {t: [k for k, _ in p] for t, p in plans.items()}
    assert keys["site"] == keys["single"] == keys["markdown"] == keys["myst"]
    assert {"robot", "iri", "ontocheck", "oops"} <= set(keys["markdown"])
    assert plans["myst"][-1] == ("render", "Write MyST files")
    cli = Settings(source="a.ttl", task="markdown", oops="off").cli()
    assert cli.startswith("ontoreview export --format markdown") and "--no-oops" in cli
