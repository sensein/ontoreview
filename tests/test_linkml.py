from ontoreview.linkml import is_linkml_file
from ontoreview.model.axioms import expr_text

PI = "https://w3id.org/example/personinfo/"


def test_detection(fixtures):
    assert is_linkml_file(fixtures / "linkml" / "personinfo.yaml")
    assert not is_linkml_file(fixtures / "pizza.ttl")


def test_schema_metadata(personinfo):
    loaded, o = personinfo
    assert loaded.source_kind == "linkml"
    m = o.metadata
    assert m.title == "Person Information Model"
    assert m.version_info == "0.3.0"
    assert m.license_label.startswith("CC0")
    assert m.preferred_prefix == "personinfo"
    assert "people" in m.keywords


def test_classes_slots_enums_types(personinfo):
    _, o = personinfo
    by_label = {t.label: t for t in o.terms.values()}
    person = by_label["Person"]
    assert person.iri == "http://schema.org/Person"  # class_uri honoured
    assert {r.label for r in person.superclasses} == {"NamedThing", "HasAliases"}  # is_a + mixin
    assert person.alt_labels == ["human being"]
    # imported module (core.yaml) is merged
    assert by_label["NamedThing"].kind == "class"
    assert by_label["id"].kind == "datatype_property"
    # slot range decides property kind
    assert by_label["employed_by"].kind == "object_property"
    assert by_label["employed_by"].deprecated
    assert by_label["age_in_years"].kind == "datatype_property"
    # enum -> class with one-of, permissible values -> individuals
    gender = by_label["GenderType"]
    assert gender.kind == "class"
    assert expr_text(gender.equivalent[0]).startswith("{")
    assert len(gender.instances) == 4
    # custom type -> datatype
    assert by_label["PhoneNumberType"].kind == "datatype"


def test_slot_usage_restrictions(personinfo):
    _, o = personinfo
    person = next(t for t in o.terms.values() if t.label == "Person")
    texts = [expr_text(e) for e in person.restrictions]
    # slot_usage makes primary_email required -> exactly 1, with the pattern facet
    assert any(t.startswith("schema:email exactly 1 xsd:string[pattern") for t in texts), texts
    assert any("age_in_years max 1 xsd:integer[>= 0, <= 999]" in t for t in texts), texts
    org = next(t for t in o.terms.values() if t.label == "Organization")
    assert any("employees only personinfo:Person" in expr_text(e) or "employees only schema:Person" in expr_text(e)
               for e in org.restrictions)


def test_inverse_and_identifier(personinfo):
    _, o = personinfo
    employees = next(t for t in o.terms.values() if t.label == "employees")
    assert [expr_text(e) for e in employees.inverse_of] == ["personinfo:employed_by"]
    ident = next(t for t in o.terms.values() if t.label == "id")
    assert "Functional" in ident.characteristics
