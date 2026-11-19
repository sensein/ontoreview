"""Turn an rdflib graph into the ontoreview documentation model."""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..config import AgentConfig, Config
from ..loader import LoadedOntology
from ..vocab import (
    ALT_LABEL_PROPS,
    BIBO,
    BUILTIN_NAMESPACES,
    CC,
    CHARACTERISTICS,
    COMMENT_PROPS,
    DC,
    DCAT,
    DCTERMS,
    DEFINITION_PROPS,
    DOAP,
    EXAMPLE_PROPS,
    FOAF,
    LABEL_PROPS,
    NOTE_PROPS,
    PAV,
    PROV,
    REPLACED_BY_PROPS,
    SCHEMA,
    SCHEMA_HTTP,
    SOURCE_PROPS,
    STATUS_PROPS,
    STRUCTURAL_PREDICATES,
    VANN,
    VCARD,
)
from .axioms import ExpressionRenderer, expr_refs, literal_text
from .entities import Agent, Annotation, Expr, Metadata, Ontology, Ref, Term, TreeNode, UsageRef
from .licenses import license_label

log = logging.getLogger(__name__)

LINKML_NS = "https://w3id.org/linkml/"

# Friendly names for well-known predicates shown in "other annotations".
PREDICATE_LABELS = {
    LINKML_NS + "required": "required (LinkML)",
    LINKML_NS + "recommended": "recommended (LinkML)",
    LINKML_NS + "multivalued": "multivalued (LinkML)",
    LINKML_NS + "identifier": "identifier (LinkML)",
    LINKML_NS + "key": "key (LinkML)",
    LINKML_NS + "abstract": "abstract (LinkML)",
    LINKML_NS + "mixin": "mixin (LinkML)",
    LINKML_NS + "mixins": "mixins (LinkML)",
    LINKML_NS + "tree_root": "tree root (LinkML)",
    LINKML_NS + "pattern": "pattern (LinkML)",
    LINKML_NS + "minimum_value": "minimum value (LinkML)",
    LINKML_NS + "maximum_value": "maximum value (LinkML)",
    LINKML_NS + "inlined": "inlined (LinkML)",
    LINKML_NS + "inlined_as_list": "inlined as list (LinkML)",
    LINKML_NS + "ifabsent": "if absent (LinkML)",
    LINKML_NS + "designates_type": "designates type (LinkML)",
    LINKML_NS + "attribute_of": "attribute of (LinkML)",
    LINKML_NS + "permissible_value": "permissible value (LinkML)",
    LINKML_NS + "unit": "unit (LinkML)",
    LINKML_NS + "rank": "rank (LinkML)",
    LINKML_NS + "base": "base type (LinkML)",
}
HIDDEN_PREDICATES = {LINKML_NS + "domain_of", LINKML_NS + "kind", LINKML_NS + "generation_source"}

NOTE_LABELS = {
    "scope_note": "Scope note",
    "editorial_note": "Editorial note",
    "history_note": "History note",
    "change_note": "Change note",
    "note": "Note",
    "usage_note": "Usage note",
}

MAPPING_LABELS = {
    SKOS.exactMatch: "exact match",
    SKOS.closeMatch: "close match",
    SKOS.broadMatch: "broad match",
    SKOS.narrowMatch: "narrow match",
    SKOS.relatedMatch: "related match",
    OWL.sameAs: "same as",
}


def _s(*preds) -> list:
    out = []
    for p in preds:
        if isinstance(p, (list, tuple)):
            out.extend(p)
        else:
            out.append(p)
    return out


