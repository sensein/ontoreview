import base64
import re

import ontoreview
from ontoreview.studio import Studio


def _html(tmp_path, fixtures, **kw):
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, **kw)
    return (tmp_path / "index.html").read_text()


def test_default_layout_paper(fixtures, tmp_path):
    html = _html(tmp_path, fixtures)
    # one document header with metadata + downloads, no separate metadata/index sections
    assert 'class="doc-header"' in html and 'class="doc-downloads"' in html
    assert 'id="overview"' in html and 'class="stats"' in html and 'class="index-group' not in html
    # terms listed as a sub-hierarchy in the sidebar
    assert 'class="toc-kind"' in html
    toc = html.split('<main', 1)[0]
    assert 'href="#Pizza"' in toc
    # numbered sections, reference group
    assert re.search(r'<span class="secno">\d+\.1</span>', html)
    assert 'id="reference"' in html


def test_term_index_section_option(fixtures, tmp_path):
    html = _html(tmp_path, fixtures, ui={"term_index": "section"})
    assert 'id="overview"' in html and 'class="index-cols"' in html
    assert 'class="toc-kind"' not in html


def test_ui_options(fixtures, tmp_path):
    html = _html(tmp_path, fixtures, ui={"font": "sans", "width": "normal", "section_numbers": False,
                                         "accent": "#aa0000"})
    assert 'data-font="sans"' in html and 'data-width="normal"' in html and "data-nonumbers" in html
    assert "--link:#aa0000" in html


def test_section_order(fixtures, tmp_path):
    html = _html(tmp_path, fixtures, ui={"section_order": ["quality", "reference", "graph"]})
    main = html.split('<main', 1)[1]
    assert main.index('id="quality"') < main.index('id="classes"') < main.index('id="graph"')


def test_single_file_export(fixtures, tmp_path):
    out = tmp_path / "doc.html"
    ontoreview.build_single_file(fixtures / "pizza.ttl", out)
    html = out.read_text()
    assert not re.search(r'<(script|link)[^>]+(src|href)="(?!data:|https?:|#|mailto:)[^"]*\.(js|css)"', html)
    assert "window.ONTOREVIEW=" in html and "cytoscape" in html
    assert 'href="data:text/turtle;base64,' in html


def test_studio_pick_main_and_build(fixtures, tmp_path):
    st = Studio()
    try:
        files = [{"name": n, "data": base64.b64encode((fixtures / "linkml" / n).read_bytes()).decode()}
                 for n in ("core.yaml", "personinfo.yaml")]
        info = st.build_upload({"files": files})
        assert info["main"] == "personinfo.yaml" and info["terms"] > 20
        body, name = st.export(info["id"])
        assert name == "personinfo.html" and b"Person Information Model" in body
        # path components in uploaded names are ignored
        evil = [{"name": "../../evil.ttl", "data": base64.b64encode((fixtures / "pizza.ttl").read_bytes()).decode()}]
        info2 = st.build_upload({"files": evil})
        assert info2["main"] == "evil.ttl"
        assert not (st.root.parent / "evil.ttl").exists()
    finally:
        st.close()


def test_graph_data_has_vowl_details(tmp_path):
    import json
    from pathlib import Path

    from ontoreview.build import build
    fx = Path(__file__).parent / "fixtures" / "linkml" / "personinfo.yaml"
    build(str(fx), out=str(tmp_path))
    js = (tmp_path / "ontoreview-data.js").read_text()
    data = json.loads(js[len("window.ONTOREVIEW="):-1])
    nodes = {n["data"]["label"]: n["data"] for n in data["graph"]["nodes"]}
    assert any(d["l"] == "birth_date" for d in nodes["Person"]["dprops"])
    assert data["ui"]["notation"] == "vowl"
    assert any(e["data"].get("inv") for e in data["graph"]["edges"] if e["data"]["type"] == "prop")
    html = (tmp_path / "index.html").read_text()
    assert 'id="g-notation"' in html and "legend-vowl" in html


