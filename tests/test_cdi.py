"""Cross-domain interoperability: scoring parity with the reference script, reference specs,
the report section, the build record and the app settings. Offline: file and SSSOM references
and a fixed stand-in for the language model."""

import json
import os

import pytest
from rdflib import Graph

import ontoreview
from ontoreview.config import EvaluationConfig
from ontoreview.quality_checks import cdi
from ontoreview.quality_checks.cdi import core
from ontoreview.ui_core import Settings


def fake_levels(text: str) -> list[float]:
    """Longer definitions read as more specific."""
    return [0.1, 0.2, 0.4, 0.2, 0.1] if len(text) > 60 else [0.5, 0.3, 0.1, 0.05, 0.05]


@pytest.fixture
def toy(fixtures):
    d = fixtures / "cdi"
    return d / "toy_onto.ttl", d / "toy_ref.ttl", d / "toy_to_bfo.sssom.tsv"


def _ev(**kw) -> EvaluationConfig:
    return EvaluationConfig(**{"cdi_ontoaligner": "off", **kw})    # deterministic: no matcher model


def test_scores_match_reference_script(toy):
    onto_path, ref, sssom = toy
    onto = core.load_ontology(onto_path)
    r, _, _, corr = core.evaluate(onto, [core.LocalFileSource(ref), core.SSSOMSource(sssom)],
                                  core.CallableBackend(fake_levels), verbose=False)
    # values produced by crossdomain_interoperability.py on the same inputs
    assert (round(r.align, 6), round(r.gen, 6), round(r.cdi, 6)) == (0.689556, 0.384375, 0.493603)
    assert r.n_aligned_entities == 8 and len(corr) == 11
    assert core.cdi_score(0.5, 0.5) == 0.5 and core.cdi_score(0, 0) == 0
    assert core.class_generality([1, 0, 0, 0, 0]) == 1 and core.class_generality([0, 0, 0, 0, 1]) == 0


def test_alignment_only_without_language_model(toy):
    onto_path, ref, _ = toy
    r, *_ = core.evaluate(core.load_ontology(onto_path), [core.LocalFileSource(ref)], None, verbose=False)
    assert r.gen is None and r.cdi is None and not r.interoperable and r.align > 0
    assert r.definition_coverage == 5 / 8


@pytest.mark.parametrize("spec, kind, extra", [
    ("ols", "ols", {"names": None, "prefix": "ols"}),
    ("ols:envo,chebi", "ols", {"names": ["envo", "chebi"]}),
    ("bioportal:NCIT", "bioportal", {"names": ["NCIT"], "prefix": "bioportal"}),
    ("ols@https://service.tib.eu/ts4tib/api", "ols", {"base": "https://service.tib.eu/ts4tib/api",
                                                      "prefix": "ols@service.tib.eu"}),
    ("ontoportal:AGROVOC@https://data.agroportal.lirmm.fr", "bioportal", {"names": ["AGROVOC"],
                                                                        "prefix": "bioportal@data.agroportal.lirmm.fr"}),
    ("https://example.org/ref.owl", "url", {}),
    ("maps.sssom.tsv", "sssom", {}),
    ("ref.ttl", "file", {}),
])
def test_reference_specs(spec, kind, extra):
    ref = cdi.parse_reference(spec)
    assert ref["kind"] == kind
    for k, v in extra.items():
        assert ref[k] == v


