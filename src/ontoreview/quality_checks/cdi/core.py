# ruff: noqa: E741, B905, B007  (kept as in the reference implementation)
"""Cross-domain interoperability (CDI) scoring: alignment, generality and their combination.

Ported from the reference implementation ``crossdomain_interoperability.py`` (the CDI bundle);
the formulas, defaults and names follow it and its LaTeX definition, so results match the
script. Changes for OntoReview: the scorer is a library (no CLI or CSV writing here; see
:mod:`ontoreview.quality_checks.cdi`), progress goes to logging, HTTP requests send a generic
User-Agent and stop at a shared deadline, repository sources carry a configurable id prefix so
several OLS / OntoPortal instances can be used side by side, references can be URLs, and the
generality model is optional (``backend=None`` scores alignment only).

Correspondence with the definition (labels of the LaTeX definition in brackets):

* Reference set 𝒪 = 𝒪_giv ∪ 𝒪_disc [par:reference] -> build_reference_set()
* Lexical coverage cov_D(O_d) [eq:cov] -> lexical_coverage()
* (i)(a) direct correspondences -> SSSOMSource, LocalFileSource, OLSSource, OntoAlignerSource
* (i)(b) lexical correspondences, Table tab:syn -> lexical_relation(), *Source.correspondences()
* (i)(c) inferred correspondences (traversal) -> infer_by_traversal()
* calibration κ_μ -> Calibration
* strength s(m) = c·ρ(r)·γ^k [eq:strength] -> strength()
* a(e) [eq:ae] -> alignment_strengths(); Align(O_D), Align_d(O_D) [eq:align] -> alignment_score()
* gen(c) = 1 - Σ p_c(ℓ_k) w_k [eq:genc] -> class_generality(); Gen(O_D) [eq:gen] -> generality_score()
* CDI_β = (1+β²)·A·G / (A + β²·G) [eq:cdi] -> cdi_score()
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)
USER_AGENT = "ontoreview (ontology evaluation; cross-domain interoperability)"

# ===========================================================================
# Constants — LaTeX "Default parameters"
# ===========================================================================

ABSTRACT = (
    "We consider an ontology cross-domain interoperable if it both aligns "
    "with ontologies from other domains and defines its classes in "
    "sufficiently general, domain-neutral terms. We treat the latter as an "
    "indicator of its potential for adoption beyond its original domain."
)

DEFAULT_TAU = 0.5        # τ      threshold on s(m)                [eq:ae]
DEFAULT_C_LEX = 0.9      # c_lex  confidence of lexical matches     (i)(b)
DEFAULT_RHO_SUB = 0.8    # ρ_sub  weight of ⊑ / ⊒                   [eq:strength]
DEFAULT_GAMMA = 0.8      # γ      per-step traversal decay          [eq:strength]
DEFAULT_K_MAX = 3        # k_max  maximum traversal depth           (i)(c)
DEFAULT_TOP_N = 10       # N      discovered references kept        [par:reference]
DEFAULT_BETA = 1.0       # β      CDI weighting                     [eq:cdi]
DEFAULT_THETA = 0.5      # θ      interoperability threshold        [eq:cdi]
DEFAULT_NLI_MODEL = "facebook/bart-large-mnli"

# Relations r ∈ {≡, ⊑, ⊒}, read as "e r e'".
EQ, SUB, SUP = "≡", "⊑", "⊒"
INVERSE = {EQ: EQ, SUB: SUP, SUP: SUB}

# Generality scale ℓ_1 … ℓ_K (most general -> most specific)      (ii)
SPECIFICITY_LEVELS: tuple[str, ...] = (
    "a broad, abstract statement applicable to many situations",
    "a general statement about a particular field",
    "a moderately specific statement describing a concept or method",
    "a specific statement describing a concrete system or process",
    "a highly specific statement containing measurable details",
)
HYPOTHESIS_TEMPLATE = "This text is {}."

# def(c): annotation properties, in order of preference           (ii)
DEFINITION_PROPERTIES: tuple[str, ...] = (
    "http://www.w3.org/2004/02/skos/core#definition",
    "http://purl.obolibrary.org/obo/IAO_0000115",
    "http://www.w3.org/2000/01/rdf-schema#comment",
    "http://purl.org/dc/terms/description",
    "http://purl.org/dc/elements/1.1/description",
)

# Syn_t(x): synonym properties by type t                          (i)(b)
OIO = "http://www.geneontology.org/formats/oboInOwl#"
SYNONYM_PROPERTIES: dict[str, tuple[str, ...]] = {
    "exact": (
        "http://www.w3.org/2000/01/rdf-schema#label",
        "http://www.w3.org/2004/02/skos/core#prefLabel",
        "http://www.w3.org/2004/02/skos/core#altLabel",
        OIO + "hasExactSynonym",
    ),
    "broad": (OIO + "hasBroadSynonym",),     # names a concept broader than x
    "narrow": (OIO + "hasNarrowSynonym",),   # names a concept narrower than x
    # hasRelatedSynonym is ignored by definition.
}

# Table tab:syn — (type in Syn(e), type in Syn(e')) -> r           (i)(b)
SYNONYM_TABLE: dict[tuple[str, str], str] = {
    ("exact", "exact"): EQ,
    ("broad", "exact"): SUB,    # s broader than e, s names e'  => e ⊑ e'
    ("narrow", "exact"): SUP,   # s narrower than e, s names e' => e ⊒ e'
    ("exact", "broad"): SUP,    # s names e, s broader than e'  => e ⊒ e'
    ("exact", "narrow"): SUB,   # s names e, s narrower than e' => e ⊑ e'
}

# Mapping predicates with SKOS semantics ("subject r object")      (i)(a)
PREDICATE_RELATION: dict[str, str] = {
    "skos:exactMatch": EQ,
    "owl:equivalentClass": EQ,
    "owl:equivalentProperty": EQ,
    "owl:sameAs": EQ,
    "skos:broadMatch": SUB,     # object is broader  => subject ⊑ object
    "rdfs:subClassOf": SUB,
    "rdfs:subPropertyOf": SUB,
    "skos:narrowMatch": SUP,    # object is narrower => subject ⊒ object
    # skos:closeMatch / skos:relatedMatch are ignored by definition.
}

STANDARD_PREFIXES: dict[str, str] = {
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "semapv": "https://w3id.org/semapv/vocab/",
    "obo": "http://purl.obolibrary.org/obo/",
}

OLS_BASE = "https://www.ebi.ac.uk/ols4/api"
BIOPORTAL_BASE = "https://data.bioontology.org"


# ===========================================================================
# Data structures
# ===========================================================================

@dataclass
class Term:
    """An entity x with its typed strings Syn_t(x) (normalised)."""
    iri: str
    label: str = ""
    syn: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    raw: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    definition: str = ""


@dataclass(frozen=True)
class Correspondence:
    """m = <e, e', r, c, k, μ> plus the reference ontology O_d it points into."""
    source: str                 # e  ∈ E_D
    target: str                 # e' ∈ O_d
    relation: str               # r  ∈ {≡, ⊑, ⊒}
    confidence: float           # c  (calibrated)
    depth: int = 0              # k
    method: str = ""            # μ
    target_ontology: str = ""   # O_d identifier, e.g. "ols:envo"
    via: str = ""               # ancestor a for inferred correspondences


