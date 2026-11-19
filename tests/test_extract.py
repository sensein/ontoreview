from ontoreview.config import Config
from ontoreview.loader import load_ontology
from ontoreview.model.axioms import expr_text
from ontoreview.model.extract import extract

P = "https://example.org/pizza#"


def test_kinds_and_counts(pizza):
    _, o = pizza
    assert o.stats["class"] == 8
    assert o.stats["object_property"] == 4
    assert o.stats["datatype_property"] == 2
    assert o.stats["individual"] == 1
    assert o.namespace == P


def test_metadata(pizza):
    _, o = pizza
    m = o.metadata
    assert m.title == "Pizza Ontology"
    assert m.version_info == "1.2.0"
    assert m.license_label == "CC BY 4.0"
    assert m.preferred_prefix == "pizza"
    alice = m.creators[0]
    assert alice.name == "Alice Example"
    assert alice.orcid and alice.affiliation == "Example University"
    assert any(a.email == "jane@example.org" for a in m.creators)
    assert m.contributors[0].name == "Anonymous Helper"


def test_language_selection(fixtures):
    loaded = load_ontology(fixtures / "pizza.ttl")
    es = extract(loaded, Config(languages=["es", "en"]), "es")
    assert es.terms[P + "Food"].label == "Comida"
    assert es.terms[P + "Food"].definition == "Cualquier cosa comestible."
    assert es.metadata.title == "Ontología de Pizza"


def test_manchester_rendering(pizza):
    _, o = pizza
    pizza_cls = o.terms[P + "Pizza"]
    texts = sorted(expr_text(e) for e in pizza_cls.restrictions)
    assert texts == ["pizza:hasBase some pizza:PizzaBase", "pizza:hasCalories max 1"]
    veg = o.terms[P + "VegetarianPizza"]
    assert expr_text(veg.equivalent[0]) == \
        "pizza:Pizza and (not (pizza:hasTopping some pizza:MeatTopping))"
    cal = o.terms[P + "hasCalories"]
    assert expr_text(cal.range[0]) == "xsd:integer[>= 0]"


def test_relations_and_usage(pizza):
    _, o = pizza
    food = o.terms[P + "Food"]
    assert {r.label for r in food.subclasses} == {"Pizza", "Pizza base", "Pizza topping"}
    pizza_cls = o.terms[P + "Pizza"]
    roles = {(u.role, u.ref.label) for u in pizza_cls.used_in}
    assert ("in domain of", "has topping") in roles
    assert ("used in axioms of", "Vegetarian pizza") in roles
    assert [r.label for r in pizza_cls.instances] == ["Margherita"]
    has_base = o.terms[P + "hasBase"]
    assert has_base.characteristics == ["Functional"]
    assert [r.label for r in has_base.super_properties] == ["has ingredient"]
    assert o.terms[P + "CheeseTopping"].deprecated


def test_class_tree(pizza):
    _, o = pizza
    roots = {n.ref.label for n in o.class_tree}
    assert "Food" in roots and "Pizza" not in roots
    food = next(n for n in o.class_tree if n.ref.label == "Food")
    assert {c.ref.label for c in food.children} == {"Pizza", "Pizza base", "Pizza topping"}


def test_used_prefixes_only(pizza):
    _, o = pizza
    prefixes = dict(o.prefixes)
    assert "pizza" in prefixes and "brick" not in prefixes


def test_overrides(fixtures):
    loaded = load_ontology(fixtures / "pizza.ttl")
    o = extract(loaded, Config(metadata={"title": "Override", "creators": [{"name": "X"}]}))
    assert o.metadata.title == "Override"
    assert [a.name for a in o.metadata.creators] == ["X"]


def test_reasoning(fixtures):
    loaded = load_ontology(fixtures / "pizza.ttl")
    o = extract(loaded, Config(reason=True))
    meat = o.terms[P + "MeatTopping"]
    assert "Food" in {r.label for r in meat.inferred_superclasses}


def test_skos(fixtures):
    loaded = load_ontology(fixtures / "colors-skos.ttl")
    o = extract(loaded, Config())
    assert o.metadata.title == "Colour thesaurus"
    red = next(t for t in o.terms.values() if t.label == "red")
    assert red.kind == "concept"
    assert {r.label for r in red.narrower} == {"dark red", "maroon"}
    assert red.alt_labels == ["crimson"]
    assert "exact match" in red.mappings
    assert o.concept_tree[0].ref.label == "colour"


def test_used_annotation_properties(fixtures):
    loaded = load_ontology(fixtures / "pizza.ttl")
    o = extract(loaded, Config())
    aps = {t.curie: t for t in o.by_kind("annotation_property")}
    assert {"skos:definition", "dcterms:creator", "rdfs:label", "owl:versionInfo"} <= set(aps)
    assert not {"rdfs:subClassOf", "owl:versionIRI", "rdf:type"} & set(aps)  # not annotations
    d = aps["skos:definition"]
    assert d.undeclared and d.external and d.use_count > 1
    assert "annotation_property" in o.kind_trees  # listed in the sidebar

    off = extract(loaded, Config(include_used_annotation_properties=False))
    assert not off.by_kind("annotation_property")