def test_given_and_discovered_on_one_repository():
    """A named source (ols:a) must not mark candidates of a discovery source (ols) as given."""
    class Repo(core.ReferenceSource):
        prefix = "ols"

        def __init__(self, names, hits):
            self.given, self.names, self.hits, self._info = names is not None, names, hits, {}

        def correspondences(self, onto):
            return [core.Correspondence(e, f"x:{o}", core.EQ, 1.0, 0, "lexical", f"ols:{o}") for e, o in self.hits]

        def describe(self, ids):
            for oid in ids:
                self._info.setdefault(oid, core.OntologyInfo(oid, "ols", domain="farming" if oid == "ols:c" else "",
                                                              given=self.given))

        def info(self):
            return self._info

    onto = core.OntologyEntities("", (), ["e1", "e2"], ["e1", "e2"], {}, {}, {})
    _, _, table = core.build_reference_set(onto, [Repo(["a"], [("e1", "a")]), Repo(None, [("e1", "b"), ("e2", "c")])],
                                           domains=["farming"], verbose=False)
    assert (table["ols:a"].given, table["ols:b"].given) == (True, False)
    assert table["ols:c"].status == "excluded-same-domain"


def test_report_section(toy):
    onto_path, ref, sssom = toy
    rep = cdi.run_cdi(Graph().parse(onto_path), _ev(cdi_references=[str(ref), str(sssom)], cdi_term_db=False),
                      str(onto_path), backend=core.CallableBackend(fake_levels))
    assert rep.tool == "Cross-domain interoperability" and rep.error is None
    m = {r["metric"]: r for r in rep.metrics}
    assert m["CDI"]["value"].startswith("0.49, not interoperable") and m["CDI"]["status"] == "warn"
    assert m["Align"]["value"].startswith("0.69; 8 of 9") and m["Gen"]["value"].startswith("0.38")
    assert {"file:toy_ref.ttl", "sssom:toy_to_bfo.sssom.tsv"} <= set(m)
    codes = {i.code: i for i in rep.items}
    assert codes["CDI-A"].affected == ["http://example.org/toy/SoilPHReading"]
    assert "2 reference ontologies (2 given, 0 discovered)" in rep.scope
    assert rep.provenance["summary"]["cdi"] == pytest.approx(0.493603, abs=1e-6)


def test_offline_skips_repositories_and_missing_key(toy, monkeypatch):
    onto_path, ref, _ = toy
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    ev = _ev(cdi_references=["ols", "bioportal:NCIT", str(ref)], iri_network=True, cdi_generality=False)
    sources, notes = cdi.build_sources(["bioportal:NCIT"], ev, onto_path.parent, 0)
    assert not sources and "BIOPORTAL_API_KEY" in notes[0]
    rep = cdi.run_cdi(Graph().parse(onto_path), _ev(cdi_references=["ols", str(ref)], iri_network=False,
                                                    cdi_generality=False))
    assert "ols: skipped, network lookups are off" in rep.scope
    assert next(r for r in rep.metrics if r["metric"] == "Gen")["status"] == "skipped"
    assert cdi.run_cdi(Graph().parse(onto_path), _ev(cdi_references=["ols"], iri_network=False,
                                                     cdi_term_db=False)).error


def test_optional_api_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("BIOPORTAL_API_KEY", raising=False)
    monkeypatch.delenv("ONTOPORTAL_API_KEY", raising=False)
    bp, agro = cdi.parse_reference("bioportal:NCIT"), cdi.parse_reference("ontoportal@https://data.agroportal.lirmm.fr")
    assert cdi.api_key(_ev(), bp) == ""                                   # optional: no key, no error
    ev = _ev(cdi_api_keys={"bioportal": "k1", "ontoportal": "k2"})
    assert (cdi.api_key(ev, bp), cdi.api_key(ev, agro)) == ("k1", "k2")
    ev = _ev(cdi_api_keys={"ontoportal": "k2", "bioportal@data.agroportal.lirmm.fr": "k3"})
    assert cdi.api_key(ev, agro) == "k3"
    monkeypatch.setenv("BIOPORTAL_API_KEY", "env")
    assert cdi.api_key(_ev(), bp) == "env" and "env" not in repr(_ev(cdi_api_keys={"bioportal": "secret"}))
    s = Settings(source="x.ttl", cdi=True, cdi_references="bioportal", cdi_bioportal_key="secret")
    assert s.evaluation()["cdi_api_keys"] == {"bioportal": "secret"}
    assert "secret" not in s.cli() and "secret" not in s.to_toml() and "secret" not in repr(s)
    from ontoreview.ui_core import record_run
    hist = tmp_path / "history.json"
    record_run(s, None, "x", path=hist)
    s.save(tmp_path / "settings.json")
    assert "secret" not in hist.read_text() and "secret" not in (tmp_path / "settings.json").read_text()


