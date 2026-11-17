"""Built-in quality rules. Each yields ``(subject_iri | None, message)`` tuples."""

from __future__ import annotations

import re
from collections import defaultdict

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from ..model.axioms import expr_refs
from . import CheckContext, rule

_PROPS = ("object_property", "datatype_property", "property")
LINKML_NS = "https://w3id.org/linkml/"
_XSD = str(XSD)
_LITERAL_TYPES = {str(RDFS.Literal), str(RDF.langString), str(RDF.PlainLiteral), str(RDF.XMLLiteral),
                  str(RDF.HTML), str(RDFS.Datatype)}


def _own(ctx: CheckContext):
    """Terms that belong to this ontology (not imported, not external)."""
    return [t for t in ctx.ontology.terms.values() if not t.imported and not t.external]


# ------------------------------------------------------------------ metadata
@rule("OB001", "Ontology has no title", "warning",
      "Add dcterms:title (or rdfs:label) to the owl:Ontology node.")
def no_title(ctx):
    if not ctx.ontology.metadata.title:
        yield None, "The ontology has no title."


@rule("OB002", "Ontology has no description", "warning",
      "Add dcterms:description or dcterms:abstract so readers know what the ontology is for.")
def no_description(ctx):
    m = ctx.ontology.metadata
    if not (m.description or m.abstract):
        yield None, "The ontology has neither a description nor an abstract."


@rule("OB003", "No license declared", "warning",
      "Declare a license with dcterms:license so others know how they may reuse the ontology.",
      "https://w3id.org/widoco/bestPractices")
def no_license(ctx):
    if not ctx.ontology.metadata.license:
        yield None, "No license is declared (dcterms:license)."


@rule("OB004", "No version information", "info",
      "Add owl:versionInfo and owl:versionIRI to make releases citable and comparable.")
def no_version(ctx):
    m = ctx.ontology.metadata
    if not m.version_info:
        yield None, "No owl:versionInfo."
    if not m.version_iri and ctx.ontology.source_kind != "linkml":
        yield None, "No owl:versionIRI."


@rule("OB005", "No creators", "warning", "Credit the authors with dcterms:creator.")
def no_creator(ctx):
    if not ctx.ontology.metadata.creators:
        yield None, "No creator is declared (dcterms:creator)."


@rule("OB006", "No preferred prefix/namespace", "info",
      "Add vann:preferredNamespacePrefix and vann:preferredNamespaceUri.")
def no_prefix(ctx):
    m = ctx.ontology.metadata
    if not m.preferred_prefix:
        yield None, "No preferred namespace prefix (vann:preferredNamespacePrefix)."


# ------------------------------------------------------------------ terms
@rule("OB010", "Term without a label", "warning",
      "Every term should have a human-readable rdfs:label or skos:prefLabel (OOPS! P08).")
def missing_label(ctx):
    for t in _own(ctx):
        if not t.labels:
            yield t.iri, f"{t.kind_label} `{t.curie or t.iri}` has no label."


@rule("OB011", "Term without a definition", "warning",
      "Every term should have a definition (skos:definition, IAO:0000115 or rdfs:comment) (OOPS! P08).")
def missing_definition(ctx):
    for t in _own(ctx):
        if not t.definition and t.kind != "individual":
            yield t.iri, f"{t.kind_label} “{t.label}” has no definition."


@rule("OB012", "Property without domain", "info",
      "Consider declaring rdfs:domain (OOPS! P11). Ignored when the property is used in class axioms.")
def missing_domain(ctx):
    for t in _own(ctx):
        if t.kind in _PROPS and not t.domain and not t.super_properties and not t.inverse_of \
                and not any(u.role == "used in axioms of" for u in t.used_in):
            yield t.iri, f"Property “{t.label}” has no domain."


@rule("OB013", "Property without range", "info", "Consider declaring rdfs:range (OOPS! P11).")
def missing_range(ctx):
    for t in _own(ctx):
        if t.kind in _PROPS and not t.range and not t.super_properties and not t.inverse_of:
            yield t.iri, f"Property “{t.label}” has no range."


@rule("OB014", "Cycle in class hierarchy", "error",
      "A class is (indirectly) a subclass of itself, which makes the classes equivalent (OOPS! P06).")
