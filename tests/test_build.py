import json
import re
import sys
import textwrap

import tomllib
from typer.testing import CliRunner

import ontoreview
from ontoreview.cli import app
from ontoreview.widoco import widoco_to_toml

runner = CliRunner()


def test_single_page_build(fixtures, tmp_path):
    res = ontoreview.build(fixtures / "pizza.ttl", out=tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "<title>Pizza Ontology</title>" in html
    for anchor in ("Pizza", "hasTopping", "Margherita", "classes", "quality", "graph"):
        assert f'id="{anchor}"' in html, anchor
    # self-contained: assets and embedded data exist, no external scripts
    assert (tmp_path / "assets" / "ontoreview.js").exists()
    assert (tmp_path / "assets" / "vendor" / "cytoscape.min.js").exists()
    assert not re.search(r'<script[^>]+src="https?://', html)
    data = (tmp_path / "ontoreview-data.js").read_text()
    payload = json.loads(data[len("window.ONTOREVIEW="):-1])
    assert any(d["label"] == "Pizza" for d in payload["search"])
    assert payload["graph"]["nodes"]
    # JSON-LD for search engines
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    assert json.loads(ld)["@type"] == "DefinedTermSet"
    # publishing artefacts
    for f in ("ontology.ttl", "ontology.owl", "ontology.jsonld", "ontology.nt", ".htaccess",
              "CITATION.cff", "provenance.ttl", "quality.json"):
        assert (tmp_path / f).exists(), f
    assert "RewriteCond %{HTTP_ACCEPT} text/turtle" in (tmp_path / ".htaccess").read_text()
    assert res.report is not None


def test_markdown_is_rendered_and_html_escaped(fixtures, tmp_path):
    src = tmp_path / "x.ttl"
    src.write_text(textwrap.dedent("""
        @prefix : <https://ex.org/x#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <https://ex.org/x> a owl:Ontology .
        :A a owl:Class ; rdfs:label "A <script>alert(1)</script>" ;
           rdfs:comment "Some **bold** text <img src=x onerror=alert(1)>" .
    """))
    ontoreview.build(src, out=tmp_path / "out")
    html = (tmp_path / "out" / "index.html").read_text()
    assert "<strong>bold</strong>" in html
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html


def test_multi_page_and_languages(fixtures, tmp_path):
    ontoreview.build(fixtures / "pizza-v2.ttl", out=tmp_path, layout="multi", languages=["en", "es"],
                  previous_version=str(fixtures / "pizza.ttl"))
    for page in ("index.html", "classes.html", "graph.html", "changelog.html", "quality.html"):
        assert (tmp_path / page).exists(), page
    classes = (tmp_path / "classes.html").read_text()
    assert 'href="datatype-properties.html#hasCalories"' in classes or "datatype-properties.html#" in classes
    es = (tmp_path / "es" / "index.html").read_text()
    assert "Ontología de Pizza" in es and 'href="../assets/ontoreview.css?v=' in es
    assert (tmp_path / "CHANGELOG.md").exists()


def test_linkml_build(fixtures, tmp_path):
    res = ontoreview.build(fixtures / "linkml" / "personinfo.yaml", out=tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "Person Information Model" in html
    assert "generated from a LinkML schema" in html
    assert res.ontology.source_kind == "linkml"


def test_cli_check_exit_codes(fixtures):
    r = runner.invoke(app, ["check", str(fixtures / "pizza.ttl")])
    assert r.exit_code == 1
    r = runner.invoke(app, ["check", str(fixtures / "pizza.ttl"), "--fail-on", "never"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["check", str(fixtures / "colors-skos.ttl"), "--format", "json"])
    assert r.exit_code == 0


def test_cli_diff_and_export(fixtures, tmp_path):
    r = runner.invoke(app, ["diff", str(fixtures / "pizza.ttl"), str(fixtures / "pizza-v2.ttl"), "-f", "json"])
    assert r.exit_code == 0 and '"added"' in r.output
    r = runner.invoke(app, ["export", str(fixtures / "pizza.ttl"), "-f", "myst", "-o", str(tmp_path)])
    assert r.exit_code == 0
    assert "(pizza)=" in (tmp_path / "classes.md").read_text()


def test_config_file(fixtures, tmp_path, monkeypatch):
    (tmp_path / "intro.md").write_text("Hello **intro**")
    (tmp_path / "ontoreview.toml").write_text(textwrap.dedent(f"""
        source = "{(fixtures / 'pizza.ttl').as_posix()}"
        output = "site"
        introduction = "intro.md"
        [metadata]
        title = "From config"
        [[custom_sections]]
        title = "Examples"
        content = "Use it *well*."
    """))
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["build"])
    assert r.exit_code == 0, r.output
    html = (tmp_path / "site" / "index.html").read_text()
    assert "From config" in html and "<strong>intro</strong>" in html and 'id="examples"' in html


def test_plugin(fixtures, tmp_path, monkeypatch):
    plugin = tmp_path / "myplugin.py"
    plugin.write_text(textwrap.dedent("""
        def sections(ontology, config):
            return [{"id": "extra", "title": "Extra", "markdown": "From **plugin**"}]
        def term_blocks(term, ontology):
            return ['<p class="plugged">plugged</p>'] if term.iri.endswith('#Pizza') else []
    """))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("myplugin", None)
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path / "out", plugins=["myplugin"])
    html = (tmp_path / "out" / "index.html").read_text()
    assert 'id="extra"' in html and "<strong>plugin</strong>" in html
    assert html.count('class="plugged"') == 1


def test_theme_override(fixtures, tmp_path):
    theme = tmp_path / "theme" / "templates" / "sections"
    theme.mkdir(parents=True)
    (theme / "namespaces.html").write_text('<section id="namespaces">CUSTOM NS</section>')
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path / "out", theme=str(tmp_path / "theme"))
    assert "CUSTOM NS" in (tmp_path / "out" / "index.html").read_text()