@pytest.mark.real_cdi
def test_build_writes_record(toy, tmp_path, monkeypatch):
    onto_path, ref, sssom = toy
    monkeypatch.setattr(cdi, "generality_backend", lambda ev: (core.CallableBackend(fake_levels), ""))
    ontoreview.build(onto_path, out=tmp_path, evaluation={"cdi_references": [str(ref), str(sssom)],
                                                          "cdi_ontoaligner": "off"})
    rec = json.loads((tmp_path / "cdi.json").read_text())
    assert rec["summary"]["n_entities"] == 9 and rec["correspondences"] and rec["per_entity"]
    html = (tmp_path / "index.html").read_text()
    assert "Cross-domain interoperability" in html and "CDI score" in html
    assert not (tmp_path / "iri-checks.json").exists()


def test_app_settings(toy):
    _, ref, sssom = toy
    s = Settings(source=str(toy[0]), cdi=True, cdi_references=f"ols:envo,chebi\n{ref}\n\n{sssom}", cdi_domains="soil, farming")
    ev = s.evaluation()
    assert ev["cdi_references"] == ["ols:envo,chebi", str(ref), str(sssom)]
    assert ev["cdi_domains"] == ["soil", "farming"]
    assert "--cdi ols:envo,chebi" in s.cli() and "--cdi-domain soil" in s.cli()
    assert not s.validate()
    assert any("not found" in p for p in Settings(source=str(toy[0]), cdi=True, cdi_references="missing.ttl").validate())
    off = Settings(source=str(toy[0]), cdi=False)
    assert off.evaluation()["cdi"] == "off" and "--no-cdi" in off.cli()
    assert Settings().cdi and Settings().cdi_ontoaligner == "sbert" and EvaluationConfig().cdi == "on"


@pytest.mark.ontoaligner
@pytest.mark.skipif(not os.environ.get("ONTOREVIEW_TEST_ONTOALIGNER"), reason="slow: set ONTOREVIEW_TEST_ONTOALIGNER=1")
@pytest.mark.parametrize("matcher", ["fuzzy", "sbert"])
def test_ontoaligner_matcher(toy, matcher):
    pytest.importorskip("ontoaligner")
    onto_path, ref, _ = toy
    corr = core.OntoAlignerSource(ref, matcher=matcher, threshold=0.5).correspondences(core.load_ontology(onto_path))
    pairs = {(m.source.rsplit("/", 1)[1], m.target.rsplit("/", 1)[1]) for m in corr}
    assert ("Sensor", "Sensor") in pairs
    assert all(m.relation == core.EQ and m.method == f"ontoaligner-{matcher}" for m in corr)


def test_ontoaligner_settings_and_hf_token(monkeypatch):
    s = Settings(source="x.ttl", cdi_ontoaligner="fuzzy", hf_token="hf_secret")
    ev = s.evaluation()
    assert ev["cdi_ontoaligner"] == "fuzzy" and "--cdi-ontoaligner fuzzy" in s.cli()
    assert ev["cdi_hf_token"] == "hf_secret" and "hf_secret" not in s.cli() + s.to_toml() + repr(s)
    assert "cdi_ontoaligner" not in Settings(source="x.ttl").evaluation()        # sbert is the default
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with cdi.hf_token(EvaluationConfig(cdi_hf_token="hf_secret")):
        assert os.environ["HF_TOKEN"] == "hf_secret"
    assert "HF_TOKEN" not in os.environ


