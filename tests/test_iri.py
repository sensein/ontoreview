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
    assert iri_issue("http:///nohost") == "missing host"
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


# ------------------------------------------------------------------ RFC 3987, releases, expiry
@pytest.mark.parametrize("value", [
    "http://example.org/a#B", "https://ex.org/p?q=1&r=a%20b#frag", "urn:isbn:0451450523", "mailto:a@b.org",
    "http://[2001:db8::1]:8080/x", "http://[v1.fe80::a+en1]/", "http://例え.テスト/パス#断片", "tag:x.org,2026:a/b",
    "http://ex.org/?", "file:///tmp/x.ttl", "http://ex.org/a%41b", "http://ex.org:8080/", "ex+t.a-1:x",
])
def test_rfc3987_valid(value):
    assert iri_issue(value) is None


@pytest.mark.parametrize("value,why", [
    ("http://example.org/a b", "path"), ("example.org/x", "scheme"), ("http:///x", "host"),
    ("http://ex.org:99999/", "port"), ("http://user:pw@ex.org/", "credentials"), ("http://[::zz]/", "IPv6"),
    ("http://ex.org/%zz", "percent"), ("1http://x/", "scheme"), ("http://ex.org/a#b#c", "fragment"),
    ("http://ex.org/a{b}", "path"), ("http://ex.org/", "path"), ("http://ex.org/a\u0000", "path"),
    ("http://ex.org/<x>", "path"), ("http://ex.org:8a/", "port"), ("http://[::1/", "IP literal"),
    ("http://ex.org/q?a b", "query"),
])
def test_rfc3987_invalid(value, why):
    assert why in iri_issue(value)


def _old(store, key, days):
    from datetime import datetime, timedelta, timezone
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with store.db:
        store.db.execute("UPDATE documents SET fetched_at=? WHERE key=?", (when, key))


def test_expired_snapshot_refreshed_or_flagged(tmp_path, monkeypatch):
    f = tmp_path / "vocab.ttl"
    f.write_text(VOCAB)
    bundle = TermStore(iri.data_file("top_terms.sqlite3"), readonly=True)
    cache = TermStore(tmp_path / "c.sqlite3")
    try:
        cache.save("https://vocab.test/", Graph().parse(f), f.as_uri(), f.read_bytes())
        _old(cache, "https://vocab.test/", 90)
        r = Validator(bundle, cache, iri.load_catalog(), offline=True, providers=[]).validate(
            "https://vocab.test/Entity", {"class"})
        assert r["status"] == "valid" and r["stale"] and r["age_days"] > 89          # offline: used, flagged
        assert r["release"]["ontology_iri"] == "https://vocab.test/" and r["release"]["sha256"]
        r = Validator(bundle, cache, iri.load_catalog(), providers=[]).validate("https://vocab.test/Entity", {"class"})
        assert r["snapshot"] == "refreshed" and not r.get("stale")                    # online: re-read the file
        _old(cache, "https://vocab.test/", 90)
        f.unlink()                                                                     # source gone: flagged
        r = Validator(bundle, cache, iri.load_catalog(), providers=[]).validate("https://vocab.test/Entity", {"class"})
        assert r["status"] == "valid" and r["stale"]
        assert not Validator(bundle, cache, iri.load_catalog(), providers=[], max_age_days=0).validate(
            "https://vocab.test/Entity", {"class"}).get("stale")                       # 0 = never expires
    finally:
        bundle.close()
        cache.close()


def test_expired_repository_record_is_asked_again(tmp_path):
    from datetime import datetime, timedelta, timezone

    calls = []

    class Down:
        name = "ols"

        def lookup(self, iri_, roles, timeout=20):
            calls.append(iri_)
            return None, {"provider": "ols", "status": "unavailable"}

    bundle = TermStore(iri.data_file("top_terms.sqlite3"), readonly=True)
    cache = TermStore(tmp_path / "c.sqlite3")
    try:
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        cache.save_repository_term("https://r.test/X", {"class"}, {"iri": "https://r.test/X", "status": "valid",
                                                                  "provider": "ols", "fetched_at": old})
        r = Validator(bundle, cache, iri.load_catalog(), providers=[Down()]).validate("https://r.test/X", {"class"})
        assert calls == ["https://r.test/X"] and r["status"] == "valid" and r["stale"] and "could not refresh" in r["detail"]
    finally:
        bundle.close()
        cache.close()


def test_release_mismatch_with_versioned_import():
    g = Graph().parse(data="""
        @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        <https://me.test/o> a owl:Ontology ; owl:imports <http://www.w3.org/ns/prov-o-20120312> .
        <https://me.test/o#A> a owl:Class ; rdfs:subClassOf <http://www.w3.org/ns/prov#Entity> .""", format="turtle")
    rep = iri.run_iri_checks(g, ev(), None, "https://me.test/o#")
    [mm] = [i for i in rep.items if i.code == "release_mismatch"]
    assert mm.severity == "warning" and mm.affected == ["http://www.w3.org/ns/prov#Entity"]
    assert "prov-o-20130430" in mm.note and "prov-o-20120312" in mm.note
    by = {m["metric"]: m for m in rep.metrics}
    assert "prov-o-20130430" in by["releases"]["value"] and by["freshness"]["status"] in ("ok", "info")


