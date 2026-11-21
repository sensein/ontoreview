"""Suggested fixes: each fixer, the check on a copy, required metadata, versions, patch, provenance,
and AI drafts (stub servers for the OpenAI-compatible and Anthropic APIs, a fake local model)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import DCTERMS, RDFS, SKOS

import ontoreview
from ontoreview.config import AIConfig
from ontoreview.fixes import FixError, FixSession, MissingMetadata, next_version
from ontoreview.fixes.rules import readable

B = """@prefix : <http://example.org/b#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
<http://example.org/b> a owl:Ontology ; dcterms:title "B"@en ; dcterms:description "Test."@en ;
  dcterms:license <https://creativecommons.org/licenses/by/4.0/> ; dcterms:creator "Me" .
:Neuron a owl:Class ; rdfs:label "  neuron  "@en ; skos:definition "a nerve cell."@en .
:Interneuron a owl:Class ; rdfs:label "interneuron"@en ; rdfs:subClassOf :GABAergicInterneuron, :Neuron .
:GABAergicInterneuron a owl:Class ; rdfs:label "GABAergic interneuron"@en ; rdfs:subClassOf :Interneuron .
:Glia a owl:Class ; rdfs:label "glia"@en, "glial cell"@en ; rdfs:subClassOf :Glia .
:hasPart a owl:ObjectProperty ; rdfs:label "has part"@en ; owl:inverseOf :hasPart .
:PyramidalCell a owl:Class ; rdfs:subClassOf :Neuron .
"""
NS = "http://example.org/b#"
VALUES = {"OB001": {"title": "Soil sensing"}, "OB002": {"description": "Soil pH readings."},
          "OB003": {"license": "https://creativecommons.org/licenses/by/4.0/"},
          "OB005": {"creators": "Ada Lovelace https://orcid.org/0000-0002-1825-0097\nGrace Hopper"}}


@pytest.fixture
def b(tmp_path):
    p = tmp_path / "b.ttl"
    p.write_text(B)
    return p


def by_rule(s, rule):
    return next(x for x in s.suggestions if x.rule == rule)


def test_suggestions_and_precheck(b):
    s = FixSession(b)
    rules = {x.rule for x in s.suggestions}
    assert {"FX001", "FX002", "OB010", "OB014", "OB017", "OB022", "OB025"} <= rules
    s.precheck()
    for x in s.suggestions:
        if x.options and x.rule != "OB025":
            assert all(not c["new_findings"] for c in x.checked["options"]), (x.rule, x.checked)
    inv = by_rule(s, "OB025")      # removing owl:inverseOf exposes a missing domain and range: shown, not hidden
    assert not inv.checked["options"][0]["new_findings"] and inv.checked["options"][1]["new_findings"]


def test_apply_writes_new_version_and_never_touches_source(b):
    original = b.read_bytes()
    s = FixSession(b)
    assert s.accept_safe() == 4                       # FX001, FX002, OB010, OB022
    s.accept(by_rule(s, "OB014").id, 0)               # keep the narrower class under the broader one
    r = s.write()
    assert r.path.name == "b-v1.ttl" and b.read_bytes() == original
    g = Graph().parse(r.path)
    n = lambda x: URIRef(NS + x)  # noqa: E731
    assert (n("Neuron"), RDFS.label, Literal("neuron", lang="en")) in g
    assert (n("Neuron"), SKOS.definition, Literal("A nerve cell.", lang="en")) in g
    assert (n("PyramidalCell"), RDFS.label, Literal("pyramidal cell", lang="en")) in g
    assert (n("Glia"), RDFS.subClassOf, n("Glia")) not in g
    assert (n("Interneuron"), RDFS.subClassOf, n("GABAergicInterneuron")) not in g
    assert (n("GABAergicInterneuron"), RDFS.subClassOf, n("Interneuron")) in g
    assert {"OB014", "OB022", "OB010"} <= {x.split()[0] for x in r.fixed} and not r.new_findings
    rec = json.loads(r.record.read_text())
    assert rec["source"]["name"] == "b.ttl" and len(rec["applied"]) == 5 and rec["not_applied"]
    assert all(a["made_by"]["type"] == "rule" for a in rec["applied"])
    # the patch, applied to the source, gives the new file
    g0 = Graph().parse(b)
    g0.update(r.patch.read_text())
    assert isomorphic(g0, g)
    # applying more later writes another file, from the fixed version
    s2 = FixSession(r.path)
    s2.accept(by_rule(s2, "OB025").id, 0)
    assert s2.write().path.name == "b-v2.ttl"


def test_required_metadata(tmp_path):
    p = tmp_path / "a.ttl"
    p.write_text("@prefix : <http://example.org/a#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                 ":X a owl:Class .\n")
    with pytest.raises(MissingMetadata, match="title, description, license, creators"):
        ontoreview.build(p, out=tmp_path / "docs", require_metadata=True, evaluation={"oops": "off"})
    s = FixSession(p)
    assert [x.rule for x in s.required_open()] == ["OB001", "OB002", "OB003", "OB005"]
    with pytest.raises(FixError, match="Fill in"):
        s.accept(by_rule(s, "OB003").id, values={})
    for x in s.required_open():
        s.accept(x.id, values=VALUES[x.rule])
    r = s.write()
    g = Graph().parse(r.path)
    onto = URIRef("http://example.org/a")
    assert (onto, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by/4.0/")) in g
    assert len(list(g.objects(onto, DCTERMS.creator))) == 2
    res = ontoreview.build(r.path, out=tmp_path / "docs", require_metadata=True, evaluation={"oops": "off"})
    meta = res.ontology.metadata
    assert meta.title == "Soil sensing" and meta.license and [c.name for c in meta.creators] == ["Ada Lovelace", "Grace Hopper"]
    assert meta.creators[0].orcid == "https://orcid.org/0000-0002-1825-0097"
    # [metadata] in the config counts as present
    ontoreview.build(p, out=tmp_path / "docs2", require_metadata=True, evaluation={"oops": "off"}, metadata={
        "title": "A", "description": "D", "license": "https://creativecommons.org/licenses/by/4.0/",
        "creators": [{"name": "Me"}]})


def test_fixed_version_provenance(b, tmp_path):
    s = FixSession(b)
    s.accept_safe()
    r = s.write()
    ontoreview.build(r.path, out=tmp_path / "docs", evaluation={"oops": "off"})
    html = (tmp_path / "docs" / "index.html").read_text()
    assert "Fixes applied" in html and "4 fixes applied" in html and "b.ttl" in html
    from rdflib.namespace import PROV
    pg = Graph().parse(tmp_path / "docs" / "provenance.ttl")
    (fixed, orig), = pg.subject_objects(PROV.wasDerivedFrom) if False else [
        x for x in pg.subject_objects(PROV.wasDerivedFrom) if str(x[0]).startswith("urn:sha256:")]
    assert str(orig).startswith("urn:sha256:") and fixed != orig
    assert len(list(pg.subjects(DCTERMS.isPartOf, URIRef("urn:ontoreview:apply-fixes")))) == 4
    # a fixed file edited afterwards no longer claims the record
    r.path.write_text(r.path.read_text() + "\n# edited\n")
    ontoreview.build(r.path, out=tmp_path / "docs2", evaluation={"oops": "off"})
    assert "Fixes applied" not in (tmp_path / "docs2" / "index.html").read_text()


def test_stale_and_versions(b, tmp_path):
    s = FixSession(b)
    s.accept(by_rule(s, "OB022").id)
    b.write_text(B.replace("rdfs:subClassOf :Glia", ""))         # the file changed after the check
    s.graph.remove((URIRef(NS + "Glia"), RDFS.subClassOf, URIRef(NS + "Glia")))
    with pytest.raises(FixError, match="changed since the check"):
        s.write()
    (tmp_path / "x-v1.ttl").write_text("")
    assert next_version(tmp_path / "x.ttl").name == "x-v2.ttl"
    assert next_version(tmp_path / "x-v2.ttl").name == "x-v3.ttl"
    assert next_version(tmp_path / "x.owl").name == "x-v1.owl"


@pytest.mark.parametrize("local, label", [("PyramidalCell", "pyramidal cell"), ("has_part", "has part"),
                                          ("DNASequence", "DNA sequence"), ("CL_0000540", None), ("12345", None)])
def test_readable_names(local, label):
    assert readable(local) == label


def test_manual_has_no_fix(tmp_path):
    p = tmp_path / "m.ttl"
    p.write_text(B + ":Glia owl:disjointWith :Neuron . :Glia rdfs:subClassOf :Neuron .\n")
    s = FixSession(p)
    m = by_rule(s, "OB020")
    assert m.kind == "M" and not m.options
    with pytest.raises(FixError, match="Manual"):
        s.accept(m.id)


# ---------------------------------------------------------------- AI
class Stub(BaseHTTPRequestHandler):
    """Answers OpenAI-compatible chat completions and Anthropic messages with a fixed definition."""
    seen: list = []
    answer = {"definition": "A neuron with a pyramid-shaped cell body.", "reason": "From the parent."}

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.endswith("/chat/completions"):
            out = {"model": "stub-model-2026-01-01",
                   "choices": [{"message": {"content": json.dumps(Stub.answer)}}]}
        else:
            out = {"model": "claude-stub-20260101", "content": [{"type": "tool_use", "name": "answer",
                                                                  "input": Stub.answer}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def stub():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Stub.seen = []
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.parametrize("provider", ["custom", "anthropic"])
def test_ai_definition_draft_and_accept(b, stub, provider, monkeypatch):
    from ontoreview.fixes.ai import ai_suggestions, pick_source, refine_definition
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ai = AIConfig(enabled=True, priority=["api"], api_provider=provider, api_model="m1", api_key="sk-secret",
                  api_base_url=stub + ("/v1" if provider == "custom" else ""))
    src = pick_source(ai)
    s = FixSession(b)
    drafts = ai_suggestions(s, src)
    d = next(x for x in drafts if x.subject == NS + "PyramidalCell")
    assert d.kind == "L" and d.made_by["type"] == "llm" and d.made_by["model"] == "m1"
    assert d.made_by["revision"] in ("stub-model-2026-01-01", "claude-stub-20260101") and d.made_by["prompt_sha256"]
    s.accept(d.id, text="A neuron whose cell body is shaped like a pyramid.")       # edited by the user
    ref = s.add(refine_definition(s, NS + "Neuron", src))
    s.accept(ref.id)
    r = s.write()
    g = Graph().parse(r.path)
    assert (URIRef(NS + "PyramidalCell"), SKOS.definition,
            Literal("A neuron whose cell body is shaped like a pyramid.", lang="en")) in g
    assert (URIRef(NS + "Neuron"), SKOS.definition, Literal("a nerve cell.", lang="en")) not in g
    rec = json.loads(r.record.read_text())
    a = next(x for x in rec["applied"] if x["subject"] == NS + "PyramidalCell")
    assert a["edited"] and a["made_by"]["source"] == "api"
    assert "sk-secret" not in r.record.read_text()                   # keys never in records
    path, headers, body = Stub.seen[0]
    if provider == "anthropic":
        assert path == "/v1/messages" and headers["x-api-key"] == "sk-secret" and body["tool_choice"]["name"] == "answer"
    else:
        assert path == "/v1/chat/completions" and headers["authorization"] == "Bearer sk-secret"
        assert body["response_format"]["type"] == "json_schema"


def test_ai_priority_and_invalid_output(b, stub, monkeypatch):
    from ontoreview.fixes.ai import AIError, draft_definition, pick_source, sources
    ai = AIConfig(enabled=True, priority=["ollama", "hf", "api"], ollama_url="http://127.0.0.1:9",
                  api_provider="custom", api_model="m", api_base_url=stub + "/v1")
    monkeypatch.setattr(sources.HFSource, "available", lambda self: (False, "not installed"))
    assert pick_source(ai).name == "api"                  # Ollama down, HF missing → the API
    with pytest.raises(AIError, match="off"):
        pick_source(AIConfig(enabled=False))
    with pytest.raises(AIError, match="ollama: Ollama is not running"):
        pick_source(AIConfig(enabled=True, priority=["ollama"], ollama_url="http://127.0.0.1:9"))
    Stub.answer = {"wrong": "shape"}
    try:
        with pytest.raises(AIError, match="not usable"):
            draft_definition(FixSession(b), NS + "PyramidalCell", pick_source(ai))
        assert len(Stub.seen) == 2                        # retried once, then discarded
    finally:
        Stub.answer = {"definition": "A neuron with a pyramid-shaped cell body.", "reason": "From the parent."}


def test_hf_source_with_fake_pipeline(b, monkeypatch):
    from ontoreview.fixes.ai import draft_definition
    from ontoreview.fixes.ai.sources import HFSource

    class FakePipe:
        def __call__(self, msgs, **kw):
            return [{"generated_text": msgs + [{"role": "assistant", "content":
                     '<think>hmm</think>{"definition": "A neuron shaped like a pyramid."}'}]}]
    monkeypatch.setattr(HFSource, "_pipe", lambda self: ("text", FakePipe()))
    monkeypatch.setattr(HFSource, "describe", lambda self: {"source": "hf", "model": self.model, "revision": "abc"})
    d = draft_definition(FixSession(b), NS + "PyramidalCell", HFSource("Qwen/Qwen3.5-4B"))
    assert "pyramid" in d.options[0].add[0][2] and d.made_by["model"] == "Qwen/Qwen3.5-4B"


@pytest.mark.parametrize("text, expected", [
    ("Ada Lovelace | 0000-0002-1825-0097 | ada@example.org",
     [{"name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0002-1825-0097", "email": "ada@example.org"}]),
    ("Ada Lovelace <ada@example.org> https://orcid.org/0000-0002-1825-0097\nGrace Hopper",
     [{"name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0002-1825-0097", "email": "ada@example.org"},
      {"name": "Grace Hopper", "orcid": "", "email": ""}]),
    (" | 0000-0002-1825-0097 | \nTim | | tim@example.org", [{"name": "Tim", "orcid": "", "email": "tim@example.org"}]),
])
def test_parse_creators(text, expected):
    from ontoreview.fixes.rules import parse_creators
    assert parse_creators(text) == expected


def test_several_creators_with_orcid_and_email(tmp_path):
    p = tmp_path / "a.ttl"
    p.write_text("@prefix : <http://example.org/a#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
                 ":X a owl:Class .\n")
    s = FixSession(p)
    vals = dict(VALUES, OB005={"creators": "Ada Lovelace | 0000-0002-1825-0097 | ada@example.org\n"
                                           "Grace Hopper |  | grace@example.org\nAlan Turing | |"})
    with pytest.raises(FixError, match="valid ORCID"):
        s.accept(by_rule(s, "OB005").id, values={"creators": "Bob | not-an-orcid |"})
    for x in s.required_open():
        s.accept(x.id, values=vals[x.rule])
    r = s.write()
    res = ontoreview.build(r.path, out=tmp_path / "docs", require_metadata=True, evaluation={"oops": "off"})
    people = [(c.name, c.orcid, c.email) for c in res.ontology.metadata.creators]
    assert sorted(people) == sorted([("Ada Lovelace", "https://orcid.org/0000-0002-1825-0097", "ada@example.org"),
                                     ("Grace Hopper", None, "grace@example.org"), ("Alan Turing", None, None)])


def test_linkml_schema_fixed_into_yaml_copy(fixtures, tmp_path):
    import shutil
    for f in (fixtures / "linkml").iterdir():
        shutil.copy(f, tmp_path / f.name)
    src = tmp_path / "core.yaml"                     # no description, license or creators
    original = src.read_text()
    s = FixSession(src)
    assert {x.rule for x in s.required_open()} == {"OB002", "OB003", "OB005"}
    from ontoreview.fixes.session import linkml_element
    defs = [x for x in s.suggestions if x.rule == "OB011" and x.fields]
    mine = [x for x in defs if s.supported(x)]
    # a definition is written as `description:` of a class/slot/enum of this file; imported terms are not
    assert all(linkml_element(s._linkml_data(), x.subject) for x in mine)
    assert all(not s.supported(x) for x in defs if x not in mine)
    if mine:
        s.accept(mine[0].id, values={mine[0].fields[0].name: "A thing for testing."})
    for x in s.required_open():
        s.accept(x.id, values=dict(VALUES, OB005={"creators": "Ada Lovelace | 0000-0002-1825-0097 | ada@example.org"})[x.rule])
    r = s.write()
    assert r.path.name == "core-v1.yaml" and src.read_text() == original and r.patch.suffix == ".yaml"
    if mine:
        import yaml
        node = yaml.safe_load(r.path.read_text())
        for k in linkml_element(yaml.safe_load(src.read_text()), mine[0].subject):
            node = node[k]
        assert node["description"] == "A thing for testing."
    res = ontoreview.build(r.path, out=tmp_path / "docs", require_metadata=True, evaluation={"oops": "off"})
    m = res.ontology.metadata
    assert m.description == "Soil pH readings." and "creativecommons.org/licenses/by/4.0" in m.license
    (c,) = m.creators
    assert (c.name, c.orcid, c.email) == ("Ada Lovelace", "https://orcid.org/0000-0002-1825-0097", "ada@example.org")


def test_ai_assisted_in_docs_and_provenance(b, stub, tmp_path):
    from rdflib.namespace import PROV  # noqa: F401

    from ontoreview.fixes.ai import ai_suggestions, pick_source
    ai = AIConfig(enabled=True, priority=["api"], api_provider="custom", api_model="m1", api_base_url=stub + "/v1")
    s = FixSession(b)
    d = next(x for x in ai_suggestions(s, pick_source(ai)) if x.subject == NS + "PyramidalCell")
    assert not any(x.rule == "OB011" and x.subject == NS + "PyramidalCell" and x.kind == "U" for x in s.suggestions)
    s.accept(d.id)
    r = s.write()
    assert json.loads(r.record.read_text())["applied"][0]["ai_assisted"] is True
    ontoreview.build(r.path, out=tmp_path / "docs", evaluation={"oops": "off"})
    html = (tmp_path / "docs" / "index.html").read_text()
    assert 'class="ai-tag"' in html and "1 AI-assisted" in html
    pg = Graph().parse(tmp_path / "docs" / "provenance.ttl")
    assert Literal("AI-assisted") in set(pg.objects(None, DCTERMS.type))


def test_other_checks_become_fixes(b):
    """ROBOT, OntoCheck and OOPS! findings reuse the built-in fixers (merged and tagged), the rest are manual."""
    from ontoreview.fixes.external import external_suggestions
    from ontoreview.report.models import ExternalItem, ExternalReport
    s = FixSession(b)
    pyr = NS + "PyramidalCell"
    reports = [
        ExternalReport("ROBOT", "", items=[ExternalItem("missing_label", "Missing label", "warning", affected=[pyr]),
                                           ExternalItem("missing_definition", "Missing definition", "warning",
                                                        affected=[NS + "Interneuron"])]),
        ExternalReport("OntoCheck", "", items=[ExternalItem("checkLabel", "Classes without rdfs:label", "info",
                                                            affected=[pyr])]),
        ExternalReport("OOPS!", "", items=[ExternalItem("P07", "Merging different concepts", "warning",
                                                        description="A class name joins two concepts.",
                                                        affected=[NS + "Glia"])]),
        ExternalReport("Cross-domain interoperability", "", items=[ExternalItem("CDI-A", "x", "info", affected=[pyr])]),
    ]
    added = external_suggestions(s, reports)
    label = next(x for x in s.suggestions if x.rule == "OB010" and x.subject == pyr)
    assert label.reported_by == ["ROBOT · missing_label", "OntoCheck · checkLabel"]     # merged, once
    defn = next(x for x in s.suggestions if x.rule == "OB011" and x.subject == NS + "Interneuron")
    assert "ROBOT · missing_definition" in defn.reported_by
    manual = next(x for x in added if x.rule == "OOPS!:P07")
    assert manual.kind == "M" and "joins two concepts" in manual.explanation and manual.severity == "warning"
    assert not any("CDI" in tag for x in s.suggestions for tag in x.reported_by)       # interoperability: no fixes


LINKML_MINI = """id: https://example.org/mini
name: mini
title: Mini schema
description: A small schema.
license: https://creativecommons.org/licenses/by/4.0/
default_prefix: ex
prefixes:
  ex: https://example.org/mini/
  linkml: https://w3id.org/linkml/