@dataclass
class OntologyEntities:
    path: str
    namespace: tuple[str, ...]
    entities: list[str]                         # E_D
    classes: list[str]                          # C_D
    terms: dict[str, Term]                      # every named class/property in the file
    parents: dict[str, set[str]]                # rdfs:subClassOf (named) for all classes
    equivalents: dict[str, set[str]]            # owl:equivalentClass (named)

    @property
    def definitions(self) -> dict[str, str]:
        return {c: self.terms[c].definition for c in self.classes if self.terms[c].definition}

    @property
    def labels(self) -> dict[str, str]:
        return {e: self.terms[e].label for e in self.entities if self.terms[e].label}

    def external_iris(self) -> set[str]:
        """Named IRIs outside E_D referenced by subClassOf / equivalentClass."""
        ents = set(self.entities)
        out = set()
        for d in (self.parents, self.equivalents):
            for vs in d.values():
                out |= {v for v in vs if v not in ents}
        return out


@dataclass
class OntologyInfo:
    """A candidate or given reference ontology O_d and its selection status."""
    id: str                      # e.g. "ols:envo", "file:ref1"
    source: str                  # ols | bioportal | file | sssom | ontoaligner
    title: str = ""
    domain: str = ""             # dom(O_d)
    given: bool = False          # O_d ∈ 𝒪_giv
    description: str = ""        # used to classify O_d into a scientific domain (SI)
    coverage: float = 0.0        # cov_D(O_d)            [eq:cov]
    n_correspondences: int = 0
    status: str = ""             # selected | excluded-self | excluded-same-domain | below-top-N | excluded-user
    align_d: float = 0.0         # Align_d(O_D)          [eq:align]


@dataclass
class CDIResult:
    align: float
    gen: float | None                          # None when no generality model is available
    cdi: float | None
    interoperable: bool
    definition_coverage: float
    mean_definition_generality: float | None
    n_entities: int
    n_aligned_entities: int
    n_classes: int
    n_defined_classes: int
    reference_ontologies: list[str]
    params: dict

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# String normalisation and the synonym table
# ===========================================================================

def normalise(s: str, split_camel: bool = False) -> str:
    """Normalised string used for Syn_t(x) comparisons."""
    if split_camel:
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = s.lower()
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def local_name(iri: str) -> str:
    return re.split(r"[#/]", iri.rstrip("/#"))[-1]


def lexical_relation(type_e: str, type_e2: str) -> str | None:
    """Table tab:syn: relation implied by a shared string, or None."""
    return SYNONYM_TABLE.get((type_e, type_e2))


# ===========================================================================
# Scoring formulas
# ===========================================================================

def rho(relation: str, rho_sub: float = DEFAULT_RHO_SUB) -> float:
    """ρ(r): 1 for ≡, ρ_sub for ⊑ / ⊒.                       [eq:strength]"""
    return 1.0 if relation == EQ else rho_sub


def strength(m: Correspondence, rho_sub: float = DEFAULT_RHO_SUB,
             gamma: float = DEFAULT_GAMMA) -> float:
    """s(m) = c · ρ(r) · γ^k                                   [eq:strength]"""
    return m.confidence * rho(m.relation, rho_sub) * gamma ** m.depth


def alignment_strengths(
    entities: Sequence[str],
    correspondences: Iterable[Correspondence],
    tau: float = DEFAULT_TAU,
    rho_sub: float = DEFAULT_RHO_SUB,
    gamma: float = DEFAULT_GAMMA,
) -> dict[str, tuple[float, Correspondence | None]]:
    """
    a(e) = max_{m ∈ M(e)} s(m) if that max ≥ τ, else 0        [eq:ae]
    Returns e -> (a(e), argmax m or None).
    """
    best: dict[str, tuple[float, Correspondence | None]] = {e: (0.0, None) for e in entities}
    for m in correspondences:
        if m.source not in best:
            continue
        s = strength(m, rho_sub, gamma)
        if s > best[m.source][0]:
            best[m.source] = (s, m)
    return {e: ((s, m) if s >= tau else (0.0, m)) for e, (s, m) in best.items()}


def alignment_score(strengths: dict[str, tuple[float, Correspondence | None]]) -> float:
    """Align(O_D) = (1/|E_D|) Σ_e a(e)                         [eq:align]"""
    return sum(a for a, _ in strengths.values()) / len(strengths) if strengths else 0.0


def specificity_weights(k: int = len(SPECIFICITY_LEVELS)) -> list[float]:
    """w_k = (k-1)/(K-1)                                        (ii)"""
    return [i / (k - 1) for i in range(k)]


def class_generality(probabilities: Sequence[float]) -> float:
    """gen(c) = 1 - Σ_k p_c(ℓ_k) w_k                           [eq:genc]"""
    w = specificity_weights(len(probabilities))
    total = sum(probabilities)
    if total <= 0:
        raise ValueError("Probabilities must sum to a positive value.")
    return 1.0 - sum((p / total) * wk for p, wk in zip(probabilities, w))


def cdi_score(align: float, gen: float, beta: float = DEFAULT_BETA) -> float:
    """CDI_β = (1+β²)·A·G / (A + β²·G); 0 if A = G = 0.       [eq:cdi]
    As in F_β, β > 1 favours alignment, β < 1 favours generality."""
    if beta <= 0:
        raise ValueError("beta must be > 0")
    denom = align + beta ** 2 * gen
    return 0.0 if denom == 0 else (1 + beta ** 2) * align * gen / denom


# ===========================================================================
# Calibration κ_μ
# ===========================================================================

class Calibration:
    """κ_μ: raw score -> [0,1] per method μ. Default: identity, clipped."""

    def __init__(self, maps: dict[str, Callable[[float], float]] | None = None):
        self.maps = maps or {}

    def __call__(self, method: str, raw: float) -> float:
        f = self.maps.get(method)
        if f is None:
            for prefix, g in self.maps.items():     # allow "ontoaligner" for "ontoaligner-fuzzy"
                if method.startswith(prefix):
                    f = g
                    break
        v = f(raw) if f else raw
        return min(1.0, max(0.0, float(v)))


# ===========================================================================
# Ontology loading (O_D and file references)
# ===========================================================================

