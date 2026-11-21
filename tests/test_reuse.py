"""OB029: terms an ontology re-creates that a standard vocabulary already has (missed reuse)."""

from __future__ import annotations

from ontoreview.build import check
from ontoreview.fixes import FixSession
from ontoreview.quality_checks.reuse import norm

OFF = {k: "off" for k in ("robot", "reasoner", "oops", "ontocheck", "iri_checks", "cdi", "si")}
HEAD = """@prefix : <http://example.org/farm#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
<http://example.org/farm> a owl:Ontology .
"""


def ob029(path):
    _, r = check(str(path), evaluation=OFF)
    return {f.subject: f.message for f in r.findings if f.rule == "OB029"}


def test_norm():
    assert norm("hasBusinessFunction") == norm("has business-function") == "hasbusinessfunction"


def test_recreated_standard_term_is_reported(tmp_path):
    p = tmp_path / "farm.ttl"
    p.write_text(HEAD + ':Sensor a owl:Class ; rdfs:label "sensor"@en .\n')
    found = ob029(p)
    assert "sosa:Sensor" in found["http://example.org/farm#Sensor"]


def test_already_linked_term_is_not_reported(tmp_path):
    p = tmp_path / "farm.ttl"
    p.write_text(HEAD + ':Sensor a owl:Class ; rdfs:label "sensor"@en ; owl:equivalentClass sosa:Sensor .\n')
    assert "http://example.org/farm#Sensor" not in ob029(p)


def test_kind_mismatch_is_reported_not_suggested(tmp_path):
    p = tmp_path / "farm.ttl"           # sosa:observes is a property; here a class with that name
    p.write_text(HEAD + ':Observes a owl:Class ; rdfs:label "observes"@en .\n')
    msg = ob029(p)["http://example.org/farm#Observes"]
    assert "sosa:observes" in msg and "is a property" in msg
    s = FixSession(str(p))
    x = next(x for x in s.suggestions if x.rule == "OB029")
    assert x.kind == "M" and not x.options


def test_fix_options_link_or_reuse(tmp_path):
    p = tmp_path / "farm.ttl"
    p.write_text(HEAD + ':Sensor a owl:Class ; rdfs:label "sensor"@en .\n:Probe rdfs:subClassOf :Sensor .\n')
    s = FixSession(str(p))
    x = next(x for x in s.suggestions if x.rule == "OB029")
    link, reuse = x.options[0], x.options[-1]
    assert "owl#equivalentClass" in link.add[0][1] and "sosa/Sensor" in link.add[0][2]
    assert any("Probe" in a[0] and "sosa/Sensor" in a[2] for a in reuse.add)      # uses are rewritten
    assert not any("rdf-syntax-ns#type" in a[1] for a in reuse.add if "sosa/Sensor" in a[0])  # no redeclaration
    s.accept(x.id, option=0)
    r = s.write()
    assert any(f.startswith("OB029") for f in r.fixed) and not r.new_findings
