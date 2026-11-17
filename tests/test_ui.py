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
    assert 'id="overview"' not in html
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