def _infer_namespace(g, classes: list[str]) -> tuple[str, ...]:
    """Guess O_D's own IRI prefix: ontology IRI if it prefixes most classes,
    otherwise the most common prefix (up to the last '#', '/' or '_')."""
    from rdflib.namespace import OWL, RDF
    if not classes:
        return ()
    onto_iris = [str(s) for s in g.subjects(RDF.type, OWL.Ontology)]
    for oi in onto_iris:
        for cand in (oi, oi.rstrip("/#") + "/", oi.rstrip("/#") + "#"):
            if sum(c.startswith(cand) for c in classes) >= 0.5 * len(classes):
                return (cand,)
    counts: dict[str, int] = defaultdict(int)
    for c in classes:
        m = re.match(r"(.*[#/_])", c)
        if m:
            counts[m.group(1)] += 1
    if not counts:
        return ()
    best = max(counts, key=counts.get)
    return (best,) if counts[best] >= 0.3 * len(classes) else ()


def read_ontology_header(path: str | Path, lang: str = "en") -> dict[str, str]:
    """IRI, title and description from the owl:Ontology header of a file (empty strings when the
    file has no header or cannot be read). The description is used to classify O_d into a domain."""
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import OWL, RDF
    empty = {"iri": "", "title": "", "description": ""}
    try:
        g = Graph()
        g.parse(str(path))
    except Exception:  # noqa: BLE001 - SSSOM, unparsable or remote-only files
        return empty
    title_p = ("http://purl.org/dc/terms/title", "http://purl.org/dc/elements/1.1/title",
               "http://www.w3.org/2000/01/rdf-schema#label")
    desc_p = ("http://purl.org/dc/terms/description", "http://purl.org/dc/elements/1.1/description",
              "http://www.w3.org/2000/01/rdf-schema#comment", "http://www.w3.org/2004/02/skos/core#definition")

    def first(subj, props):
        for prop in props:
            vals = [o for o in g.objects(subj, URIRef(prop)) if isinstance(o, Literal)]
            pref = [v for v in vals if v.language in (lang, None)] or vals
            if pref:
                return str(pref[0]).strip()
        return ""

    for subj in g.subjects(RDF.type, OWL.Ontology):
        return {"iri": str(subj), "title": first(subj, title_p), "description": first(subj, desc_p)}
    return empty


def load_ontology(
    path: str | Path,
    namespace: str | Sequence[str] | None = "auto",
    include_properties: bool = True,
    lang: str = "en",
) -> OntologyEntities:
    """
    Parse an RDF/OWL file. E_D = own classes (+ object/datatype properties),
    restricted to `namespace` ("auto" = inferred, None = all named entities).
    Extracts Syn_t(x), def(c), rdfs:subClassOf and owl:equivalentClass.
    """
    from rdflib import Graph, Literal, URIRef
    from rdflib.namespace import OWL, RDF, RDFS

    g = Graph()
    g.parse(str(path))

    def named(n) -> bool:
        return isinstance(n, URIRef) and str(n) not in (str(OWL.Thing), str(OWL.Nothing))

    all_classes = sorted({str(s) for t in (OWL.Class, RDFS.Class)
                          for s in g.subjects(RDF.type, t) if named(s)})
    all_props = sorted({str(s) for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
                        for s in g.subjects(RDF.type, t) if named(s)})

    if namespace == "auto":
        ns = _infer_namespace(g, all_classes)
    elif namespace is None:
        ns = ()
    else:
        ns = (namespace,) if isinstance(namespace, str) else tuple(namespace)

    own = (lambda s: s.startswith(ns)) if ns else (lambda s: True)
    classes = [c for c in all_classes if own(c)]
    props = [p for p in all_props if own(p)] if include_properties else []
    entities = sorted(set(classes) | set(props))

    def literals(subject, predicate) -> list[str]:
        vals = [o for o in g.objects(subject, predicate) if isinstance(o, Literal)]
        pref = [v for v in vals if v.language in (lang, None)]
        return [str(v).strip() for v in (pref or vals) if str(v).strip()]

    terms: dict[str, Term] = {}
    for iri in set(all_classes) | set(all_props):
        node = URIRef(iri)
        t = Term(iri)
        for typ, props_ in SYNONYM_PROPERTIES.items():
            for p in props_:
                for v in literals(node, URIRef(p)):
                    t.raw[typ].add(v)
                    t.syn[typ].add(normalise(v))
        labels = literals(node, RDFS.label) or literals(node, URIRef(SYNONYM_PROPERTIES["exact"][1]))
        t.label = labels[0] if labels else ""
        if not t.raw["exact"]:                       # fall back to the IRI local name
            ln = local_name(iri)
            t.raw["exact"].add(normalise(ln, split_camel=True))
            t.syn["exact"].add(normalise(ln, split_camel=True))
        for p in DEFINITION_PROPERTIES:
            d = literals(node, URIRef(p))
            if d:
                t.definition = d[0]
                break
        terms[iri] = t

    parents: dict[str, set[str]] = defaultdict(set)
    equivalents: dict[str, set[str]] = defaultdict(set)
    for s, o in g.subject_objects(RDFS.subClassOf):
        if named(s) and named(o):
            parents[str(s)].add(str(o))
    for s, o in g.subject_objects(RDFS.subPropertyOf):
        if named(s) and named(o):
            parents[str(s)].add(str(o))
    for s, o in g.subject_objects(OWL.equivalentClass):
        if named(s) and named(o):
            equivalents[str(s)].add(str(o))
            equivalents[str(o)].add(str(s))

    return OntologyEntities(str(path), ns, entities, classes, terms,
                            dict(parents), dict(equivalents))


# ===========================================================================
# HTTP helper (stdlib only; cached, retried, thread-safe)
# ===========================================================================

class _HTTP:
    def __init__(self, headers: dict | None = None, retries: int = 3, timeout: float = 30,
                 deadline: float | None = None):
        self.headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        self.retries, self.timeout, self.deadline = retries, timeout, deadline
        self.cache: dict[str, dict | None] = {}
        self.lock = threading.Lock()
        self.out_of_time = False     # set when the deadline cut lookups short
        self.unavailable: set[str] = set()   # hosts that were down during this run

    def get_json(self, url: str, params: dict | None = None) -> dict | None:
        full = url + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        with self.lock:
            if full in self.cache:
                return self.cache[full]
        from ... import netstate

        out = None
        for attempt in range(self.retries):
            if self.deadline is not None and time.time() > self.deadline:
                self.out_of_time = True
                return None
            if netstate.is_down(full):          # failed earlier: skip at once instead of waiting again
                self.unavailable.add(netstate.host(full))
                return None
            try:
                req = urllib.request.Request(full, headers=self.headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    out = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 401, 403, 404):
                    if e.code in (401, 403):
                        raise
                    break
                if attempt >= 1:                # a second server error: the service is down
                    netstate.mark_down(full)
                    self.unavailable.add(netstate.host(full))
                    break
                time.sleep(1.5)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                netstate.mark_down(full)        # no answer: do not retry, skip this host from now on
                self.unavailable.add(netstate.host(full))
                break
            except json.JSONDecodeError:
                time.sleep(1.5 * (attempt + 1))
        with self.lock:
            self.cache[full] = out
        return out


