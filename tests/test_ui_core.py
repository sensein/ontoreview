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
    load_history,
    record_run,
    run_task,
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
    res = run_task(Settings(source=str(fixtures / "pizza.ttl"), output=str(out), task=task))
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
    res = run_task(Settings(source=str(folder), output=str(out), task=task))
    assert res.ok == 2
    if page:
        assert (out / page).is_file() and (out / "vocab" / "colors" / page).is_file()
    else:
        assert set(json.loads((out / "quality.json").read_text())) == {"pizza.ttl", "vocab/colors.ttl"}


def test_history(folder, tmp_path):
    hist = tmp_path / "history.json"
    s = Settings(source=str(folder), output=str(tmp_path / "site"))
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
    run_task(Settings(source=str(folder), output=str(out)))
    info = existing_output(out)
    assert info["kind"] == "folder" and info["count"] == 2 and info["index"].endswith("index.html")
    run_task(Settings(source=str(folder / "pizza.ttl"), output=str(tmp_path / "one")))
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