def test_overview_and_quality_summary(fixtures, tmp_path):
    from ontoreview.report.models import ExternalReport, Report

    html = _html(tmp_path, fixtures)
    main = html.split('<main', 1)[1]
    assert main.index('id="overview"') < main.index('id="graph"')
    toc = html.split('<main', 1)[0]
    assert 'toc-label">Terms<' in toc and 'toc-label">Reference<' not in toc
    assert 'quality checks run' in main
    # scores come from tools that declare one; CDI's summary key is "cdi"
    r = Report(external=[ExternalReport("Cross-domain interoperability", "", provenance={
        "summary": {"cdi": 0.326, "interoperable": False, "params": {"theta": 0.5}}})])
    (s,) = r.scores()
    assert s["value"] == 0.326 and s["passed"] is False and s["anchor"] == "quality-cross-domain-interoperability"
    rows = r.check_rows()
    assert rows[0]["anchor"] == "quality-builtin" and rows[1]["count"] == 0


def test_section_order_terms_alias(fixtures, tmp_path):
    html = _html(tmp_path, fixtures, ui={"section_order": ["terms", "graph"]})
    main = html.split('<main', 1)[1]
    assert main.index('id="classes"') < main.index('id="graph"')


def test_graph_links_values_to_their_class(tmp_path):
    """Enum values / individuals and class-typed concepts hang from their class; loose concepts from
    their scheme; property edges are on by default."""
    import json
    from pathlib import Path

    from ontoreview.build import build
    from ontoreview.config import UIConfig
    from ontoreview.loader import load_ontology
    from ontoreview.model.extract import extract
    from ontoreview.config import Config
    from ontoreview.render.data import graph_data

    assert UIConfig().graph_property_edges is True and UIConfig().graph_individuals is True

    fx = Path(__file__).parent / "fixtures" / "linkml" / "personinfo.yaml"
    build(str(fx), out=str(tmp_path / "site"))
    js = (tmp_path / "site" / "ontoreview-data.js").read_text()
    g = json.loads(js[len("window.ONTOREVIEW="):-1])["graph"]
    assert g["values"], "enum values missing from the figure"
    vals = {v["data"]["id"] for v in g["values"]}
    inst = [e["data"] for e in g["edges"] if e["data"]["type"] == "inst"]
    assert vals == {e["target"] for e in inst}      # every value has its rdf:type edge
    assert "enum value, dotted to its class" in (tmp_path / "site" / "index.html").read_text()

    ttl = tmp_path / "c.ttl"
    ttl.write_text("""
@prefix : <http://ex.org/o#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://ex.org/o> a owl:Ontology .
:ConditionType a owl:Class ; rdfs:label "ConditionType" .
:Damaged a skos:Concept , :ConditionType ; skos:prefLabel "Damaged" ; skos:inScheme :Conditions .
:Good a owl:NamedIndividual , :ConditionType ; rdfs:label "Good" .
:Conditions a skos:ConceptScheme ; skos:prefLabel "Conditions" ; skos:hasTopConcept :Loose .
:Loose a skos:Concept ; skos:prefLabel "Loose" ; skos:inScheme :Conditions .
""")
    cfg = Config(source=str(ttl))
    onto = extract(load_ontology(str(ttl)), cfg)
    g = graph_data(onto, lambda r: "#")
    e = {(x["data"]["source"].split("#")[1], x["data"]["target"].split("#")[1], x["data"]["type"],
          x["data"].get("rel")) for x in g["edges"]}
    assert ("ConditionType", "Damaged", "inst", None) in e        # concept typed by a class
    assert ("ConditionType", "Good", "inst", None) in e           # named individual -> value node
    assert ("Conditions", "Loose", "sub", "top concept of") in e  # otherwise from its scheme
    assert not any(t == "Damaged" and s == "Conditions" for s, t, *_ in e)
    assert [v["data"]["label"] for v in g["values"]] == ["Good"]
    assert graph_data(onto, lambda r: "#", individuals=False)["values"] == []