def test_widoco_migration(tmp_path):
    p = tmp_path / "config.properties"
    p.write_text("ontologyTitle=T\nauthors=A;B\nauthorsURI=;https\\://orcid.org/1\nlicenseURI=http\\://x\n")
    data = tomllib.loads(widoco_to_toml(p, "o.ttl"))
    assert data["metadata"]["title"] == "T"
    assert data["metadata"]["creators"] == [{"name": "A"}, {"name": "B", "iri": "https://orcid.org/1"}]


import pytest  # noqa: E402

REAL = ["prov-o.ttl", "foaf.rdf", "org.ttl", "skos.rdf", "dcat.ttl"]


@pytest.mark.parametrize("name", REAL)
def test_real_world_ontologies_build(fixtures, tmp_path, name):
    res = ontoreview.build(fixtures / "real" / name, out=tmp_path)
    assert res.ontology.metadata.title
    assert len(res.ontology.terms) > 20
    assert (tmp_path / "index.html").stat().st_size > 10_000


def test_sidebar_lists_quality_subsections(fixtures, tmp_path):
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path)
    html = (tmp_path / "index.html").read_text()
    nav = html[html.index('class="toc-quality"'):]
    nav = nav[:nav.index("</ol>")]
    assert 'href="#quality-builtin"' in nav and 'href="#quality-oops"' in nav and "OOPS!" in nav
    assert 'id="quality-builtin"' in html and 'id="quality-oops"' in html
    assert 'href=""' not in html[html.index('id="quality"'):]          # tools without a URL get no empty link


def test_provenance_timeline_matches_ttl(fixtures, tmp_path):
    import re

    from rdflib import Graph
    from rdflib.namespace import PROV

    import ontoreview
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, evaluation={"oops": "off", "cdi": "off"})
    html = (tmp_path / "index.html").read_text()
    assert 'class="prov-timeline"' in html and "Documentation generated" in html and "SHA-256" in html
    g = Graph().parse(tmp_path / "provenance.ttl")
    ended = str(next(g.objects(None, PROV.endedAtTime)))
    started = str(next(g.objects(None, PROV.startedAtTime)))
    assert f'datetime="{ended}"' in html and f'datetime="{started}"' in html     # same record, same times
    assert any(str(o).startswith("urn:sha256:") for o in g.objects(None, PROV.used))
    standalone = (tmp_path / "standalone.html").read_text()
    assert 'class="prov-timeline"' in standalone and 'href="provenance.ttl"' not in standalone
    assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC", html)


def test_provenance_dates():
    from ontoreview.publish import _when

    assert _when("2013-04-30")[1] is True
    assert _when("2026-11-21T10:00:00Z")[0].hour == 10
    assert _when("spring 2020") is None and _when("") is None
