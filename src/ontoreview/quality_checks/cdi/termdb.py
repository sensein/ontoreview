"""The term database in the cross-domain interoperability check.

The CDI check shares the IRI checks' SQLite term database (bundled W3C vocabularies plus the
user's cache, :mod:`ontoreview.quality_checks.iri.store`) and uses it in three ways:

* **First source of correspondences** (:class:`TermDBSource`). Every stored vocabulary is a
  candidate reference ontology (``db:<document key>``), matched like a repository: shared IRIs
  (reuse), exact label matches, and the vocabularies that define the external superclasses the
  ontology points to. It runs before OLS / BioPortal, offline, and needs no key.
* **Reference ontology details** (:class:`InfoCache`). Title, domain and release (ontology IRI,
  version IRI, version, load/release date) of OLS and BioPortal ontologies are read from the
  database first and fetched from the repository only when missing or older than
  ``evaluation.iri_cache_days``; fetched details are saved.
* **Growing the database** (:func:`save_reference`). Reference ontologies the user provides
  (uploads, files, URLs) are indexed as documents, with their SHA-256, source and retrieval time,
  so they are searchable on the Term database page and used first on later runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ..iri.store import age_days, ontology_title
from . import core

log = logging.getLogger(__name__)

ENTITY_TYPES = {str(OWL.Class), str(RDFS.Class), str(OWL.ObjectProperty), str(OWL.DatatypeProperty),
                str(RDF.Property), str(OWL.AnnotationProperty)}
SELF_SHARE = 0.5        # a stored document declaring at least this share of E_D is the ontology itself


def _headers(graph: Graph) -> list[str]:
    return sorted(str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef))


def save_reference(store, path: Path, source_url: str, kind: str) -> dict:
    """Index a user-provided reference ontology into the writable database; return its release record."""
    payload = Path(path).read_bytes()
    g = Graph()
    g.parse(str(path))
    headers = _headers(g)
    key = headers[0] if len(headers) == 1 else source_url
    n = store.save(key, g, source_url, payload)
    doc = store.document(key) or {}
    log.info("CDI: saved reference %s to the term database (%d terms)", key, n)
    rel = {"source": kind, "title": ontology_title(g, headers), "ontology_iri": headers[0] if headers else None,
           "version_iri": next((str(o) for o in g.objects(None, OWL.versionIRI)), None),
           "version": next((str(o) for o in g.objects(None, OWL.versionInfo)), None),
           "sha256": hashlib.sha256(payload).hexdigest(), "source_url": source_url,
           "retrieved": doc.get("fetched_at"), "document": key, "database": "cache", "terms_indexed": n}
    rel = {k: v for k, v in rel.items() if v not in (None, "")}      # only what the file states
    rel["identified_by"] = core.identified_by(rel)
    return rel


def file_release(path: Path, source_url: str, kind: str) -> dict:
    """Release record of a mapping file (SSSOM) used as a reference: what was read, and when."""
    payload = Path(path).read_bytes()
    rel = {"source": kind, "title": Path(path).name, "sha256": hashlib.sha256(payload).hexdigest(),
           "source_url": source_url, "retrieved": datetime.now(timezone.utc).isoformat()}
    rel["identified_by"] = core.identified_by(rel)
    return rel


class InfoCache:
    """Reference ontology details from the database first (fresh within ``max_age_days``)."""

    def __init__(self, store, max_age_days: float = 30):
        self.store, self.max_age = store, max_age_days
        self.hits: set[str] = set()

    def get(self, ontology_id: str) -> dict | None:
        row = self.store.reference_ontology(ontology_id) if self.store else None
        if not row:
            return None
        age = age_days(row["fetched_at"])
        if self.max_age and age is not None and age > self.max_age:
            return None
        self.hits.add(ontology_id)
        return row

    def put(self, info: dict) -> None:
        if self.store:
            try:
                self.store.save_reference_ontology(info)
            except Exception as e:  # noqa: BLE001 - the cache is a convenience
                log.debug("could not cache %s: %s", info.get("id"), e)


class TermDBSource(core.ReferenceSource):
    """Stored vocabularies as reference ontologies (𝒪_disc candidates ``db:<key>``)."""

    given = False
    prefix = "db"

    def __init__(self, stores: list[tuple[str, object]], onto_headers: list[str], exclude_keys: set[str],
                 c_lex: float = core.DEFAULT_C_LEX):
        self.stores, self.onto_headers, self.exclude = stores, set(onto_headers), set(exclude_keys)
        self.c_lex = c_lex
        self.id = "term database"
        self._info: dict[str, core.OntologyInfo] = {}
        self._self: set[str] = set()
        self._defined_in: dict[str, str] = {}
        self.releases: dict[str, dict] = {}

    def _documents(self) -> dict[str, dict]:
        docs = {}
        for where, store in self.stores:
            for row in store.db.execute("SELECT key, source_url, fetched_at, sha256, metadata FROM documents"):
                if row["key"] in self.exclude or row["key"] in docs:
                    continue
                docs[row["key"]] = dict(row) | {"metadata": json.loads(row["metadata"] or "{}"), "where": where}
        return docs

    def correspondences(self, onto: core.OntologyEntities) -> list[core.Correspondence]:
        docs = self._documents()
        ents = set(onto.entities)
        wanted_iris = ents | onto.external_iris()
        wanted_strings = {s for e in onto.entities for strings in onto.terms[e].syn.values() for s in strings}
        iri_docs: dict[str, list[str]] = {}
        by_string: dict[str, list[tuple[str, str]]] = {}
        declared: dict[str, set[str]] = {}
        for _, store in self.stores:
            for row in store.db.execute("SELECT document_key, iri, types, labels FROM terms"):
                key, iri = row["document_key"], row["iri"]
                if key not in docs or not set(json.loads(row["types"])) & ENTITY_TYPES:
                    continue
                if iri in wanted_iris:
                    iri_docs.setdefault(iri, []).append(key)
                    if iri in ents:
                        declared.setdefault(key, set()).add(iri)
                for label in json.loads(row["labels"]):
                    s = core.normalise(label)
                    if s in wanted_strings:
                        by_string.setdefault(s, []).append((key, iri))
        for key, iris in declared.items():
            meta = docs[key]["metadata"]
            if set(meta.get("ontology_iris") or []) & self.onto_headers or len(iris) >= SELF_SHARE * len(ents):
                self._self.add("db:" + key)
        out: list[core.Correspondence] = []
        for iri, keys in iri_docs.items():
            for key in keys:
                oid = "db:" + key
                if oid in self._self:
                    continue
                if iri in ents:                       # (i)(a) the stored vocabulary reuses e
                    out.append(core.Correspondence(iri, iri, core.EQ, 1.0, 0, "shared-iri", oid))
                else:
                    self._defined_in.setdefault(iri, oid)
        out += core._asserted_direct(onto, self._defined_in, "asserted")
        for e in onto.entities:                       # (i)(b) lexical, Table tab:syn (stored labels: exact)
            for typ_e, strings in onto.terms[e].syn.items():
                for s in strings:
                    for key, iri2 in by_string.get(s, ()):
                        oid = "db:" + key
                        r = core.lexical_relation(typ_e, "exact")
                        if r and iri2 not in ents and oid not in self._self:
                            out.append(core.Correspondence(e, iri2, r, self.c_lex, 0, f"lexical:{typ_e}/exact", oid))
        for oid in {m.target_ontology for m in out} | self._self:
            d = docs[oid[3:]]
            meta = d["metadata"]
            self._info[oid] = core.OntologyInfo(oid, "termdb", title=meta.get("title") or oid[3:], given=False)
            rel = {"source": f"term database ({d['where']})", "title": meta.get("title"), "document": d["key"],
                   "ontology_iri": (meta.get("ontology_iris") or [None])[0],
                   "version_iri": (meta.get("version_iris") or [None])[0], "sha256": d["sha256"],
                   "source_url": d["source_url"], "retrieved": d["fetched_at"]}
            rel = {k: v for k, v in rel.items() if v not in (None, "")}   # older records may lack fields
            rel["identified_by"] = core.identified_by(rel)
            self.releases[oid] = rel
        return out

    def identity_targets(self, onto):
        return [core.Correspondence(x, x, core.EQ, 1.0, 0, "shared-iri", o) for x, o in self._defined_in.items()]

    def self_ontologies(self):
        return set(self._self)

    def info(self):
        return self._info


__all__ = ["InfoCache", "TermDBSource", "file_release", "save_reference"]