# ===========================================================================
# Reference sources
# ===========================================================================

class ReferenceSource(ABC):
    """A provider of reference ontologies O_d and correspondences into them."""

    #: True if the user named the ontologies (𝒪_giv); False for discovery (𝒪_disc)
    given: bool = True
    #: id prefix of the ontologies this source describes ("ols", "bioportal", …); "" for files
    prefix: str = ""

    @abstractmethod
    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        """Direct and lexical correspondences (k = 0) for e ∈ E_D, (i)(a)-(b)."""

    def identity_targets(self, onto: OntologyEntities) -> list[Correspondence]:
        """For external IRIs x referenced by O_D (subClassOf/equivalentClass)
        that are defined in some O_d: <x, x, ≡, 1, 0>. Used by traversal (i)(c)."""
        return []

    def self_ontologies(self) -> set[str]:
        """Repository ontologies that define an IRI in E_D (i.e. O_D itself)."""
        return set()

    def info(self) -> dict[str, OntologyInfo]:
        return {}


def _asserted_direct(onto: OntologyEntities, defined_in: dict[str, str],
                     method: str) -> list[Correspondence]:
    """(i)(a) asserted axioms: e subClassOf x / e equivalentClass x, with x in O_d."""
    out = []
    for e in onto.entities:
        for x in onto.parents.get(e, ()):
            if x in defined_in:
                out.append(Correspondence(e, x, SUB, 1.0, 0, method + ":subClassOf", defined_in[x]))
        for x in onto.equivalents.get(e, ()):
            if x in defined_in:
                out.append(Correspondence(e, x, EQ, 1.0, 0, method + ":equivalentClass", defined_in[x]))
    return out


class LocalFileSource(ReferenceSource):
    """A reference ontology given as a local/uploaded file."""

    def __init__(self, path: str | Path, c_lex: float = DEFAULT_C_LEX):
        self.path = str(path)
        self.id = "file:" + Path(path).name
        self.c_lex = c_lex
        self.ref = load_ontology(path, namespace=None, include_properties=True)
        self.index: dict[str, list[tuple[str, str]]] = defaultdict(list)   # string -> [(iri, type)]
        for iri, t in self.ref.terms.items():
            for typ, strings in t.syn.items():
                for s in strings:
                    self.index[s].append((iri, typ))

    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        out: list[Correspondence] = []
        ref_iris = set(self.ref.terms)
        for e in onto.entities:
            # (i)(a) shared IRI: O_d reuses e
            if e in ref_iris:
                out.append(Correspondence(e, e, EQ, 1.0, 0, "shared-iri", self.id))
            # (i)(b) lexical, Table tab:syn
            for typ_e, strings in onto.terms[e].syn.items():
                for s in strings:
                    for iri2, typ_e2 in self.index.get(s, ()):
                        r = lexical_relation(typ_e, typ_e2)
                        if r and iri2 != e:
                            out.append(Correspondence(e, iri2, r, self.c_lex, 0,
                                                      f"lexical:{typ_e}/{typ_e2}", self.id))
        out += _asserted_direct(onto, {x: self.id for x in ref_iris}, "asserted")
        return out

    def identity_targets(self, onto):
        return [Correspondence(x, x, EQ, 1.0, 0, "shared-iri", self.id)
                for x in onto.external_iris() if x in self.ref.terms]

    def info(self):
        h = read_ontology_header(self.path)
        return {self.id: OntologyInfo(self.id, "file", title=h["title"] or Path(self.path).name, given=True,
                                      description=h["description"])}


class SSSOMSource(ReferenceSource):
    """Curated mappings in an SSSOM TSV file (asserted direct correspondences)."""

    def __init__(self, path: str | Path, prefix_map: dict[str, str] | None = None,
                 calibration: Calibration | None = None):
        self.path = Path(path)
        self.id = "sssom:" + self.path.name
        self.prefix_map = prefix_map or {}
        self.calibration = calibration or Calibration()

    @staticmethod
    def _header_curie_map(lines: list[str]) -> dict[str, str]:
        text = "\n".join(l[1:] for l in lines)
        try:
            import yaml
            return dict((yaml.safe_load(text) or {}).get("curie_map", {}) or {})
        except Exception:
            cmap, inside = {}, False
            for line in text.splitlines():
                if line.strip().startswith("curie_map"):
                    inside = True
                    continue
                if inside:
                    if line.startswith((" ", "\t")) and ":" in line:
                        k, v = line.strip().split(":", 1)
                        cmap[k.strip()] = v.strip().strip("'\"")
                    else:
                        inside = False
            return cmap

    @staticmethod
    def _expand(curie: str, pmap: dict[str, str]) -> str:
        if curie.startswith(("http://", "https://", "urn:")):
            return curie
        if ":" in curie:
            p, l = curie.split(":", 1)
            if p in pmap:
                return pmap[p] + l
        return curie

    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        header = [l for l in lines if l.startswith("#")]
        body = [l for l in lines if l.strip() and not l.startswith("#")]
        pmap = {**STANDARD_PREFIXES, **self._header_curie_map(header), **self.prefix_map}
        preds = {self._expand(k, pmap): v for k, v in PREDICATE_RELATION.items()}
        ents = set(onto.entities)
        out = []
        for row in csv.DictReader(body, delimiter="\t"):
            s = self._expand(row["subject_id"].strip(), pmap)
            o = self._expand(row["object_id"].strip(), pmap)
            r = preds.get(self._expand(row["predicate_id"].strip(), pmap))
            if r is None:
                continue
            raw = (row.get("confidence") or "").strip()
            c = self.calibration("sssom", float(raw) if raw else 1.0)
            if s in ents and o not in ents:
                out.append(Correspondence(s, o, r, c, 0, "sssom", self.id))
            elif o in ents and s not in ents:       # orient so that source ∈ E_D
                out.append(Correspondence(o, s, INVERSE[r], c, 0, "sssom", self.id))
        return out

    def info(self):
        return {self.id: OntologyInfo(self.id, "sssom", title=self.path.name, given=True)}


def _as_rdfxml(path: str | Path, cache_dir: str | Path | None = None) -> str:
    """Return a path to an RDF/XML version of `path` (converted with rdflib if needed)."""
    from rdflib import Graph
    path = Path(path)
    if path.suffix.lower() in (".owl", ".rdf", ".xml"):
        try:
            Graph().parse(str(path), format="xml")
            return str(path)
        except Exception:
            pass
    out = Path(cache_dir or Path(tempfile.gettempdir()) / "ontoreview-cdi") / (path.stem + ".rdfxml.owl")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        g = Graph()
        g.parse(str(path))
        g.serialize(str(out), format="xml")
    return str(out)