def test_schema_v2_database_is_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
        finished_at TEXT, source TEXT, ontology_iri TEXT, settings TEXT NOT NULL, summary TEXT);
        CREATE TABLE run_results (run_id INTEGER NOT NULL, iri TEXT NOT NULL, roles TEXT NOT NULL,
        status TEXT NOT NULL, source TEXT, detail TEXT, attempts TEXT, PRIMARY KEY(run_id, iri));
        PRAGMA user_version=2;""")
    c.close()
    st = TermStore(path)
    try:
        run = st.start_run(None, None, {})
        st.finish_run(run, [{"iri": "http://x.org/a", "status": "valid", "release": {"version_iri": "v1"},
                             "stale": True}], {})
        [row] = st.run_results(run)
        assert row["release"] == {"version_iri": "v1"} and row["stale"] is True
        assert st.db.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        st.close()


def test_refresh_document_and_cli(tmp_path):
    from typer.testing import CliRunner

    from ontoreview.cli import app

    _seed(tmp_path)
    r = iri.refresh_document("https://vocab.test/")
    assert r["terms"] == 4 and r["changed"] is False
    (tmp_path / "vocab.ttl").write_text(VOCAB + '<https://vocab.test/New> a <http://www.w3.org/2002/07/owl#Class> .\n')
    out = CliRunner().invoke(app, ["terms", "refresh", "https://vocab.test/"])
    assert out.exit_code == 0 and "5 terms (changed)" in out.output
    assert CliRunner().invoke(app, ["terms", "refresh", "https://nope.test/"]).exit_code == 1


def test_groups_per_term_documents_and_names(tmp_path):
    cache = TermStore(default_cache_path())
    try:
        for name in ("E21_Person", "E22_Object"):
            g = Graph().parse(data=f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
                <http://crm.test/crm/{name}> a rdfs:Class ; rdfs:label "{name}" .""", format="turtle")
            cache.save(f"http://crm.test/crm/{name}", g, f"http://crm.test/rdfs/{name}.rdf", b"x")
    finally:
        cache.close()
    _seed(tmp_path)
    groups = {g["group"]: g for g in iri.list_groups() if g["where"] == "cache"}
    crm = groups["http://crm.test/crm/"]
    assert len(crm["documents"]) == 2 and crm["terms"] == 2 and crm["title"] == "crm (crm.test)"
    bundled = {g["title"] for g in iri.list_groups() if g["where"] == "bundled"}
    assert "PROV-O" in bundled and not any(t.startswith("http") for t in bundled)
    hits = iri.search_terms("", document=crm["keys"])
    assert len(hits) == 2 and {h["vocabulary"] for h in hits} == {"crm (crm.test)"}


def test_title_is_stored_for_new_documents(tmp_path):
    f = tmp_path / "v.ttl"
    f.write_text(VOCAB.replace('<https://vocab.test/> a owl:Ontology .',
                               '<https://vocab.test/> a owl:Ontology ; <http://purl.org/dc/terms/title> "Vocab"@de, '
                               '"Test Vocabulary"@en .'))
    iri.add_document(path=f)
    [g] = [g for g in iri.list_groups() if g["group"] == "https://vocab.test/"]
    assert g["title"] == "Test Vocabulary"


def test_build_freezes_iri_provenance_in_the_docs(tmp_path):
    import ontoreview

    src = tmp_path / "o.ttl"
    src.write_text(PROV_ALIAS)
    out = tmp_path / "site"
    ontoreview.build(src, out=out, evaluation={"iri_network": False, "robot": "off", "oops": "off", "ontocheck": "off"})
    rec = json.loads((out / "iri-checks.json").read_text())
    [rel] = [r for r in rec["releases"] if r["version_iri"] == "http://www.w3.org/ns/prov-o-20130430"]
    assert rel["terms"] == 3 and len(rel["sha256"]) == 64 and rel["source"] == "bundle"
    assert {t["iri"] for t in rec["terms"]} >= {"http://www.w3.org/ns/prov#Entity"} and rec["checked_at"]
    prov = Graph().parse(out / "provenance.ttl")
    from rdflib import URIRef
    from rdflib.namespace import PROV
    assert (URIRef("urn:ontoreview:build"), PROV.used, URIRef(rel["version_iri"])) in prov
    html = (out / "index.html").read_text()
    assert "Verified against" in html and "prov-o-20130430" in html
    before = (out / "iri-checks.json").read_text()
    iri.remove_document("http://www.w3.org/ns/prov-o#")      # cache changes later: the built docs do not
    assert (out / "iri-checks.json").read_text() == before