def subclass_cycle(ctx):
    supers = {t.iri: [r.iri for r in t.superclasses] for t in ctx.ontology.terms.values()
              if t.kind == "class"}
    reported: set[frozenset] = set()
    for start in supers:
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            for nxt in supers.get(node, []):
                if nxt == start:
                    key = frozenset(path)
                    if key not in reported:
                        reported.add(key)
                        names = " → ".join(ctx.ontology.terms[p].label for p in path + [start])
                        yield start, f"Cycle: {names}"
                elif nxt not in path and len(path) < 50:
                    stack.append((nxt, path + [nxt]))


@rule("OB015", "Undeclared term", "error",
      "A term in the ontology namespace is used but never declared (no rdf:type) (OOPS! P34/P35).")
def undeclared(ctx):
    ns = ctx.ontology.namespace
    if not ns:
        return
    g = ctx.graph
    used: set[str] = set()
    for s, p, o in g:
        for x in (s, p, o):
            if isinstance(x, URIRef) and str(x).startswith(ns) and str(x) != ns:
                used.add(str(x))
    onto_iri = ctx.ontology.metadata.iri
    for iri in sorted(used):
        if iri in ctx.ontology.terms or iri == onto_iri:
            continue
        if (URIRef(iri), RDF.type, None) in g:
            continue
        yield None, f"`{iri}` is used but not declared."


@rule("OB016", "Duplicate labels", "warning",
      "Two or more terms share the same label, which confuses readers and tools.")
def duplicate_labels(ctx):
    by_label = defaultdict(list)
    for t in _own(ctx):
        for lang, labels in t.labels.items():
            for lab in set(labels):
                by_label[(lab.strip().lower(), lang)].append(t)
    for (lab, lang), terms in sorted(by_label.items()):
        if len({t.iri for t in terms}) > 1:
            names = ", ".join(f"`{t.curie or t.iri}`" for t in terms)
            yield terms[0].iri, f"Label “{lab}”{' @' + lang if lang else ''} is used by {names}."


@rule("OB017", "Multiple labels in one language", "warning",
      "A term has more than one rdfs:label/skos:prefLabel in the same language.")
def multiple_labels(ctx):
    for t in _own(ctx):
        for lang, labels in t.labels.items():
            if len(set(labels)) > 1:
                yield t.iri, f"“{t.label}” has {len(set(labels))} labels{' in @' + lang if lang else ' without language tag'}."


@rule("OB018", "Deprecated term without replacement", "info",
      "Deprecated terms should point to their replacement with dcterms:isReplacedBy.")
def deprecated_no_replacement(ctx):
    for t in _own(ctx):
        if t.deprecated and not t.replaced_by:
            yield t.iri, f"“{t.label}” is deprecated but has no replacement."


@rule("OB019", "Inconsistent naming convention", "info",
      "Classes are usually UpperCamelCase and properties lowerCamelCase (OOPS! P22).")
def naming(ctx):
    if ctx.ontology.source_kind == "linkml":
        return  # LinkML uses snake_case slots by convention
    for t in _own(ctx):
        ln = t.local_name
        if not re.match(r"^[A-Za-z]", ln):
            continue
        if t.kind == "class" and not re.match(r"^[A-Z][A-Za-z0-9]*$", ln):
            yield t.iri, f"Class name `{ln}` is not UpperCamelCase."
        elif t.kind in ("object_property", "datatype_property") and not re.match(r"^[a-z][A-Za-z0-9]*$", ln):
            yield t.iri, f"Property name `{ln}` is not lowerCamelCase."


@rule("OB020", "Class both subclass of and disjoint with another", "error",
      "A class that is a subclass of a class it is disjoint with is unsatisfiable.")
def subclass_and_disjoint(ctx):
    for t in ctx.ontology.terms.values():
        if t.kind != "class":
            continue
        sup = {r.iri for r in t.superclasses}
        for d in t.disjoint:
            if d.iri in sup:
                yield t.iri, f"“{t.label}” is a subclass of and disjoint with “{d.label}”."


@rule("OB021", "Transitive property used as functional", "error",
      "In OWL 2 DL a transitive property cannot be functional or inverse functional.")