class OntoAlignerSource(ReferenceSource):
    """
    Note: OntoAligner imports pykeen/pystow, which needs a writable home
    directory; set PYSTOW_HOME if ~/.data is not writable.

    Automatic matcher (i)(a) via OntoAligner on O_D and a reference *file*.
    matcher = "fuzzy"  -> ConceptLightweightEncoder + SimpleFuzzySMLightweight
    matcher = "sbert"  -> ConceptLightweightEncoder + SBERTRetrieval + retriever_postprocessor
    Produces ≡ correspondences with c = κ_μ(score).
    """

    def __init__(self, path: str | Path, matcher: str = "fuzzy", threshold: float = 0.5,
                 sbert_model: str = "all-MiniLM-L6-v2", top_k: int = 5, device: str = "cpu",
                 calibration: Calibration | None = None, ontology_id: str | None = None):
        self.path, self.matcher, self.threshold = str(path), matcher, threshold
        self.sbert_model, self.top_k, self.device = sbert_model, top_k, device
        self.calibration = calibration or Calibration()
        self.id = ontology_id or ("file:" + Path(path).name)   # same O_d as the file source

    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        from ontoaligner import encoder as oa_encoder
        from ontoaligner.ontology import GenericOMDataset

        # OntoAligner's GenericOntology parses RDF/XML only -> convert if needed.
        dataset = GenericOMDataset().collect(source_ontology_path=_as_rdfxml(onto.path),
                                             target_ontology_path=_as_rdfxml(self.path))
        enc = oa_encoder.ConceptLightweightEncoder()
        encoded = enc(source=dataset["source"], target=dataset["target"])
        if self.matcher == "fuzzy":
            from ontoaligner.aligner import SimpleFuzzySMLightweight
            preds = SimpleFuzzySMLightweight(fuzzy_sm_threshold=self.threshold).generate(input_data=encoded)
        elif self.matcher == "sbert":
            from ontoaligner.aligner import SBERTRetrieval
            from ontoaligner.postprocess import retriever_postprocessor
            # Fix over the reference script: top_k above the reference's size fails in torch.topk
            # ("selected index k out of range"), e.g. a reference with fewer than 5 entities.
            model = SBERTRetrieval(device=self.device, top_k=max(1, min(self.top_k, len(dataset["target"]))))
            model.load(path=self.sbert_model)
            preds = retriever_postprocessor(model.generate(input_data=encoded))
        else:
            raise ValueError(f"unknown OntoAligner matcher {self.matcher!r}")

        method = f"ontoaligner-{self.matcher}"
        ents = set(onto.entities)
        return [Correspondence(p["source"], p["target"], EQ,
                               self.calibration(method, float(p["score"])), 0, method, self.id)
                for p in preds if p["source"] in ents and float(p["score"]) >= self.threshold]

    def info(self):
        h = read_ontology_header(self.path)
        return {self.id: OntologyInfo(self.id, "file", title=h["title"] or Path(self.path).name, given=True,
                                      description=h["description"])}


class OLSSource(ReferenceSource):
    """
    EBI OLS4. ontologies=None -> discovery over all of OLS (𝒪_disc);
    otherwise the named ontologies are given references (𝒪_giv).

    (i)(a) direct:  IRI lookup -> ontologies that *reuse* e (non-defining) give
                    <e, e, ≡, 1>; the defining ontology of e is O_D itself.
                    Asserted subClassOf/equivalentClass to IRIs defined in O_d.
    (i)(b) lexical: exact search of each exact/broad/narrow string of e; only
                    hits from the *defining* ontology count. OLS returns labels
                    and (exact) synonyms of e', so e'-side type is 'exact'.
    """

    def __init__(self, ontologies: Sequence[str] | None = None, c_lex: float = DEFAULT_C_LEX,
                 rows: int = 200, workers: int = 8, base: str = OLS_BASE, prefix: str = "ols",
                 timeout: float = 30, deadline: float | None = None):
        self.ontologies = [o.lower() for o in ontologies] if ontologies else None
        self.given = ontologies is not None
        self.c_lex, self.rows, self.workers, self.base = c_lex, rows, workers, base.rstrip("/")
        self.prefix = prefix
        self.http = _HTTP(timeout=timeout, deadline=deadline)
        self._self: set[str] = set()
        self._info: dict[str, OntologyInfo] = {}
        self.info_cache = None       # term database, asked before the repository (see cdi.termdb)
        self.releases: dict[str, dict] = {}
        self._defined_in: dict[str, str] = {}

    def _oid(self, name: str) -> str:
        return f"{self.prefix}:{name}"

    def _keep(self, name: str) -> bool:
        return self.ontologies is None or name in self.ontologies

    def _search(self, q: str) -> list[dict]:
        params = {"q": q, "exact": "true", "queryFields": "label,synonym", "rows": self.rows,
                  "fieldList": "iri,label,synonym,ontology_name,is_defining_ontology,type"}
        if self.ontologies:
            params["ontology"] = ",".join(self.ontologies)
        d = self.http.get_json(self.base + "/search", params)
        return (d or {}).get("response", {}).get("docs", [])

    def _lookup_iri(self, iri: str) -> list[dict]:
        d = self.http.get_json(self.base + "/terms", {"iri": iri, "size": 500})
        return (d or {}).get("_embedded", {}).get("terms", [])

    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        ents = set(onto.entities)
        queries = sorted({(e, typ, raw) for e in onto.entities
                          for typ, raws in onto.terms[e].raw.items() for raw in raws})
        iris = sorted(ents | onto.external_iris())
        with ThreadPoolExecutor(self.workers) as ex:
            search_res = list(ex.map(lambda q: self._search(q[2]), queries))
            iri_res = dict(zip(iris, ex.map(self._lookup_iri, iris)))

        out: list[Correspondence] = []
        # (i)(a) reuse of e / definition of external IRIs
        for iri, hits in iri_res.items():
            for h in hits:
                name = h.get("ontology_name", "")
                if h.get("is_defining_ontology"):
                    if iri in ents:
                        self._self.add(self._oid(name))          # O_D itself is in OLS
                    else:
                        self._defined_in.setdefault(iri, self._oid(name))
                elif iri in ents and self._keep(name):
                    out.append(Correspondence(iri, iri, EQ, 1.0, 0, "shared-iri", self._oid(name)))
        out += _asserted_direct(onto, self._defined_in, "asserted")

        # (i)(b) lexical, Table tab:syn (e'-side type: exact)
        for (e, typ_e, raw), hits in zip(queries, search_res):
            for h in hits:
                name = h.get("ontology_name", "")
                if not h.get("is_defining_ontology") or not self._keep(name) or h.get("iri") in ents:
                    continue
                r = lexical_relation(typ_e, "exact")
                if r:
                    out.append(Correspondence(e, h["iri"], r, self.c_lex, 0,
                                              f"lexical:{typ_e}/exact", self._oid(name)))
        return out

    def identity_targets(self, onto):
        return [Correspondence(x, x, EQ, 1.0, 0, "shared-iri", o) for x, o in self._defined_in.items()]

    def self_ontologies(self):
        return set(self._self)

    def describe(self, ontology_ids: Iterable[str]) -> dict[str, OntologyInfo]:
        """dom(O_d), title and release from OLS v2 metadata; the term database is asked first."""
        for oid in ontology_ids:
            if oid in self._info or not oid.startswith(self.prefix + ":"):
                continue
            if _from_cache(self, oid):
                continue
            d = self.http.get_json(f"{self.base}/v2/ontologies/{oid.split(':', 1)[1]}") or {}
            dom = d.get("domain", "")
            dom = dom if isinstance(dom, str) else ", ".join(map(str, dom or []))
            title = _text(d.get("title"))
            desc = _text(d.get("description"))
            self._info[oid] = OntologyInfo(oid, self.prefix, title=title, domain=dom, given=self.given,
                                           description=desc)
            if d:
                rel = release_record(self.prefix, oid.split(":", 1)[1], d, title=title,
                                     ontology_iri=_text(d.get("iri")),
                                     version_iri=_text(d.get(OWL_VERSION_IRI) or d.get("versionIri")),
                                     version=_text(d.get(OWL_VERSION_INFO) or d.get("version")),
                                     released=_text(d.get("loaded") or d.get("updated") or d.get("sourceFileTimestamp")))
                _to_cache(self, oid, dom, rel, self._info[oid].description)
        return self._info

    def info(self):
        return self._info


