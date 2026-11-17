"""Documenting a folder of ontologies: discovery, per-ontology sub-folders, index, export, check."""

import json
import shutil

import pytest
from rdflib import Graph
from typer.testing import CliRunner

from ontoreview.cli import app
from ontoreview.collection import build_collection, export_collection, find_ontologies, slugs_for

runner = CliRunner()


@pytest.fixture
def onto_folder(tmp_path, fixtures):
    """A realistic folder: nested sub-folders, LinkML, non-ontology YAML/JSON, a broken file,
    an unsupported syntax, two files with the same stem, and a sub-folder config."""
    src = tmp_path / "ontologies"
    (src / "vocab").mkdir(parents=True)
    (src / "schemas").mkdir()
    (src / "cq").mkdir()
    shutil.copy(fixtures / "pizza.ttl", src / "pizza.ttl")
    Graph().parse(fixtures / "pizza.ttl").serialize(src / "pizza.owl", format="xml")
    shutil.copy(fixtures / "colors-skos.ttl", src / "vocab" / "colors.ttl")
    shutil.copy(fixtures / "linkml" / "personinfo.yaml", src / "schemas" / "personinfo.yaml")
    shutil.copy(fixtures / "linkml" / "core.yaml", src / "schemas" / "core.yaml")
    shutil.copy(fixtures / "cq" / "pizza-cq.yaml", src / "cq" / "pizza-cq.yaml")  # not an ontology
    (src / "notes.json").write_text('{"not": "json-ld"}')                         # not an ontology
    (src / "broken.ttl").write_text("@prefix : <http://x/> .\n:a :b ")             # parse error
    (src / "legacy.omn").write_text("Prefix: : <http://x/>")                       # unsupported
    (src / "vocab" / "ontoreview.toml").write_text('[metadata]\ntitle = "Colour vocabulary"\n')
    return src


def test_discovery_ignores_non_ontologies(onto_folder):
    files, skipped = find_ontologies(onto_folder)
    rel = sorted(f.relative_to(onto_folder).as_posix() for f in files)
    assert rel == ["broken.ttl", "pizza.owl", "pizza.ttl", "schemas/core.yaml", "schemas/personinfo.yaml",
                   "vocab/colors.ttl"]
    assert [s.name for s in skipped] == ["legacy.omn"]


def test_slugs_mirror_folders_and_disambiguate(onto_folder):
    files, _ = find_ontologies(onto_folder)
    slugs = {f.relative_to(onto_folder).as_posix(): s for f, s in slugs_for(files, onto_folder).items()}
    assert slugs["vocab/colors.ttl"] == "vocab/colors"
    assert slugs["pizza.ttl"] == "pizza-ttl" and slugs["pizza.owl"] == "pizza-owl"
    assert slugs["schemas/personinfo.yaml"] == "schemas/personinfo"


def test_build_collection(onto_folder, tmp_path):
    out = tmp_path / "site"
    res = build_collection(onto_folder, out)
    assert {e.slug for e in res.ok} == {"pizza-ttl", "pizza-owl", "vocab/colors", "schemas/personinfo",
                                        "schemas/core"}
    assert [e.source for e in res.failed] == ["broken.ttl"]   # one bad file does not stop the rest
    assert res.skipped == ["legacy.omn"]
    for e in res.ok:
        assert (out / e.slug / "index.html").is_file()
        assert (out / e.slug / "assets" / "ontoreview.css").is_file()   # each sub-site is self-contained
    colors = next(e for e in res.ok if e.slug == "vocab/colors")
    assert colors.title == "Colour vocabulary"                         # sub-folder ontoreview.toml applied
    index = (out / "index.html").read_text()
    assert 'href="vocab/colors/index.html"' in index and "Colour vocabulary" in index
    assert "broken.ttl" in index and "legacy.omn" in index and '<html lang="en">' in index
    manifest = json.loads((out / "collection.json").read_text())
    assert len(manifest["ontologies"]) == 6 and manifest["skipped"] == ["legacy.omn"]


def test_build_collection_skips_its_own_output(onto_folder):
    out = onto_folder / "docs"
    build_collection(onto_folder, out)
    again = build_collection(onto_folder, out)       # generated ontology.ttl etc. must not be picked up
    assert len(again.entries) == 6


def test_single_file_collection(onto_folder, tmp_path):
    out = tmp_path / "single"
    res = build_collection(onto_folder, out, single_file=True)
    assert (out / "vocab" / "colors" / "index.html").is_file() and len(res.ok) == 5


def test_export_collection(onto_folder, tmp_path):
    out = tmp_path / "md"
    res = export_collection(onto_folder, out)
    assert (out / "vocab" / "colors" / "index.md").is_file()
    assert (out / "pizza-ttl" / "classes.md").is_file()
    index = (out / "index.md").read_text()
    assert "[Colour vocabulary](vocab/colors/index.md)" in index and "broken.ttl" in index
    assert len(res.ok) == 5
    myst = export_collection(onto_folder, tmp_path / "myst", myst=True)
    assert "```{toctree}" in (tmp_path / "myst" / "index.md").read_text() and len(myst.ok) == 5


def test_cli_folder(onto_folder, tmp_path):
    r = runner.invoke(app, ["build", str(onto_folder), "-o", str(tmp_path / "site")])
    assert r.exit_code == 1, r.output                 # broken.ttl -> non-zero, but everything else built
    assert (tmp_path / "site" / "vocab" / "colors" / "index.html").is_file()
    assert "5 of 6" in r.output
    (onto_folder / "broken.ttl").unlink()
    r = runner.invoke(app, ["export", str(onto_folder), "-o", str(tmp_path / "md")])
    assert r.exit_code == 0, r.output and (tmp_path / "md" / "index.md").is_file()
    r = runner.invoke(app, ["check", str(onto_folder), "--fail-on", "never", "--format", "json",
                            "-o", str(tmp_path / "q.json")])
    assert r.exit_code == 0, r.output
    data = json.loads((tmp_path / "q.json").read_text())
    assert "vocab/colors.ttl" in data and "summary" in data["vocab/colors.ttl"]


def test_discovery_skips_earlier_output(onto_folder, tmp_path):
    build_collection(onto_folder, onto_folder / "docs")             # output inside the source folder
    build_collection(onto_folder, onto_folder / "old-site")         # and another, older one
    files, _ = find_ontologies(onto_folder)
    assert len(files) == 6 and not any("docs" in f.parts or "old-site" in f.parts for f in files)