META = {
    "title": _s(DCTERMS.title, DC.title, RDFS.label, SCHEMA.name, SCHEMA_HTTP.name, SKOS.prefLabel),
    "subtitle": _s(BIBO.shortTitle, SCHEMA.alternateName, SCHEMA_HTTP.alternateName),
    "abstract": _s(DCTERMS.abstract, BIBO.abstract),
    "description": _s(DCTERMS.description, DC.description, SCHEMA.description,
                      SCHEMA_HTTP.description, RDFS.comment, SKOS.definition),
    "version_info": _s(OWL.versionInfo, SCHEMA.version, SCHEMA_HTTP.version, PAV.version),
    "version_iri": _s(OWL.versionIRI),
    "prior_version": _s(OWL.priorVersion, PAV.previousVersion),
    "issued": _s(DCTERMS.issued, SCHEMA.datePublished, SCHEMA_HTTP.datePublished),
    "created": _s(DCTERMS.created, SCHEMA.dateCreated, SCHEMA_HTTP.dateCreated, PAV.createdOn),
    "modified": _s(DCTERMS.modified, SCHEMA.dateModified, SCHEMA_HTTP.dateModified, PAV.lastUpdateOn),
    "license": _s(DCTERMS.license, CC.license, SCHEMA.license, SCHEMA_HTTP.license),
    "rights": _s(DCTERMS.rights, DC.rights),
    "citation": _s(DCTERMS.bibliographicCitation, SCHEMA.citation, SCHEMA_HTTP.citation),
    "doi": _s(BIBO.doi),
    "preferred_prefix": _s(VANN.preferredNamespacePrefix),
    "preferred_namespace": _s(VANN.preferredNamespaceUri),
    "logo": _s(FOAF.logo, SCHEMA.logo, SCHEMA_HTTP.logo, SCHEMA.image, SCHEMA_HTTP.image, FOAF.depiction),
    "status": _s(BIBO.status, *STATUS_PROPS),
    "homepage": _s(FOAF.homepage, SCHEMA.url, SCHEMA_HTTP.url, DOAP.homepage),
    "repository": _s(SCHEMA.codeRepository, SCHEMA_HTTP.codeRepository, DOAP.repository),
}
META_LISTS = {
    "keywords": _s(SCHEMA.keywords, SCHEMA_HTTP.keywords, DCAT.keyword, DCTERMS.subject),
    "backward_compatible_with": _s(OWL.backwardCompatibleWith),
    "incompatible_with": _s(OWL.incompatibleWith),
    "see_also": _s(RDFS.seeAlso),
    "source": _s(DCTERMS.source, PROV.wasDerivedFrom),
}
AGENTS = {
    "creators": _s(DCTERMS.creator, DC.creator, SCHEMA.creator, SCHEMA_HTTP.creator, SCHEMA.author,
                   SCHEMA_HTTP.author, FOAF.maker, PAV.authoredBy, PAV.createdBy),
    "contributors": _s(DCTERMS.contributor, DC.contributor, SCHEMA.contributor,
                       SCHEMA_HTTP.contributor, PAV.contributedBy),
    "publishers": _s(DCTERMS.publisher, DC.publisher, SCHEMA.publisher, SCHEMA_HTTP.publisher),
    "funders": _s(SCHEMA.funder, SCHEMA_HTTP.funder, FOAF.fundedBy),
}
META_PREDICATES = {p for ps in (*META.values(), *META_LISTS.values(), *AGENTS.values()) for p in ps}
META_PREDICATES |= {RDF.type, OWL.imports}

_KIND_TYPES = [
    (OWL.ObjectProperty, "object_property"),
    (OWL.DatatypeProperty, "datatype_property"),
    (OWL.AnnotationProperty, "annotation_property"),
    (OWL.Class, "class"),
    (RDFS.Class, "class"),
    (OWL.DeprecatedClass, "class"),
    (RDFS.Datatype, "datatype"),
    (OWL.DeprecatedProperty, "property"),
    (RDF.Property, "property"),
    (SKOS.ConceptScheme, "concept_scheme"),
    (SKOS.Concept, "concept"),
    (OWL.NamedIndividual, "individual"),
]
# OWL 2 built-in annotation properties (OWL 2 Structural Specification §5.5).
BUILTIN_ANNOTATION_PROPERTIES = {
    RDFS.label, RDFS.comment, RDFS.seeAlso, RDFS.isDefinedBy, OWL.deprecated, OWL.versionInfo,
    OWL.priorVersion, OWL.backwardCompatibleWith, OWL.incompatibleWith,
}
_PROPERTY_KINDS = {"object_property", "datatype_property", "property", "annotation_property"}


def _is_builtin(iri: str) -> bool:
    return iri.startswith(BUILTIN_NAMESPACES)


def local_name(iri: str) -> str:
    m = re.search(r"[#/:]([^#/:]+)/?$", iri)
    return m.group(1) if m else iri


def _anchorize(text: str) -> str:
    a = re.sub(r"[^A-Za-z0-9_\-.]", "_", text).strip("_")
    return a or "term"