class BioPortalSource(ReferenceSource):
    """
    NCBO BioPortal (API key required). ontologies=None -> discovery.
    (i)(b) lexical: /search with require_exact_match; matchType tells whether
    e' matched on prefLabel or synonym (both treated as exact).
    dom(O_d): BioPortal categories.
    """

    def __init__(self, api_key: str, ontologies: Sequence[str] | None = None,
                 c_lex: float = DEFAULT_C_LEX, workers: int = 4, base: str = BIOPORTAL_BASE,
                 prefix: str = "bioportal", timeout: float = 30, deadline: float | None = None):
        if not api_key:
            raise ValueError("BioPortal requires an API key (BIOPORTAL_API_KEY).")
        self.ontologies = [o.upper() for o in ontologies] if ontologies else None
        self.given = ontologies is not None
        self.c_lex, self.workers, self.base = c_lex, workers, base.rstrip("/")
        self.prefix = prefix
        self.http = _HTTP(headers={"Authorization": f"apikey token={api_key}"},
                          timeout=timeout, deadline=deadline)
        self._info: dict[str, OntologyInfo] = {}
        self.info_cache = None       # term database, asked before the repository (see cdi.termdb)
        self.releases: dict[str, dict] = {}

    @staticmethod
    def _acronym(hit: dict) -> str:
        link = hit.get("links", {}).get("ontology", "")
        return link.rstrip("/").split("/")[-1]

    def _search(self, q: str) -> list[dict]:
        params = {"q": q, "require_exact_match": "true", "pagesize": 100,
                  "include": "prefLabel,synonym", "display_context": "false"}
        if self.ontologies:
            params["ontologies"] = ",".join(self.ontologies)
        d = self.http.get_json(self.base + "/search", params)
        return (d or {}).get("collection", [])

    def correspondences(self, onto: OntologyEntities) -> list[Correspondence]:
        ents = set(onto.entities)
        queries = sorted({(e, typ, raw) for e in onto.entities
                          for typ, raws in onto.terms[e].raw.items() for raw in raws})
        with ThreadPoolExecutor(self.workers) as ex:
            results = list(ex.map(lambda q: self._search(q[2]), queries))
        out = []
        for (e, typ_e, _), hits in zip(queries, results):
            for h in hits:
                iri, acr = h.get("@id", ""), self._acronym(h)
                if not iri or iri in ents or not acr:
                    continue
                r = lexical_relation(typ_e, "exact")
                if r:
                    out.append(Correspondence(e, iri, r, self.c_lex, 0,
                                              f"lexical:{typ_e}/exact", f"{self.prefix}:{acr}"))
        return out

    def describe(self, ontology_ids: Iterable[str]) -> dict[str, OntologyInfo]:
        for oid in ontology_ids:
            if oid in self._info or not oid.startswith(self.prefix + ":"):
                continue
            if _from_cache(self, oid):
                continue
            acr = oid.split(":", 1)[1]
            meta = self.http.get_json(f"{self.base}/ontologies/{acr}") or {}
            cats = self.http.get_json(f"{self.base}/ontologies/{acr}/categories") or []
            dom = ", ".join(c.get("name", "") for c in cats if isinstance(c, dict))
            self._info[oid] = OntologyInfo(oid, self.prefix, title=meta.get("name", ""),
                                           domain=dom, given=self.given)
            if meta:
                sub = self.http.get_json(f"{self.base}/ontologies/{acr}/latest_submission",
                                         {"display": "version,released,URI,versionIRI,description"}) or {}
                self._info[oid].description = _text(sub.get("description"))
                rel = release_record(self.prefix, acr, {"ontology": meta, "latest_submission": sub},
                                     title=meta.get("name", ""), ontology_iri=_text(sub.get("URI")),
                                     version_iri=_text(sub.get("versionIRI")), version=_text(sub.get("version")),
                                     released=_text(sub.get("released")))
                _to_cache(self, oid, dom, rel, self._info[oid].description)
        return self._info

    def info(self):
        return self._info


# ===========================================================================
# Reference ontology releases (OntoReview addition: what each O_d was checked against)
# ===========================================================================

OWL_VERSION_IRI = "http://www.w3.org/2002/07/owl#versionIRI"
OWL_VERSION_INFO = "http://www.w3.org/2002/07/owl#versionInfo"


def _text(v) -> str:
    """A plain string from an API value that may be a string, a list or {"value": …}; "" if absent."""
    if isinstance(v, dict):
        v = v.get("value") or v.get("@value") or v.get("@id")
    if isinstance(v, (list, tuple)):
        v = next((_text(x) for x in v if _text(x)), "")
    return str(v).strip() if v not in (None, "") else ""


def identified_by(rel: dict) -> str:
    """The strongest release identifier a record has. Not every ontology declares a version IRI or
    version, and not every repository reports a load date, so the fingerprint is the fallback."""
    for key, name in (("version_iri", "version IRI"), ("version", "version"), ("released", "release/load date"),
                      ("sha256", "content hash"), ("metadata_sha256", "metadata fingerprint")):
        if rel.get(key):
            return name
    return "retrieval time only"


