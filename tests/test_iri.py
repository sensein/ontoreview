"""IRI checks (quality_checks/iri, report/iri.py) and the term database. Network is always mocked."""

import asyncio
import json

import pytest
from rdflib import Graph

from ontoreview.config import Config
from ontoreview.quality_checks import iri
from ontoreview.quality_checks.iri import http as iri_http
from ontoreview.quality_checks.iri import validate as iri_validate
from ontoreview.quality_checks.iri.http import iri_issue
from ontoreview.quality_checks.iri.store import TermStore, default_cache_path
from ontoreview.quality_checks.iri.validate import Validator, references

pytestmark = pytest.mark.real_iri

PROV_ALIAS = """\
@prefix ex: <https://example.org/my-ontology#> .
@prefix ap: <http://www.w3.org/ns/prov#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.org/my-ontology> a owl:Ontology ; owl:versionIRI <https://example.org/my-ontology/1.0> .
ex:Document a owl:Class ; rdfs:subClassOf ap:Entity .
ex:document1 a ex:Document ; ap:wasAttributedTo ex:author1 .
ex:author1 a ap:Agent .
ex:Thing a owl:Class ; rdfs:subClassOf <https://unknown.test/vocab#Widget> .
"""
VOCAB = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://vocab.test/> a owl:Ontology .
<https://vocab.test/Entity> a owl:Class ; rdfs:label "Entity" .
<https://vocab.test/Old> a owl:Class ; owl:deprecated true .
<https://vocab.test/rel> a owl:ObjectProperty ; rdfs:label "rel" .
"""


def ev(**kw):
    return Config(evaluation={"iri_network": False, **kw}).evaluation


def test_iri_syntax():
    assert iri_issue("http://example.org/a#B") is None
    assert iri_issue("http://example.org/a B") and iri_issue("example.org/a") and iri_issue("http://%zz.org/")
    assert iri_issue("http:///nohost") == "missing host or embedded credentials"
    assert iri_issue("urn:isbn:123") is None and iri_issue("urn:isbn:123", http_only=True)


def test_alias_prefix_uses_bundled_sqlite_offline():
    g = Graph().parse(data=PROV_ALIAS, format="turtle")
    rep = iri.run_iri_checks(g, ev(), "prov_alias.ttl", "https://example.org/my-ontology#")
    by = {m["metric"]: m for m in rep.metrics}
    assert by["external"]["value"].startswith("4 checked: 3 valid, 1 unverified")
    assert "bundled 3" in by["sources"]["value"] and by["header"]["status"] == "ok"
    assert by["resolves"]["status"] == "skipped"
    [unv] = [i for i in rep.items if i.code == "unverified_external_term"]
    assert unv.affected == ["https://unknown.test/vocab#Widget"] and unv.severity == "info"
    assert "Run #1 recorded" in rep.scope
    runs = iri.recent_runs()
    assert runs[0]["summary"]["statuses"] == {"valid": 3, "unverified": 1} and runs[0]["settings"]["offline"]


def test_references_skip_builtins_and_own_namespaces():
    g = Graph().parse(data=PROV_ALIAS, format="turtle")
    refs = references(g, iri.local_namespaces(g, None))
    assert "http://www.w3.org/ns/prov#Entity" in refs and refs["http://www.w3.org/ns/prov#Entity"] == {"class"}
    assert refs["http://www.w3.org/ns/prov#wasAttributedTo"] == {"property"}
    assert not any(k.startswith(("https://example.org/", "http://www.w3.org/2002/07/owl#")) for k in refs)


def test_own_namespaces_on_the_same_host_but_not_catalogued():
    g = Graph().parse(data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <https://ex.org/onto/ontology> a owl:Ontology .
        <https://ex.org/onto/Building> a owl:Class .
        <https://ex.org/onto/Style#Newari> a owl:NamedIndividual .
        <http://purl.obolibrary.org/obo/go.owl> a owl:Ontology .
        <http://purl.obolibrary.org/obo/BFO_0000001> a owl:Class .""", format="turtle")
    ns = iri.local_namespaces(g, None, catalog=iri.load_catalog())
    assert "https://ex.org/onto/" in ns and "https://ex.org/onto/Style#" in ns
    assert "http://purl.obolibrary.org/obo/" not in ns          # BFO is catalogued: still checked as external


