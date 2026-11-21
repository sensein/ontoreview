"""Missed reuse: terms an ontology defines itself that a standard vocabulary already has.

The complement of the IRI checks (which validate the external IRIs an ontology *uses*): here each own
class or property is looked up, by label and by local name, in the term database (the bundled
snapshot of widely reused vocabularies plus the user's cache). A match with another IRI suggests the
term was re-created instead of reused, e.g. a local ``:Person`` next to ``prov:Person``.

Unlike plain name matching, candidates are filtered: deprecated terms are never suggested, a term
already linked to the candidate (equivalence, subclass/subproperty, SKOS mapping) is not reported, and
the candidate's declared type is compared with the local term's kind, so a class named like a standard
*property* is reported as a kind mismatch rather than suggested as a replacement.
Local only: no network access, so the result is deterministic and works offline.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

CLASS_TYPES = {str(OWL.Class), str(RDFS.Class)}
PROPERTY_TYPES = {str(RDF.Property), str(OWL.ObjectProperty), str(OWL.DatatypeProperty),
                  str(OWL.AnnotationProperty)}
CLASS_KINDS = {"class"}
PROPERTY_KINDS = {"object_property", "datatype_property", "annotation_property", "property"}
LINKS = (OWL.equivalentClass, OWL.equivalentProperty, RDFS.subClassOf, RDFS.subPropertyOf, OWL.sameAs,
         SKOS.exactMatch, SKOS.closeMatch, SKOS.broadMatch, SKOS.narrowMatch, SKOS.relatedMatch)
# placeholder domains (RFC 2606) and test IRIs: never a vocabulary to reuse
PLACEHOLDER = re.compile(r"^(https?://([^/]+\.)?example\.(org|com|net)/|urn:|file:)", re.I)
MIN_LENGTH = 4          # shorter names ("id", "age") match too much to be useful
LIMIT = 3


def norm(name: str) -> str:
    """``hasBusinessFunction``, ``has business function`` and ``has_business-function`` → ``hasbusinessfunction``."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return re.sub(r"[^0-9a-z]+", "", s.lower())


def local_name(iri: str) -> str:
    return re.split(r"[/#]", str(iri).rstrip("/#"))[-1]


@dataclass(frozen=True)
class Candidate:
    iri: str
    curie: str
    label: str
    kind: str               # class | property
    via: str                # label | name
    same_kind: bool


def _kind_of(types) -> str | None:
    t = set(types)
    if t & CLASS_TYPES:
        return "class"
    if t & PROPERTY_TYPES:
        return "property"
    return None


@lru_cache(maxsize=4)
def _index(paths: tuple[tuple[str, float], ...]) -> dict[str, list[tuple]]:
    """norm(name) → [(iri, label, kind, via)] over every snapshot in the given databases."""
    idx: dict[str, list[tuple]] = {}
    seen: set[tuple[str, str]] = set()
    for path, _mtime in paths:
        with suppress(sqlite3.Error):
            db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                for iri, types, labels, deprecated in db.execute(
                        "SELECT iri, types, labels, deprecated FROM terms"):
                    kind = _kind_of(json.loads(types or "[]"))
                    if deprecated or kind is None or PLACEHOLDER.match(iri):
                        continue
                    names = [(lab, "label") for lab in json.loads(labels or "[]")] + [(local_name(iri), "name")]
                    for name, via in names:
                        key = norm(name)
                        if len(key) >= MIN_LENGTH and (key, iri) not in seen:
                            seen.add((key, iri))
                            idx.setdefault(key, []).append((iri, str(name), kind, via))
            finally:
                db.close()
    return idx


def term_index(cache: Path | None = None) -> dict[str, list[tuple]]:
    """The index over the bundled snapshot and (if present) the user's cache; rebuilt when either changes."""
    from .iri import data_file
    from .iri.store import default_cache_path
    files = []
    with suppress(Exception):
        files.append(Path(str(data_file("top_terms.sqlite3"))))
    files.append(Path(cache) if cache else default_cache_path())
    key = tuple((str(f), f.stat().st_mtime) for f in files if f.is_file())
    return _index(key)


_NM = Graph(bind_namespaces="rdflib").namespace_manager


def curie(iri: str) -> str:
    with suppress(Exception):
        q = _NM.normalizeUri(URIRef(iri))
        if not q.startswith("<"):
            return q
    return iri


def candidates(term, graph: Graph, own_namespaces: list[str], index: dict) -> list[Candidate]:
    """Standard terms with the same label or local name as ``term`` (best first, at most :data:`LIMIT`)."""
    kind = "class" if term.kind in CLASS_KINDS else "property" if term.kind in PROPERTY_KINDS else None
    if kind is None:
        return []
    names = [(lab, "label") for lang, labs in term.labels.items() if lang in ("", "en", None)
             or lang.startswith("en") for lab in labs]
    names.append((term.local_name or local_name(term.iri), "name"))
    linked = {str(o) for p in LINKS for o in graph.objects(URIRef(term.iri), p)} | \
             {str(s) for p in LINKS for s in graph.subjects(p, URIRef(term.iri))}
    found: dict[str, Candidate] = {}
    for name, via in names:
        for iri, label, ckind, cvia in index.get(norm(name), []):
            if (iri == term.iri or iri in linked or any(iri.startswith(ns) for ns in own_namespaces if ns)
                    or iri in found):
                continue
            found[iri] = Candidate(iri, curie(iri), label, ckind, "label" if "label" in (via, cvia) else "name",
                                   ckind == kind)
    ranked = sorted(found.values(), key=lambda c: (not c.same_kind, c.via != "label", c.curie))
    return ranked[:LIMIT]


__all__ = ["Candidate", "candidates", "curie", "norm", "term_index"]