imports:
- linkml:types
default_range: string
classes:
  Sample:
    description: A physical sample.
    attributes:
      sample_code:
        range: string
slots:
  collected_by:
    range: string
"""


def test_linkml_attribute_definition_goes_into_the_yaml(tmp_path):
    import yaml

    from ontoreview.fixes.session import linkml_element
    src = tmp_path / "mini.yaml"
    src.write_text(LINKML_MINI)
    s = FixSession(src)
    code = next(x for x in s.suggestions if x.rule == "OB011" and x.subject.endswith("sample_code"))
    assert linkml_element(s._linkml_data(), code.subject) == ("classes", "Sample", "attributes", "sample_code")
    assert s.yaml_writable(code)
    s.accept(code.id, values={code.fields[0].name: "The lab code of a sample."})
    r = s.write()
    assert r.path.suffix == ".yaml"
    out = yaml.safe_load(r.path.read_text())
    assert out["classes"]["Sample"]["attributes"]["sample_code"]["description"] == "The lab code of a sample."
    assert out["classes"]["Sample"]["attributes"]["sample_code"]["range"] == "string"      # the rest is kept


def test_linkml_fix_without_a_yaml_key_writes_owl(tmp_path):
    """A fix LinkML YAML cannot hold: the OWL version of the schema is written with every fix, plus the
    YAML-expressible part as a patch."""
    from ontoreview.fixes.model import Option, Suggestion
    src = tmp_path / "mini.yaml"
    src.write_text(LINKML_MINI)
    s = FixSession(src)
    iri = next(t for t in s.onto.terms if t.endswith("collected_by"))
    odd = s.add(Suggestion("OB099", iri, "D", "Mark as deprecated", options=[Option("Deprecate", add=[
        (f"<{iri}>", "<http://www.w3.org/2002/07/owl#deprecated>",
         '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>')])]))
    assert s.supported(odd) and not s.yaml_writable(odd)
    d = next(x for x in s.suggestions if x.rule == "OB011" and x.subject == iri)
    s.accept(odd.id)
    s.accept(d.id, values={d.fields[0].name: "Who collected it."})
    r = s.write()
    assert r.path.name == "mini-v1.ttl" and r.patch.name == "mini-v1.patch.ru"
    assert (tmp_path / "mini-v1.patch.yaml").is_file()
    rec = json.loads(r.record.read_text())
    assert rec["converted"].startswith("LinkML schema → OWL")
    from rdflib import Graph, URIRef
    from rdflib.namespace import OWL
    g = Graph().parse(r.path)
    assert (URIRef(iri), OWL.deprecated, None) in g
    assert src.read_text() == LINKML_MINI