def _seed(tmp_path):
    f = tmp_path / "vocab.ttl"
    f.write_text(VOCAB)
    return iri.add_document(path=f)


def test_add_search_remove(tmp_path):
    res = _seed(tmp_path)
    assert res == {"key": "https://vocab.test/", "source_url": (tmp_path / "vocab.ttl").as_uri(), "terms": 4,
                   "ontology_iris": ["https://vocab.test/"]}
    hits = iri.search_terms("entity")
    assert {h["iri"] for h in hits} >= {"https://vocab.test/Entity", "http://www.w3.org/ns/prov#Entity"}
    assert [h["where"] for h in iri.search_terms("entity", document="https://vocab.test/")] == ["cache"]
    docs = iri.list_documents()
    assert sum(d["where"] == "bundled" for d in docs) == 10 and any(d["key"] == "https://vocab.test/" for d in docs)
    assert iri.remove_document("https://vocab.test/") and not iri.search_terms("vocab.test")
    with pytest.raises(ValueError):
        iri.add_document(url="not a url")


def test_deprecated_and_wrong_type_from_an_added_vocabulary(tmp_path):
    _seed(tmp_path)
    g = Graph().parse(data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <https://me.test/o> a owl:Ontology .
        <https://me.test/o#A> a owl:Class ; rdfs:subClassOf <https://vocab.test/Old>, <https://vocab.test/rel> .
        <https://me.test/o#p> a owl:ObjectProperty ; rdfs:subPropertyOf <https://vocab.test/Entity> .""", format="turtle")
    rep = iri.run_iri_checks(g, ev(), None, "https://me.test/o#")
    codes = {i.code: i for i in rep.items}
    assert codes["deprecated_external_term"].affected == ["https://vocab.test/Old"]
    assert set(codes["external_term_wrong_type"].affected) == {"https://vocab.test/Entity", "https://vocab.test/rel"}
    assert codes["deprecated_external_term"].severity == "warning"


def test_malformed_iri_and_missing_header():
    g = Graph()
    g.parse(data='<http://ex.org/a> <http://ex.org/p> "x" .', format="nt")
    from rdflib import URIRef
    g.add((URIRef("http://ex.org/bad iri"), URIRef("http://ex.org/p"), URIRef("http://ex.org/a")))
    rep = iri.run_iri_checks(g, ev(), None, None)
    codes = {i.code: i for i in rep.items}
    assert codes["invalid_iri"].severity == "error" and codes["invalid_iri"].affected == ["http://ex.org/bad iri"]
    assert codes["no_ontology_header"].severity == "warning"


def test_remote_chain_caches_and_respects_limits(tmp_path, monkeypatch):
    calls = []

    class Fake:
        name = "ols"

        def lookup(self, iri_, roles, timeout=20):
            calls.append(iri_)
            if iri_.endswith("Found"):
                return ({"iri": iri_, "status": "valid", "provider": "ols", "types": [], "labels": [],
                         "deprecated": False, "snapshot": "ols"}, {"provider": "ols", "status": "found"})
            return None, {"provider": "ols", "status": "not_found"}

    monkeypatch.setattr(iri_validate, "download_graph", lambda *a, **k: (_ for _ in ()).throw(ValueError("404")))
    bundle = TermStore(iri.data_file("top_terms.sqlite3"), readonly=True)
    cache = TermStore(tmp_path / "c.sqlite3")
    try:
        v = Validator(bundle, cache, iri.load_catalog(), providers=[Fake()])
        assert v.validate("https://r.test/ns#Found", {"class"})["status"] == "valid"
        statuses = [v.validate(f"https://r.test/ns#Miss{i}", {"class"})["status"] for i in range(5)]
        assert statuses == ["unverified"] * 5
        assert len(calls) == 1 + 3                     # after 3 misses the namespace is not looked up again
        v2 = Validator(bundle, cache, iri.load_catalog(), providers=[Fake()])
        assert v2.validate("https://r.test/ns#Found", {"class"})["snapshot"] == "cache"   # persisted
        v3 = Validator(bundle, cache, iri.load_catalog(), providers=[Fake()], budget=-1)
        assert "budget" in v3.validate("https://other.test/x#Y", {"class"})["detail"]
    finally:
        bundle.close()
        cache.close()


def test_ontology_iri_resolution(monkeypatch):
    ttl = b'@prefix owl: <http://www.w3.org/2002/07/owl#> . <https://me.test/o> a owl:Ontology .'
    monkeypatch.setattr(iri_http, "fetch", lambda url, t, m: ({"http_status": 200, "final_url": url,
                                                               "content_type": "text/turtle"}, ttl))
    assert iri_http.resolve_ontology_iri("https://me.test/o", 5, 1000)["identity"] == "match"
    monkeypatch.setattr(iri_http, "fetch", lambda url, t, m: ({"http_status": 200, "final_url": url,
                                                               "content_type": "text/html"}, b"<html>hi</html>"))
    assert iri_http.resolve_ontology_iri("https://me.test/o", 5, 1000)["status"] == "html_only"


def test_turned_off_and_settings_round_trip():
    from ontoreview import ui_core

    assert iri.check_iris(Graph(), Config(evaluation={"iri_checks": "off"}).evaluation) is None
    s = ui_core.Settings(source="a.ttl", task="check", iri_network=False)
    assert "--offline" in s.cli() and s.evaluation()["iri_network"] is False
    assert "iri_network = false" in s.to_toml()
    assert default_cache_path().name == "iri-cache.sqlite3"      # tests use a private database


def test_cli_terms(tmp_path):
    from typer.testing import CliRunner

    from ontoreview.cli import app

    f = tmp_path / "vocab.ttl"
    f.write_text(VOCAB)
    r = CliRunner().invoke(app, ["terms", "add", str(f)])
    assert r.exit_code == 0 and "4 terms" in r.output
    r = CliRunner().invoke(app, ["terms", "search", "Entity"])
    assert r.exit_code == 0 and "vocab.test" in r.output


@pytest.mark.anyio
async def test_term_database_page(tmp_path, monkeypatch):
    pytest.importorskip("nicegui")
    from nicegui.testing.user_simulation import user_simulation

    from ontoreview import ui_core
    from ontoreview.ui import SESSION, build_page

    monkeypatch.setattr(ui_core, "SETTINGS_FILE", tmp_path / "cfg" / "ui.json")
    monkeypatch.setattr(ui_core, "HISTORY_FILE", tmp_path / "cfg" / "history.json")
    SESSION.reset()
    f = tmp_path / "vocab.ttl"
    f.write_text(VOCAB)
    iri.run_iri_checks(Graph().parse(data=PROV_ALIAS, format="turtle"), ev(), "prov_alias.ttl", None)  # one run
    async with user_simulation(root=build_page) as user:
        await user.open("/terms")
        user.find("Runs").click()
        await user.should_see(marker="term-runs", retries=30)
        user.find("Search").click()
        await user.should_see("Term database")
        user.find(marker="term-search").type("Agent").trigger("keydown.enter")
        await user.should_see(marker="term-results", retries=30)     # table cells are drawn client-side
        await user.should_see("terms", retries=5)
        user.find(marker="term-add-url").type(str(f))           # not a URL: rejected with a message
        user.find(marker="term-add-url-go").click()
        await user.should_see("Could not add it", retries=30)
    iri.add_document(path=f)
    assert json.dumps(iri.list_documents()).count("vocab.test") >= 1
    await asyncio.sleep(0)