def test_term_database_first_grows_and_records(toy):
    """User references are saved to the term database, runs are recorded, and later runs use them."""
    from ontoreview.quality_checks.iri import cache_path
    from ontoreview.quality_checks.iri.store import TermStore

    onto_path, ref, sssom = toy
    g = Graph().parse(onto_path)
    first = cdi.run_cdi(g, _ev(cdi_references=[str(ref), str(sssom)], cdi_generality=False))
    rows = {r["id"]: r for r in first.provenance["per_ontology"]}
    assert "file:toy_ref.ttl" in rows and not any(i.startswith("db:file:") for i in rows)   # no double count
    rel = rows["file:toy_ref.ttl"]["release"]
    assert rel["sha256"] and rel["document"] == ref.resolve().as_uri() and rel["identified_by"] == "content hash"
    checked = {r["id"]: r for r in first.provenance["releases"]}
    assert "version not reported" in checked["file:toy_ref.ttl"]["note"]       # kept, and said so
    assert checked["sssom:toy_to_bfo.sssom.tsv"]["sha256"]
    st = TermStore(cache_path())
    try:
        assert st.document(ref.resolve().as_uri())["sha256"] == rel["sha256"]          # the database grew
        [run] = st.recent_cdi_runs()
        assert run["id"] == first.provenance["run_id"] and run["summary"]["n_entities"] == 9
        assert "cdi_api_keys" not in run["settings"] and "cdi_hf_token" not in run["settings"]
        refs = {r["ontology_id"]: r for r in st.cdi_run_references(run["id"])}
        assert refs["file:toy_ref.ttl"]["release"]["sha256"] == rel["sha256"]
        assert st.cdi_run_correspondences(run["id"])
    finally:
        st.close()
    # later, offline and without naming the file: the stored copy is found in the term database
    later = cdi.run_cdi(g, _ev(cdi_references=["ols"], iri_network=False, cdi_generality=False))
    ids = {r["id"] for r in later.provenance["per_ontology"] if r["status"] == "selected"}
    assert "db:" + ref.resolve().as_uri() in ids and later.error is None


def test_repository_details_from_term_database_first(tmp_path, monkeypatch):
    from ontoreview.quality_checks.cdi import termdb
    from ontoreview.quality_checks.iri.store import TermStore

    st = TermStore(tmp_path / "t.sqlite3")
    try:
        cache = termdb.InfoCache(st, 30)
        src = core.OLSSource(["envo"])
        src.info_cache = cache
        calls = []
        monkeypatch.setattr(src.http, "get_json", lambda url, params=None: calls.append(url) or {
            "title": "Environment Ontology", "domain": "environment", "iri": "http://purl.obolibrary.org/obo/envo.owl",
            "loaded": "2026-11-19T00:08:01"})
        src.describe(["ols:envo"])
        assert len(calls) == 1 and src.releases["ols:envo"]["identified_by"] == "release/load date"
        again = core.OLSSource(["envo"])
        again.info_cache = cache
        monkeypatch.setattr(again.http, "get_json", lambda *a, **k: pytest.fail("asked OLS despite the database"))
        info = again.describe(["ols:envo"])["ols:envo"]
        assert (info.title, info.domain) == ("Environment Ontology", "environment")
        assert again.releases["ols:envo"]["cached"] and "ols:envo" in cache.hits
    finally:
        st.close()


@pytest.mark.parametrize("fields, expected", [
    ({"version_iri": "http://x/1.0", "version": "1.0"}, "version IRI"),
    ({"version": "1.0"}, "version"),
    ({"released": "2026-01-01"}, "release/load date"),
    ({}, "metadata fingerprint"),
])
def test_release_identified_by_what_is_available(fields, expected):
    rel = core.release_record("ols", "x", {"any": "answer"}, **fields)
    assert rel["identified_by"] == expected and rel["retrieved"] and rel["metadata_sha256"]
    assert not {"version_iri", "version", "released"} - set(fields) & set(rel)       # absent stays absent