def release_record(source: str, name: str, payload: dict, **fields) -> dict:
    """A release record with whatever the repository reported, plus what is always known: when it
    was retrieved and a fingerprint (SHA-256 of the metadata answer)."""
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    rel = {"source": source, "ontology": name, **{k: v for k, v in fields.items() if v},
           "retrieved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "metadata_sha256": hashlib.sha256(canon).hexdigest()}
    rel["identified_by"] = identified_by(rel)
    return rel


def _from_cache(src, oid: str) -> bool:
    """Fill info and release for ``oid`` from the term database; False when not there or expired."""
    cache = getattr(src, "info_cache", None)
    row = cache.get(oid) if cache else None
    if not row or "description" not in (row.get("payload") or {}):
        return False        # not cached, expired, or cached before descriptions were kept (SI needs them)
    src._info[oid] = OntologyInfo(oid, src.prefix, title=row.get("title") or "", domain=row.get("domain") or "",
                                  given=src.given, description=row["payload"].get("description") or "")
    rel = dict(row["payload"].get("release") or {})
    rel["cached"] = row["fetched_at"]
    rel.setdefault("identified_by", identified_by(rel))
    src.releases[oid] = rel
    return True


def _to_cache(src, oid: str, domain: str, rel: dict, description: str = "") -> None:
    src.releases[oid] = rel
    cache = getattr(src, "info_cache", None)
    if cache:
        cache.put({"id": oid, "source": src.prefix, "title": rel.get("title"), "domain": domain,
                   "ontology_iri": rel.get("ontology_iri"), "version_iri": rel.get("version_iri"),
                   "version": rel.get("version"), "released": rel.get("released"),
                   "payload": {"release": rel, "description": description}})


# ===========================================================================
# Reference set 𝒪 = 𝒪_giv ∪ 𝒪_disc                           [par:reference]
# ===========================================================================

def lexical_coverage(entities: Sequence[str], correspondences: Iterable[Correspondence]
                     ) -> dict[str, float]:
    """cov_D(O_d) = |{e : M_0(e, O_d) ≠ ∅}| / |E_D|            [eq:cov]
    (counts direct and lexical correspondences with k = 0)."""
    hit: dict[str, set[str]] = defaultdict(set)
    for m in correspondences:
        if m.depth == 0:
            hit[m.target_ontology].add(m.source)
    n = len(entities) or 1
    return {o: len(s) / n for o, s in hit.items()}


def _same_domain(dom: str, domains: Sequence[str]) -> bool:
    d = dom.lower()
    return bool(d) and any(x.lower() in d or d in x.lower() for x in domains)


def build_reference_set(
    onto: OntologyEntities,
    sources: Sequence[ReferenceSource],
    domains: Sequence[str] = (),
    top_n: int = DEFAULT_TOP_N,
    exclude: Sequence[str] = (),
    verbose: bool = True,
) -> tuple[list[Correspondence], list[Correspondence], dict[str, OntologyInfo]]:
    """
    Collect k = 0 correspondences from all sources, rank discovered candidates
    by cov_D, apply the self / same-domain / user exclusions, keep top-N.
    Returns (correspondences into 𝒪, identity targets for traversal, ontology table).
    """
    all_corr: list[Correspondence] = []
    identities: list[Correspondence] = []
    given_ids: set[str] = set()
    self_ids: set[str] = set()
    for src in sources:
        t0 = time.time()
        c = src.correspondences(onto)
        if verbose:
            log.info("CDI %s: %d correspondences (%.1fs)", getattr(src, "id", "") or type(src).__name__,
                     len(c), time.time() - t0)
        all_corr += c
        identities += src.identity_targets(onto)
        self_ids |= src.self_ontologies()
        if src.given:
            given_ids |= {m.target_ontology for m in c} | set(src.info())

    cov = lexical_coverage(onto.entities, all_corr)
    candidates = set(cov) | given_ids
    table: dict[str, OntologyInfo] = {}
    for src in sources:
        if hasattr(src, "describe"):
            src.describe([o for o in candidates if o.split(":", 1)[0] == src.prefix])
        for oid, inf in src.info().items():
            table.setdefault(oid, inf)
    n_corr: dict[str, int] = defaultdict(int)
    for m in all_corr:
        n_corr[m.target_ontology] += 1
    for oid in candidates:
        inf = table.setdefault(oid, OntologyInfo(oid, oid.split(":", 1)[0]))
        # Fix over the reference script (which used ``inf.given or …``): a given repository source
        # (e.g. ols:bfo) also describes candidates found by a discovery source on the same
        # repository (ols), and must not mark those as given; given_ids is the exact set.
        inf.given = oid in given_ids
        inf.coverage = cov.get(oid, 0.0)
        inf.n_correspondences = n_corr.get(oid, 0)

    excl = {x if ":" in x else f"ols:{x.lower()}" for x in exclude} | \
           {f"bioportal:{x.upper()}" for x in exclude if ":" not in x}
    ranked = sorted((table[o] for o in candidates), key=lambda i: (-i.coverage, i.id))
    kept_disc = 0
    for inf in ranked:
        if inf.id in self_ids:
            inf.status = "excluded-self"
        elif inf.id in excl:
            inf.status = "excluded-user"
        elif inf.given:
            inf.status = "selected"                     # 𝒪_giv always retained
        elif domains and _same_domain(inf.domain, domains):
            inf.status = "excluded-same-domain"
        elif kept_disc < top_n:
            inf.status = "selected"
            kept_disc += 1
        else:
            inf.status = "below-top-N"

    selected = {o for o, i in table.items() if i.status == "selected"}
    corr = [m for m in all_corr if m.target_ontology in selected]
    identities = [m for m in identities if m.target_ontology in selected]
    return corr, identities, {o: table[o] for o in candidates}


# ===========================================================================
# (i)(c) Inferred correspondences — hierarchy traversal
# ===========================================================================

def infer_by_traversal(
    onto: OntologyEntities,
    base: Sequence[Correspondence],
    identities: Sequence[Correspondence] = (),
    k_max: int = DEFAULT_K_MAX,
) -> list[Correspondence]:
    """
    For e ∈ E_D and each ancestor a at subclass distance 1 ≤ k ≤ k_max, every
    base correspondence <a, a', r, c, 0, μ> with r ∈ {≡, ⊑} yields
    <e, a', ⊑, c, k, μ> (sound: e ⊑ a ⊑ a'). ⊒ is not propagated.
    `identities` supplies <x, x, ≡, 1> for external ancestors x defined in O_d.
    """
    by_src: dict[str, list[Correspondence]] = defaultdict(list)
    for m in list(base) + list(identities):
        if m.depth == 0 and m.relation in (EQ, SUB):
            by_src[m.source].append(m)

    out: list[Correspondence] = []
    for e in onto.entities:
        seen = {e}
        frontier = deque([(e, 0)])
        while frontier:
            node, k = frontier.popleft()
            if k == k_max:
                continue
            for a in onto.parents.get(node, ()):
                if a in seen:
                    continue
                seen.add(a)
                for m in by_src.get(a, ()):
                    out.append(Correspondence(e, m.target, SUB, m.confidence, k + 1,
                                              m.method, m.target_ontology, via=a))
                frontier.append((a, k + 1))
    return out


# ===========================================================================
# (ii) Generality — language-model backends
# ===========================================================================

class LevelClassifier(Protocol):
    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]: ...