def transitive_functional(ctx):
    for t in ctx.ontology.terms.values():
        c = set(t.characteristics)
        if "Transitive" in c and c & {"Functional", "Inverse functional"}:
            yield t.iri, f"“{t.label}” is transitive and (inverse) functional."


@rule("OB022", "Self-referencing definition", "warning",
      "A class is declared equivalent to or a subclass of itself (OOPS! P24/P27).")
def self_reference(ctx):
    g = ctx.graph
    for t in ctx.ontology.terms.values():
        s = URIRef(t.iri)
        if t.kind == "class" and ((s, RDFS.subClassOf, s) in g or (s, OWL.equivalentClass, s) in g):
            yield t.iri, f"“{t.label}” refers to itself."
        if t.kind in _PROPS and (s, RDFS.subPropertyOf, s) in g:
            yield t.iri, f"“{t.label}” is a subproperty of itself."


@rule("OB023", "Orphan class", "info",
      "A class with no superclass, no subclasses and no usage is disconnected from the model.")
def orphan(ctx):
    classes = [t for t in _own(ctx) if t.kind == "class"]
    if len(classes) < 3:
        return
    for t in classes:
        if not (t.superclasses or t.subclasses or t.used_in or t.restrictions or t.equivalent
                or t.instances):
            yield t.iri, f"“{t.label}” is not connected to any other term."


@rule("OB024", "Wrong kind of range", "error",
      "Datatype properties must have a datatype range and object properties a class range (OOPS! P31-like).")
def wrong_range(ctx):
    terms = ctx.ontology.terms
    for t in ctx.ontology.terms.values():
        if t.kind not in ("object_property", "datatype_property"):
            continue
        for e in t.range:
            for r in expr_refs(e):
                is_dt = r.iri.startswith(_XSD) or r.iri in _LITERAL_TYPES or (
                    terms.get(r.iri) is not None and terms[r.iri].kind == "datatype")
                is_cls = terms.get(r.iri) is not None and terms[r.iri].kind == "class"
                if t.kind == "datatype_property" and is_cls:
                    yield t.iri, f"Datatype property “{t.label}” has class range “{r.label}”."
                if t.kind == "object_property" and is_dt:
                    yield t.iri, f"Object property “{t.label}” has datatype range “{r.label}”."


@rule("OB025", "Inverse of itself but not symmetric", "warning",
      "A property declared as inverse of itself should be declared symmetric instead (OOPS! P25).")
def inverse_self(ctx):
    g = ctx.graph
    for t in ctx.ontology.terms.values():
        s = URIRef(t.iri)
        if (s, OWL.inverseOf, s) in g and "Symmetric" not in t.characteristics:
            yield t.iri, f"“{t.label}” is declared inverse of itself."


@rule("OB026", "Missing language tags", "info",
      "When some labels carry language tags, all of them should (helps multilingual docs).")
def missing_lang(ctx):
    g = ctx.graph
    has_tagged = any(isinstance(o, Literal) and o.language for o in g.objects(None, RDFS.label))
    if not has_tagged:
        return
    for t in _own(ctx):
        if "" in t.labels:
            yield t.iri, f"“{t.label}” has a label without a language tag."


@rule("OB027", "Term outside the ontology namespace", "info",
      "Declared terms that live in other namespaces are documented as external.")
def external(ctx):
    if ctx.ontology.source_kind == "linkml":
        return  # class_uri/slot_uri/meaning mappings to external IRIs are intentional in LinkML
    for t in ctx.ontology.terms.values():
        if t.external and not t.imported:
            yield t.iri, f"`{t.curie or t.iri}` is declared here but is outside the namespace."


@rule("OB028", "Multiple domains or ranges", "warning",
      "Several rdfs:domain (or range) axioms are interpreted as their intersection, which is often not intended (OOPS! P19).")
def multiple_domain_range(ctx):
    for t in _own(ctx):
        if t.kind not in _PROPS:
            continue
        if len(t.domain) > 1:
            yield t.iri, f"“{t.label}” has {len(t.domain)} domains (intersection semantics)."
        if len(t.range) > 1:
            yield t.iri, f"“{t.label}” has {len(t.range)} ranges (intersection semantics)."