class Extractor:
    def __init__(self, loaded: LoadedOntology, config: Config, lang: str | None = None):
        self.loaded = loaded
        self.config = config
        self.main: Graph = loaded.graph
        self.g: Graph = loaded.full_graph
        self.lang = lang or (config.languages[0] if config.languages else "en")
        self.lang_prefs = [self.lang] + [x for x in (config.languages or []) if x != self.lang]
        if "en" not in self.lang_prefs:
            self.lang_prefs.append("en")
        self.terms: dict[str, Term] = {}
        self._prefixes = self._collect_prefixes()
        self.label_props = [self._iri(x) for x in config.label_properties] + LABEL_PROPS
        self.definition_props = [self._iri(x) for x in config.definition_properties] + \
            DEFINITION_PROPS[:-1] + self._auto_definition_props() + DEFINITION_PROPS[-1:]
        self.renderer = ExpressionRenderer(self.g, self.ref, self.curie_or_iri)
        self._anchors: set[str] = set()

    # ------------------------------------------------------------------ helpers
    def _iri(self, curie_or_iri: str) -> URIRef:
        if "://" in curie_or_iri:
            return URIRef(curie_or_iri)
        prefix, _, local = curie_or_iri.partition(":")
        for p, n in self.g.namespaces():
            if p == prefix:
                return URIRef(str(n) + local)
        return URIRef(curie_or_iri)

    def _auto_definition_props(self) -> list[URIRef]:
        """Ontology-specific ``*:definition`` annotation properties (e.g. prov:definition)."""
        known = set(DEFINITION_PROPS)
        out = []
        for p in set(self.g.predicates()):
            if p in known or not isinstance(p, URIRef):
                continue
            if local_name(str(p)).lower() in ("definition", "definitions"):
                out.append(p)
        return sorted(out)

    def _collect_prefixes(self) -> list[tuple[str, str]]:
        preferred = None
        for o in self.g.objects(None, VANN.preferredNamespacePrefix):
            preferred = str(o)
            break
        preferred = self.config.metadata.preferred_prefix or preferred
        named = {str(n): p for p, n in self.g.namespaces() if p and str(n)}
        out: dict[str, str] = {}
        for p, n in self.g.namespaces():
            n = str(n)
            if not n:
                continue
            if not p:
                if n in named:
                    continue
                taken = dict(self.g.namespaces())
                if preferred and preferred not in taken:
                    p = preferred
                else:
                    seg = re.sub(r"[^A-Za-z0-9]", "", n.rstrip("#/").rsplit("/", 1)[-1]).lower()
                    p = seg if seg and seg[0].isalpha() and seg not in taken and len(seg) <= 12 else ""
            out.setdefault(p, n)
        return sorted(out.items(), key=lambda x: -len(x[1]))

    def curie(self, iri: str) -> str | None:
        for prefix, ns in self._prefixes:
            if iri.startswith(ns):
                local = iri[len(ns):]
                if local and re.fullmatch(r"[A-Za-z0-9_\-.%]*", local):
                    return f"{prefix}:{local}"
        return None

    def curie_or_iri(self, iri: str) -> str:
        return self.curie(iri) or iri

    def pick(self, values: Iterable) -> str | None:
        lits = [v for v in values if isinstance(v, Literal)]
        if not lits:
            vals = list(values) if not isinstance(values, list) else values
            return str(vals[0]) if vals else None
        for lang in self.lang_prefs:
            for v in lits:
                if v.language == lang:
                    return str(v)
        for v in lits:
            if not v.language:
                return str(v)
        return str(lits[0])

    def first(self, s, preds: list, graph: Graph | None = None) -> str | None:
        g = graph or self.g
        for p in preds:
            vals = list(g.objects(s, p))
            if vals:
                return self.pick(vals)
        return None

    def label_of(self, iri) -> str | None:
        return self.first(iri, self.label_props)

    def ref(self, iri) -> Ref:
        iri_s = str(iri)
        t = self.terms.get(iri_s)
        if t is not None:
            return t.ref()
        label = self.label_of(URIRef(iri_s)) or self.curie(iri_s) or local_name(iri_s)
        return Ref(iri_s, label, self.curie(iri_s), False, None, None)

    def expr(self, node) -> Expr:
        return self.renderer.render(node)

    # ------------------------------------------------------------- namespace
    def detect_namespace(self, onto: URIRef | None, declared: list[str]) -> str | None:
        ns = self.config.metadata.preferred_namespace
        if ns:
            return ns
        if onto is not None:
            v = self.g.value(onto, VANN.preferredNamespaceUri)
            if v:
                return str(v)
        counts = Counter()
        for iri in declared:
            m = re.match(r"^(.*[#/])[^#/]+$", iri)
            if m:
                counts[m.group(1)] += 1
        if onto is not None:
            o = str(onto)
            for cand in (o + "#", o + "/", o, o.rstrip("#/") + "#", o.rstrip("#/") + "/"):
                if counts.get(cand):
                    return cand
        return counts.most_common(1)[0][0] if counts else None

    # -------------------------------------------------------------- kinds
    def kind_of(self, s: URIRef, class_iris: set[str]) -> str | None:
        types = set(self.g.objects(s, RDF.type))
        for t, kind in _KIND_TYPES:
            if t in types:
                if kind == "property":
                    # characterise plain rdf:Property by declared characteristics
                    if types & {OWL.TransitiveProperty, OWL.SymmetricProperty,
                                OWL.InverseFunctionalProperty}:
                        return "object_property"
                if kind == "individual" and types & {OWL.Class, RDFS.Class}:
                    return "class"
                return kind
        if types & set(CHARACTERISTICS):
            return "object_property"
        if any(str(t) in class_iris for t in types):
            return "individual"
        return None

    # -------------------------------------------------------------- main
    def extract(self) -> Ontology:
        g, cfg = self.g, self.config
        onto = self._ontology_node()
        main_subjects = {str(s) for s in self.main.subjects() if isinstance(s, URIRef)}

        class_iris = {
            str(s) for t in (OWL.Class, RDFS.Class) for s in g.subjects(RDF.type, t)
            if isinstance(s, URIRef)
        }
        candidates: dict[str, str] = {}
        for s in set(g.subjects(RDF.type, None)):
            if not isinstance(s, URIRef):
                continue
            s_str = str(s)
            if _is_builtin(s_str) or (onto is not None and s == onto):
                continue
            kind = self.kind_of(s, class_iris)
            if kind is None:
                continue
            candidates[s_str] = kind

        namespace = self.detect_namespace(onto, [i for i in candidates if i in main_subjects])

        for iri, kind in candidates.items():
            imported = iri not in main_subjects
            if imported and not cfg.include_imported:
                continue
            if kind == "individual" and not cfg.include_individuals:
                continue
            if kind == "annotation_property" and not cfg.include_annotation_properties:
                continue
            external = bool(namespace) and not iri.startswith(namespace)
            if external and not cfg.include_external and not imported:
                continue
            ln = local_name(iri)
            t = Term(
                iri=iri, kind=kind, anchor=self._unique_anchor(ln), curie=self.curie(iri),
                local_name=ln, label=ln, external=external, imported=imported,
            )
            self.terms[iri] = t

        if cfg.include_annotation_properties and cfg.include_used_annotation_properties:
            self._add_used_annotation_properties(onto, namespace, set(candidates))

        for t in self.terms.values():
            self._fill_common(t)
        for t in self.terms.values():
            if t.kind == "class":
                self._fill_class(t)
            elif t.kind in _PROPERTY_KINDS:
                self._fill_property(t)
            elif t.kind == "individual":
                self._fill_individual(t)
            elif t.kind in ("concept", "concept_scheme"):
                self._fill_skos(t)
        if cfg.reason:
            self._infer()
        self._usage()

        meta = self.extract_metadata(onto)
        if namespace and not meta.preferred_namespace:
            meta.preferred_namespace = namespace
        if namespace and not meta.preferred_prefix:
            for p, n in self._prefixes:
                if n == namespace:
                    meta.preferred_prefix = p
                    break

        ontology = Ontology(
            metadata=meta,
            namespace=namespace,
            terms=self.terms,
            prefixes=self._used_prefixes(),
            source_kind=self.loaded.source_kind,
            language=self.lang,
        )
        ontology.class_tree = self._tree("class", "subclasses", "superclasses")
        ontology.property_tree = self._tree(
            ("object_property", "datatype_property", "property"), "sub_properties", "super_properties"
        )
        ontology.concept_tree = self._tree("concept", "narrower", "broader")
        for kind in ontology.kinds_present():
            if kind == "class":
                ontology.kind_trees[kind] = ontology.class_tree
            elif kind == "concept":
                ontology.kind_trees[kind] = ontology.concept_tree
            elif kind in _PROPERTY_KINDS:
                ontology.kind_trees[kind] = self._tree(kind, "sub_properties", "super_properties")
            else:
                ontology.kind_trees[kind] = [TreeNode(t.ref()) for t in ontology.by_kind(kind)]
        ontology.stats = {k: len(ontology.by_kind(k)) for k in ontology.kinds_present()}
        ontology.stats["triples"] = len(self.main)
        return ontology

    def _used_prefixes(self) -> list[tuple[str, str]]:
        stems: set[str] = set()
        for triple in self.main:
            for x in triple:
                if isinstance(x, URIRef):
                    m = re.match(r"^(.*[#/:])", str(x))
                    stems.add(m.group(1) if m else str(x))
                elif isinstance(x, Literal) and x.datatype is not None:
                    stems.add(str(x.datatype).rsplit("#", 1)[0] + "#")
        used = [(p, n) for p, n in self._prefixes if any(st.startswith(n) for st in stems)]
        return sorted(used, key=lambda x: x[0])

    def _ontology_node(self) -> URIRef | None:
        """The owl:Ontology (or skos:ConceptScheme) node carrying the most metadata."""
        for t in (OWL.Ontology, SKOS.ConceptScheme):
            nodes = [s for s in self.main.subjects(RDF.type, t) if isinstance(s, URIRef)]
            if nodes:
                return max(nodes, key=lambda n: (len(list(self.main.predicate_objects(n))), str(n)))
        return None

    def _unique_anchor(self, base: str) -> str:
        a = _anchorize(base)
        cand, i = a, 2
        while cand in self._anchors or cand in RESERVED_ANCHORS:
            cand, i = f"{a}-{i}", i + 1
        self._anchors.add(cand)
        return cand

    # -------------------------------------------------------------- fillers
    def _lits_by_lang(self, s, preds) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        for p in preds:
            for o in self.g.objects(s, p):
                if isinstance(o, Literal):
                    out[o.language or ""].append(str(o))
        return dict(out)

    def _fill_common(self, t: Term) -> None:
        g = self.g
        s = URIRef(t.iri)
        t.labels = self._lits_by_lang(s, self.label_props)
        t.label = self.label_of(s) or t.local_name
        defs_by_lang: dict[str, str] = {}
        def_prop = None
        for p in self.definition_props:
            vals = [o for o in g.objects(s, p) if isinstance(o, Literal)]
            if vals:
                def_prop = p
                for v in vals:
                    defs_by_lang.setdefault(v.language or "", str(v))
                t.definition = self.pick(vals)
                break
        t.definitions = defs_by_lang
        t.comments = [
            str(o) for p in COMMENT_PROPS for o in g.objects(s, p)
            if isinstance(o, Literal) and not (p == def_prop and str(o) == t.definition)
            and (not o.language or o.language in self.lang_prefs)
        ]
        if def_prop == RDFS.comment:
            t.comments = [c for c in t.comments if c != t.definition]
        t.alt_labels = sorted({str(o) for p in ALT_LABEL_PROPS for o in g.objects(s, p)})
        t.examples = [str(o) for p in EXAMPLE_PROPS for o in g.objects(s, p)]
        for p, key in NOTE_PROPS.items():
            vals = [str(o) for o in g.objects(s, p)]
            if vals:
                t.notes.setdefault(NOTE_LABELS[key], []).extend(vals)
        t.see_also = [self.expr(o) for o in g.objects(s, RDFS.seeAlso)]
        t.is_defined_by = [self.ref(o) for o in g.objects(s, RDFS.isDefinedBy) if isinstance(o, URIRef)]
        t.source = [self.expr(o) for p in SOURCE_PROPS for o in g.objects(s, p)]
        dep = g.value(s, OWL.deprecated)
        t.deprecated = bool(dep is not None and str(dep).lower() in ("true", "1")) or bool(
            set(g.objects(s, RDF.type)) & {OWL.DeprecatedClass, OWL.DeprecatedProperty}
        )
        t.replaced_by = [self.ref(o) for p in REPLACED_BY_PROPS for o in g.objects(s, p)
                         if isinstance(o, URIRef)]
        t.status = self.first(s, STATUS_PROPS)
        for p, label in MAPPING_LABELS.items():
            vals = [self.ref(o) for o in g.objects(s, p) if isinstance(o, URIRef) and o != s]
            if vals:
                t.mappings[label] = vals
        # remaining annotations
        by_pred: dict[URIRef, list[Expr]] = defaultdict(list)
        for p, o in g.predicate_objects(s):
            if p in STRUCTURAL_PREDICATES or p in MAPPING_LABELS or str(p) in HIDDEN_PREDICATES:
                continue
            if isinstance(o, BNode) or (p == def_prop) or p in self.label_props:
                continue
            if t.kind == "individual" and self._is_assertion_predicate(p):
                continue
            if isinstance(o, Literal) and o.language and o.language not in self.lang_prefs:
                continue
            by_pred[p].append(self.expr(o) if isinstance(o, URIRef) else _lit_expr(o))
        for p, vals in by_pred.items():
            pref = self.ref(p)
            nice = PREDICATE_LABELS.get(str(p))
            if nice:
                pref = Ref(pref.iri, nice, pref.curie, pref.internal, pref.anchor, pref.kind)
            t.annotations.append(Annotation(pref, vals))
        t.annotations.sort(key=lambda a: a.prop.label.lower())

    def _add_used_annotation_properties(self, onto: URIRef | None, namespace: str | None,
                                        typed: set[str]) -> None:
        """List annotation properties used on documented terms or the ontology header but not
        declared in the input (``skos:definition``, ``dcterms:creator``, ``rdfs:label`` …), so the
        docs show every annotation property in play, not only the declared ones."""
        subjects = [URIRef(i) for i in self.terms] + ([onto] if onto is not None else [])
        uses: dict[URIRef, set] = defaultdict(set)
        for s in subjects:
            for p in self.main.predicates(s, None):
                uses[p].add(s)
        for p, users in uses.items():
            iri = str(p)
            if iri in self.terms or iri in typed or iri in HIDDEN_PREDICATES:
                continue
            if _is_builtin(iri) and p not in BUILTIN_ANNOTATION_PROPERTIES:
                continue  # rdf:type, rdfs:subClassOf, owl:versionIRI … are not annotations
            types = set(self.g.objects(p, RDF.type))
            if types & {OWL.ObjectProperty, OWL.DatatypeProperty}:
                continue  # assertions on individuals, documented as facts
            ln = local_name(iri)
            self.terms[iri] = Term(
                iri=iri, kind="annotation_property", anchor=self._unique_anchor(ln),
                curie=self.curie(iri), local_name=ln, label=ln,
                external=not (namespace and iri.startswith(namespace)),
                imported=OWL.AnnotationProperty in types,
                undeclared=OWL.AnnotationProperty not in types, use_count=len(users),
            )

    def _is_assertion_predicate(self, p) -> bool:
        types = set(self.g.objects(p, RDF.type))
        return bool(types & {OWL.ObjectProperty, OWL.DatatypeProperty})

    def _fill_class(self, t: Term) -> None:
        g, s = self.g, URIRef(t.iri)
        for o in g.objects(s, RDFS.subClassOf):
            if isinstance(o, URIRef):
                if o != OWL.Thing and str(o) != t.iri:
                    t.superclasses.append(self.ref(o))
            else:
                t.restrictions.append(self.expr(o))
        for sub in g.subjects(RDFS.subClassOf, s):
            if isinstance(sub, URIRef) and str(sub) != t.iri:
                t.subclasses.append(self.ref(sub))
        for o in set(g.objects(s, OWL.equivalentClass)) | set(g.subjects(OWL.equivalentClass, s)):
            if o != s:
                t.equivalent.append(self.expr(o))
        disj = {o for o in g.objects(s, OWL.disjointWith)} | {o for o in g.subjects(OWL.disjointWith, s)}
        for ax in g.subjects(RDF.type, OWL.AllDisjointClasses):
            members = list(self.renderer._list(g.value(ax, OWL.members)))
            if s in members:
                disj |= {m for m in members if m != s}
        t.disjoint = [self.ref(o) for o in disj if isinstance(o, URIRef)]
        for lst in g.objects(s, OWL.disjointUnionOf):
            t.disjoint_union.append(self.renderer._join(self.renderer._list(lst), "or", 0))
        for lst in g.objects(s, OWL.hasKey):
            items = self.renderer._list(lst)
            expr: Expr = []
            for i, p in enumerate(items):
                if i:
                    expr.append(("punct", ", "))
                expr += self.expr(p)
            t.keys.append(expr)
        t.instances = [self.ref(i) for i in g.subjects(RDF.type, s) if isinstance(i, URIRef)]
        _sort_refs(t, "superclasses", "subclasses", "disjoint", "instances")

    def _fill_property(self, t: Term) -> None:
        g, s = self.g, URIRef(t.iri)
        t.domain = [self.expr(o) for o in g.objects(s, RDFS.domain)]
        t.range = [self.expr(o) for o in g.objects(s, RDFS.range)]
        if not t.domain:
            t.domain = [self.expr(o) for o in g.objects(s, SCHEMA.domainIncludes)] + [
                self.expr(o) for o in g.objects(s, SCHEMA_HTTP.domainIncludes)]
        if not t.range:
            t.range = [self.expr(o) for o in g.objects(s, SCHEMA.rangeIncludes)] + [
                self.expr(o) for o in g.objects(s, SCHEMA_HTTP.rangeIncludes)]
        types = set(g.objects(s, RDF.type))
        t.characteristics = [label for cls, label in CHARACTERISTICS.items() if cls in types]
        inv = set(g.objects(s, OWL.inverseOf)) | set(g.subjects(OWL.inverseOf, s))
        t.inverse_of = [self.expr(o) for o in inv if o != s or (s, OWL.inverseOf, s) in g]
        t.super_properties = [self.ref(o) for o in g.objects(s, RDFS.subPropertyOf)
                              if isinstance(o, URIRef) and o != s]
        t.sub_properties = [self.ref(o) for o in g.subjects(RDFS.subPropertyOf, s)
                            if isinstance(o, URIRef) and o != s]
        eq = set(g.objects(s, OWL.equivalentProperty)) | set(g.subjects(OWL.equivalentProperty, s))
        t.equivalent_properties = [self.ref(o) for o in eq if isinstance(o, URIRef) and o != s]
        dis = set(g.objects(s, OWL.propertyDisjointWith)) | set(g.subjects(OWL.propertyDisjointWith, s))
        t.disjoint_properties = [self.ref(o) for o in dis if isinstance(o, URIRef)]
        t.chains = [self.renderer.chain(o) for o in g.objects(s, OWL.propertyChainAxiom)]
        _sort_refs(t, "super_properties", "sub_properties")

    def _fill_individual(self, t: Term) -> None:
        g, s = self.g, URIRef(t.iri)
        t.types = [self.expr(o) for o in g.objects(s, RDF.type) if o != OWL.NamedIndividual]
        for p, o in g.predicate_objects(s):
            if p in STRUCTURAL_PREDICATES or not self._is_assertion_predicate(p):
                continue
            t.facts.append((self.ref(p), self.expr(o)))
        t.facts.sort(key=lambda f: f[0].label.lower())
        t.same_as = [self.ref(o) for o in g.objects(s, OWL.sameAs) if isinstance(o, URIRef)]

    def _fill_skos(self, t: Term) -> None:
        g, s = self.g, URIRef(t.iri)
        broader = set(g.objects(s, SKOS.broader)) | set(g.subjects(SKOS.narrower, s))
        narrower = set(g.objects(s, SKOS.narrower)) | set(g.subjects(SKOS.broader, s))
        t.broader = [self.ref(o) for o in broader if isinstance(o, URIRef)]
        t.narrower = [self.ref(o) for o in narrower if isinstance(o, URIRef)]
        rel = set(g.objects(s, SKOS.related)) | set(g.subjects(SKOS.related, s))
        t.related = [self.ref(o) for o in rel if isinstance(o, URIRef)]
        t.in_scheme = [self.ref(o) for o in g.objects(s, SKOS.inScheme) if isinstance(o, URIRef)]
        if t.kind == "concept_scheme":
            tops = set(g.objects(s, SKOS.hasTopConcept)) | set(g.subjects(SKOS.topConceptOf, s))
            t.top_concepts = [self.ref(o) for o in tops if isinstance(o, URIRef)]
        _sort_refs(t, "broader", "narrower", "related", "top_concepts")

    def _infer(self) -> None:
        try:
            import owlrl
        except ImportError:
            log.warning("reason=true requires the 'owlrl' package: pip install 'ontoreview[reason]'")
            return
        closure = Graph()
        closure += self.g
        owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(closure)
        for t in self.terms.values():
            if t.kind != "class":
                continue
            asserted = {r.iri for r in t.superclasses}
            for o in closure.objects(URIRef(t.iri), RDFS.subClassOf):
                if isinstance(o, URIRef) and str(o) != t.iri and str(o) not in asserted \
                        and not _is_builtin(str(o)):
                    t.inferred_superclasses.append(self.ref(o))
            t.inferred_superclasses.sort(key=lambda r: r.label.lower())

    def _usage(self) -> None:
        def add(target: str, role: str, ref: Ref) -> None:
            term = self.terms.get(target)
            if term is None or term.iri == ref.iri:
                return
            if any(u.role == role and u.ref.iri == ref.iri for u in term.used_in):
                return
            term.used_in.append(UsageRef(role, ref))

        for t in list(self.terms.values()):
            r = t.ref()
            for e in t.domain:
                for x in expr_refs(e):
                    add(x.iri, "in domain of", r)
            for e in t.range:
                for x in expr_refs(e):
                    add(x.iri, "in range of", r)
            for e in t.restrictions + t.equivalent:
                for x in expr_refs(e):
                    add(x.iri, "used in axioms of", r)
            for _p, e in t.facts:
                for x in expr_refs(e):
                    add(x.iri, "value of a property of", r)
        for t in self.terms.values():
            t.used_in.sort(key=lambda u: (u.role, u.ref.label.lower()))

    def _tree(self, kinds, child_attr: str, parent_attr: str) -> list[TreeNode]:
        kinds = (kinds,) if isinstance(kinds, str) else kinds
        members = {iri: t for iri, t in self.terms.items() if t.kind in kinds}

        def build(t: Term, path: set[str]) -> TreeNode:
            node = TreeNode(t.ref())
            for c in getattr(t, child_attr):
                if c.iri in members and c.iri not in path:
                    node.children.append(build(members[c.iri], path | {c.iri}))
            node.children.sort(key=lambda n: n.ref.label.lower())
            return node

        roots = [
            t for t in members.values()
            if not any(p.iri in members and p.iri != t.iri for p in getattr(t, parent_attr))
        ]
        # members only reachable through cycles: add them as roots so nothing is lost
        reached: set[str] = set()

        def mark(n: TreeNode) -> None:
            reached.add(n.ref.iri)
            for c in n.children:
                mark(c)

        nodes = [build(t, {t.iri}) for t in roots]
        for n in nodes:
            mark(n)
        for t in members.values():
            if t.iri not in reached:
                n = build(t, {t.iri})
                mark(n)
                nodes.append(n)
        return sorted(nodes, key=lambda n: n.ref.label.lower())

    # -------------------------------------------------------------- metadata
    def _agent(self, node) -> Agent:
        g = self.g
        if isinstance(node, Literal):
            text = str(node)
            m = re.match(r"^\s*(.+?)\s*<([^>]+@[^>]+)>\s*$", text)
            if m:
                return Agent(name=m.group(1), email=m.group(2))
            return Agent(name=text)
        name = self.first(node, [FOAF.name, SCHEMA.name, SCHEMA_HTTP.name, RDFS.label, VCARD.fn,
                                 SCHEMA.legalName])
        if not name:
            given = self.first(node, [FOAF.givenName, SCHEMA.givenName, SCHEMA_HTTP.givenName])
            family = self.first(node, [FOAF.familyName, SCHEMA.familyName, SCHEMA_HTTP.familyName])
            name = " ".join(x for x in (given, family) if x) or None
        iri = str(node) if isinstance(node, URIRef) else None
        if not name:
            name = local_name(iri) if iri and "orcid.org" not in iri else (iri or "Unknown")
        email = self.first(node, [FOAF.mbox, SCHEMA.email, SCHEMA_HTTP.email, VCARD.hasEmail])
        if email and email.startswith("mailto:"):
            email = email[7:]
        orcid = iri if iri and "orcid.org" in iri else None
        aff_node = None
        for p in (SCHEMA.affiliation, SCHEMA_HTTP.affiliation, FOAF.member, VCARD["organization-name"]):
            aff_node = g.value(node, p)
            if aff_node is not None:
                break
        affiliation = None
        if aff_node is not None:
            affiliation = str(aff_node) if isinstance(aff_node, Literal) else (
                self.first(aff_node, [FOAF.name, SCHEMA.name, SCHEMA_HTTP.name, RDFS.label]) or str(aff_node))
        homepage = self.first(node, [FOAF.homepage, SCHEMA.url, SCHEMA_HTTP.url])
        return Agent(name=name, iri=iri, email=email, orcid=orcid, affiliation=affiliation,
                     homepage=homepage)

    def extract_metadata(self, onto: URIRef | None) -> Metadata:
        m = Metadata(iri=str(onto) if onto is not None else None)
        g = self.g
        if onto is not None:
            for field_name, preds in META.items():
                setattr(m, field_name, self.first(onto, preds, self.main))
            for field_name, preds in META_LISTS.items():
                vals: list[str] = []
                for p in preds:
                    vals += [str(o) for o in self.main.objects(onto, p)]
                setattr(m, field_name, sorted(set(vals)))
            for field_name, preds in AGENTS.items():
                agents: list[Agent] = []
                seen: set[str] = set()
                for p in preds:
                    for o in self.main.objects(onto, p):
                        a = self._agent(o)
                        key = (a.iri or a.name).lower()
                        if key not in seen:
                            seen.add(key)
                            agents.append(a)
                setattr(m, field_name, agents)
            m.imports = [self.ref(o) for o in self.main.objects(onto, OWL.imports)]
            ident = [str(o) for o in self.main.objects(onto, DCTERMS.identifier)]
            if not m.doi:
                m.doi = next((i for i in ident if "doi.org/" in i or i.startswith("10.")), None)
            if m.description and m.abstract == m.description:
                m.abstract = None
            # leftover ontology annotations
            by_pred: dict = defaultdict(list)
            for p, o in self.main.predicate_objects(onto):
                if p in META_PREDICATES or str(p) in HIDDEN_PREDICATES or isinstance(o, BNode):
                    continue
                if p in (DCTERMS.identifier,):
                    pass
                if isinstance(o, Literal) and o.language and o.language not in self.lang_prefs:
                    continue
                by_pred[p].append(self.expr(o) if isinstance(o, URIRef) else _lit_expr(o))
            m.other = sorted((Annotation(self.ref(p), v) for p, v in by_pred.items()),
                             key=lambda a: a.prop.label.lower())
        self._apply_overrides(m)
        if m.license and not m.license_label:
            m.license_label = license_label(m.license)
        if m.doi and m.doi.startswith("10."):
            m.doi = "https://doi.org/" + m.doi
        del g
        return m

    def _apply_overrides(self, m: Metadata) -> None:
        ov = self.config.metadata
        for name, value in ov.model_dump(exclude_none=True).items():
            if name in ("creators", "contributors", "publishers", "funders"):
                agents = [AgentConfig.model_validate(a) for a in value]
                setattr(m, name, [
                    Agent(name=a.name, iri=a.iri, email=a.email, affiliation=a.affiliation,
                          orcid=a.iri if a.iri and "orcid.org" in a.iri else None)
                    for a in agents
                ])
            else:
                setattr(m, name, value)


RESERVED_ANCHORS = {
    "introduction", "metadata", "overview", "graph", "namespaces", "terms", "classes",
    "object-properties", "datatype-properties", "properties", "annotation-properties",
    "datatypes", "individuals", "concepts", "concept-schemes", "changelog", "quality",
    "provenance", "citation", "serializations", "top", "references", "search",
}


def _lit_expr(o: Literal) -> Expr:
    text = _plain(o)
    if o.datatype == XSD.anyURI or re.fullmatch(r"https?://\S+", text):
        return [("url", text)]
    return [("lit", text)]


def _plain(o: Literal) -> str:
    if o.datatype == XSD.boolean:
        return str(o).lower()
    return str(o)


def _sort_refs(t: Term, *attrs: str) -> None:
    for a in attrs:
        refs = {r.iri: r for r in getattr(t, a)}
        setattr(t, a, sorted(refs.values(), key=lambda r: r.label.lower()))


def extract(loaded: LoadedOntology, config: Config, lang: str | None = None) -> Ontology:
    return Extractor(loaded, config, lang).extract()


__all__ = ["extract", "Extractor", "literal_text"]