class ZeroShotNLIBackend:
    """p_c(ℓ_k) from a zero-shot NLI model, hypothesis 'This text is {ℓ_k}.'"""

    def __init__(self, model: str = DEFAULT_NLI_MODEL, levels: Sequence[str] = SPECIFICITY_LEVELS,
                 hypothesis_template: str = HYPOTHESIS_TEMPLATE, batch_size: int = 8,
                 device: int | str | None = None):
        from transformers import pipeline
        kw = {"model": model}
        if device is not None:
            kw["device"] = device
        from ...quiet import quiet_transformers
        quiet_transformers()
        self.pipe = pipeline("zero-shot-classification", **kw)
        self.levels, self.template, self.batch_size = list(levels), hypothesis_template, batch_size

    def predict_proba(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        outs = self.pipe(list(texts), candidate_labels=self.levels,
                         hypothesis_template=self.template, multi_label=False,
                         batch_size=self.batch_size)
        if isinstance(outs, dict):
            outs = [outs]
        return [[float(dict(zip(o["labels"], o["scores"]))[l]) for l in self.levels] for o in outs]


class CallableBackend:
    """Wrap any function text -> probabilities over ℓ_1..ℓ_K (e.g. a prompted LLM)."""

    def __init__(self, fn: Callable[[str], Sequence[float]]):
        self.fn = fn

    def predict_proba(self, texts):
        return [list(self.fn(t)) for t in texts]


def generality_score(classes: Sequence[str], definitions: dict[str, str],
                     backend: LevelClassifier) -> tuple[float, dict[str, dict]]:
    """Gen(O_D) = (1/|C_D|) Σ_{c ∈ C_D^def} gen(c); gen(c) = 0 without def.  [eq:gen]"""
    details: dict[str, dict] = {}
    if not classes:
        return 0.0, details
    texts = sorted({definitions[c].strip() for c in classes if definitions.get(c, "").strip()})
    probs = dict(zip(texts, backend.predict_proba(texts)))
    for c in classes:
        t = definitions.get(c, "").strip()
        if t:
            p = probs[t]
            details[c] = {"definition": t, "gen": class_generality(p),
                          "predicted_level": max(range(len(p)), key=p.__getitem__) + 1,
                          **{f"p_l{k + 1}": v for k, v in enumerate(p)}}
        else:
            details[c] = {"definition": "", "gen": 0.0, "predicted_level": None}
    return sum(d["gen"] for d in details.values()) / len(classes), details


# ===========================================================================
# End-to-end evaluation
# ===========================================================================

def evaluate(
    onto: OntologyEntities,
    sources: Sequence[ReferenceSource],
    backend: LevelClassifier | None,
    domains: Sequence[str] = (),
    top_n: int = DEFAULT_TOP_N,
    exclude: Sequence[str] = (),
    tau: float = DEFAULT_TAU,
    rho_sub: float = DEFAULT_RHO_SUB,
    gamma: float = DEFAULT_GAMMA,
    k_max: int = DEFAULT_K_MAX,
    beta: float = DEFAULT_BETA,
    theta: float = DEFAULT_THETA,
    verbose: bool = True,
) -> tuple[CDIResult, list[dict], list[dict], list[Correspondence]]:
    """Returns (summary, per-entity rows, per-ontology rows, all correspondences M)."""
    # 𝒪 and k = 0 correspondences                       [par:reference], (i)(a)-(b)
    base, identities, table = build_reference_set(onto, sources, domains, top_n, exclude, verbose)
    # (i)(c) traversal
    inferred = infer_by_traversal(onto, base, identities, k_max)
    M = base + inferred

    # [eq:ae], [eq:align]
    strengths = alignment_strengths(onto.entities, M, tau, rho_sub, gamma)
    align = alignment_score(strengths)
    by_onto: dict[str, list[Correspondence]] = defaultdict(list)
    for m in M:
        by_onto[m.target_ontology].append(m)
    for oid, inf in table.items():
        if inf.status == "selected":
            inf.align_d = alignment_score(
                alignment_strengths(onto.entities, by_onto.get(oid, []), tau, rho_sub, gamma))

    # (ii) [eq:genc], [eq:gen]; without a backend only the definition coverage is known
    defs = onto.definitions
    n_def = sum(1 for c in onto.classes if defs.get(c, "").strip())
    cov_def = n_def / len(onto.classes) if onto.classes else 0.0
    if backend is not None:
        gen, gdet = generality_score(onto.classes, defs, backend)
        mean_g = sum(gdet[c]["gen"] for c in onto.classes if gdet[c]["definition"]) / n_def if n_def else 0.0
    else:
        gen, mean_g = None, None
        gdet = {c: {"definition": defs.get(c, ""), "gen": None, "predicted_level": None} for c in onto.classes}

    # [eq:cdi]
    cdi = cdi_score(align, gen, beta) if gen is not None else None
    result = CDIResult(
        align=align, gen=gen, cdi=cdi, interoperable=cdi is not None and cdi >= theta,
        definition_coverage=cov_def, mean_definition_generality=mean_g,
        n_entities=len(onto.entities), n_aligned_entities=sum(a > 0 for a, _ in strengths.values()),
        n_classes=len(onto.classes), n_defined_classes=n_def,
        reference_ontologies=sorted(o for o, i in table.items() if i.status == "selected"),
        params=dict(tau=tau, c_lex=getattr(sources[0], "c_lex", None) if sources else None,
                    rho_sub=rho_sub, gamma=gamma, k_max=k_max, top_n=top_n, beta=beta,
                    theta=theta, domains=list(domains), namespace=list(onto.namespace)),
    )

    cls = set(onto.classes)
    entity_rows = []
    for e in onto.entities:
        a, m = strengths[e]
        d = gdet.get(e, {})
        entity_rows.append({
            "entity": e, "label": onto.terms[e].label, "is_class": e in cls,
            "a_e": round(a, 4), "aligned": a > 0,
            "best_target": m.target if m else "", "relation": m.relation if m else "",
            "confidence": m.confidence if m else "", "depth": m.depth if m else "",
            "method": m.method if m else "", "target_ontology": m.target_ontology if m else "",
            "via": m.via if m else "", "best_strength": round(strength(m, rho_sub, gamma), 4) if m else "",
            "gen": round(d["gen"], 4) if e in cls and d.get("gen") is not None else "",
            "predicted_level": d.get("predicted_level", "") if e in cls else "",
            **{f"p_l{k + 1}": (round(d[f"p_l{k + 1}"], 4) if f"p_l{k + 1}" in d else "")
               for k in range(len(SPECIFICITY_LEVELS))},
            "definition": d.get("definition", ""),
        })
    onto_rows = [asdict(i) for i in sorted(table.values(),
                                           key=lambda i: (i.status != "selected", -i.coverage, i.id))]
    return result, entity_rows, onto_rows, M
