"""Validate external class/property references against SQLite snapshots and remote sources.

Adapted from the ``ontology_quality`` reference implementation (``validate_terms.py``). Lookup order:
local SQLite (cached snapshots, the bundled snapshot, cached repository records) → OLS → BioPortal
→ direct RDF download. Successful remote lookups and downloads are cached for later runs. Terms
that no source verifies are ``unverified``, never ``invalid``.

Additions for OntoReview: a per-run time budget for network lookups, and hosts that fail with a
network error are not contacted again during the same run (so one unreachable server cannot add a
timeout per term).
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import urldefrag

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from .http import fetch, host_of, iri_issue, parse_rdf
from .providers import BioPortalProvider, OLSProvider
from .store import age_days

CLASS_TYPES = {str(OWL.Class), str(RDFS.Class)}
PROPERTY_TYPES = {str(RDF.Property), str(OWL.ObjectProperty), str(OWL.DatatypeProperty),
                  str(OWL.AnnotationProperty), str(OWL.OntologyProperty)}
BUILTINS = tuple(map(str, (RDF, RDFS, OWL, XSD)))
NS_MISS_LIMIT = 3


def _namespace(iri: str) -> str:
    m = re.match(r"^(.*[#/])[^#/]+$", iri)
    return m.group(1) if m else iri


def references(graph, local_namespaces) -> dict[str, set[str]]:
    """External IRIs in class/property positions -> expected roles. Built-ins and local terms excluded."""
    refs: dict[str, set[str]] = {}
    skip = BUILTINS + tuple(ns for ns in local_namespaces if ns)

    def add(term, role):
        if isinstance(term, URIRef) and not str(term).startswith(skip):
            refs.setdefault(str(term), set()).add(role)

    for s, p, o in graph:
        add(p, "property")
        if p == RDF.type:
            add(o, "class")
        elif p in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith):
            add(s, "class")
            add(o, "class")
        elif p in (RDFS.domain, RDFS.range, OWL.onClass, OWL.someValuesFrom, OWL.allValuesFrom):
            add(o, "class_or_datatype")
        elif p in (RDFS.subPropertyOf, OWL.equivalentProperty, OWL.inverseOf):
            add(s, "property")
            add(o, "property")
        elif p == OWL.onProperty:
            add(o, "property")
    return refs


def download_graph(urls, timeout=20, max_mb=50, failed_hosts: set[str] | None = None):
    errors = []
    for url in dict.fromkeys(urls):
        if failed_hosts is not None and host_of(url) in failed_hosts:
            errors.append(f"{url}: host unreachable earlier in this run")
            continue
        info, body = fetch(url, timeout, int(max_mb * 1024 * 1024))
        if body is None:
            if failed_hosts is not None and info.get("network_error"):
                failed_hosts.add(host_of(url))
            errors.append(f"{url}: {info.get('error', 'no data')}")
            continue
        try:
            graph, _ = parse_rdf(body, info["final_url"], info.get("content_type", ""))
            return graph, info["final_url"], body
        except ValueError as exc:
            errors.append(f"{url}: {exc}")
    raise ValueError("; ".join(errors))


class Validator:
    def __init__(self, bundle, cache, catalog, offline=False, refresh=False, timeout=20, max_mb=50,
                 providers=None, budget: float | None = None, max_age_days: float | None = 30):
        self.bundle, self.cache, self.catalog = bundle, cache, catalog
        self.offline, self.refresh = offline, refresh
        self.timeout, self.max_mb = timeout, max_mb
        self.attempted: dict[str, str | None] = {}
        self.failed_hosts: set[str] = set()
        self.dead_providers: set[str] = set()
        self.ns_misses: dict[str, int] = {}     # namespace -> repository / download misses this run
        self.deadline = time.monotonic() + budget if budget else None
        self.max_age = max_age_days if max_age_days and max_age_days > 0 else None   # None: never expires
        self.refreshed: dict[str, str | None] = {}   # document key -> error (None = refreshed) this run
        self.providers = [OLSProvider(), BioPortalProvider()] if providers is None else providers

    def _out_of_time(self) -> bool:
        return self.deadline is not None and time.monotonic() > self.deadline

    def _expired(self, fetched_at: str | None) -> float | None:
        """Age in days if older than the configured maximum, else None."""
        age = age_days(fetched_at)
        return age if self.max_age is not None and age is not None and age > self.max_age else None

    def _refresh_document(self, key, entry, document) -> str | None:
        """Re-fetch an expired snapshot into the cache (once per key per run). Returns an error or None."""
        if key in self.refreshed:
            return self.refreshed[key]
        err = None
        try:
            src = document.get("source_url") or ""
            if src.startswith("file://"):
                from pathlib import Path as _P
                from urllib.parse import unquote
                from urllib.parse import urlsplit as _split

                from rdflib import Graph as _G
                path = _P(unquote(_split(src).path))
                body = path.read_bytes()
                graph = _G()
                graph.parse(path)
                self.cache.save(key, graph, src, body)
            else:
                urls = [entry["download_url"], entry["ontology_iri"]] if entry else [src or key]
                graph, url, body = download_graph(urls, self.timeout, self.max_mb, self.failed_hosts)
                self.cache.save(key, graph, url, body)
        except (ValueError, OSError) as exc:
            err = str(exc)[:300]
        except Exception as exc:  # noqa: BLE001 - e.g. a parser error in a re-read local file
            err = f"{type(exc).__name__}: {str(exc)[:280]}"
        self.refreshed[key] = err
        return err

    def validate(self, iri, roles):
        local = self._validate_snapshot(iri, roles, local_only=True)
        if local["status"] in ("valid", "deprecated", "type_not_declared", "invalid_iri"):
            return local
        attempts = [{"provider": "local", "status": local["status"]}]
        stale_record = None
        if not self.refresh:
            cached = self.cache.repository_term(iri, roles)
            if cached:
                age = self._expired(cached.get("fetched_at"))
                if age is None or self.offline or self._out_of_time():
                    extra = {"stale": True, "age_days": round(age, 1)} if age is not None else {}
                    return {**cached, "snapshot": "cache", "attempts": attempts, **extra}
                stale_record = {**cached, "snapshot": "cache", "stale": True, "age_days": round(age, 1)}
                attempts.append({"provider": "cache", "status": f"expired ({age:.0f} days); asking again"})
        if self.offline:
            return {"iri": iri, "roles": sorted(roles), "status": "unverified",
                    "detail": "No matching local declaration; remote sources disabled", "attempts": attempts}
        if self._out_of_time():
            return {"iri": iri, "roles": sorted(roles), "status": "unverified",
                    "detail": "Time budget for network lookups used up", "attempts": attempts}
        ns = _namespace(iri)
        if self.ns_misses.get(ns, 0) >= NS_MISS_LIMIT:
            attempts.append({"provider": "remote", "status": f"skipped ({NS_MISS_LIMIT} misses in this namespace)"})
            return {"iri": iri, "roles": sorted(roles), "status": "unverified",
                    "detail": f"Not found in this namespace's first {NS_MISS_LIMIT} lookups; not looked up again",
                    "attempts": attempts}
        for provider in self.providers:
            if provider.name in self.dead_providers:
                attempts.append({"provider": provider.name, "status": "skipped (unavailable earlier in this run)"})
                continue
            result, attempt = provider.lookup(iri, roles, self.timeout)
            attempts.append(attempt)
            if attempt.get("status") == "unavailable":
                self.dead_providers.add(provider.name)
            if result:
                self.cache.save_repository_term(iri, roles, result)
                return {**result, "attempts": attempts}
        if stale_record is not None:            # repositories did not confirm again: keep the old answer, flagged
            return {**stale_record, "attempts": attempts,
                    "detail": f"Cached repository result is {stale_record['age_days']:.0f} days old; "
                              "could not refresh it"}
        downloaded = self._validate_snapshot(iri, roles, force_download=True)
        attempts.append({"provider": "direct_download", "status": downloaded["status"],
                         **({"detail": downloaded["detail"]} if "detail" in downloaded else {})})
        if downloaded["status"] == "not_declared_in_snapshot":
            downloaded["status"] = "unverified"
            downloaded["detail"] = "No declaration in the checked sources; coverage is incomplete"
        if downloaded["status"] == "unverified":
            self.ns_misses[ns] = self.ns_misses.get(ns, 0) + 1
        return {**downloaded, "attempts": attempts}

    def _validate_snapshot(self, iri, roles, local_only=False, force_download=False):
        result = {"iri": iri, "roles": sorted(roles)}
        issue = iri_issue(iri)
        if issue:
            return {**result, "status": "invalid_iri", "detail": issue}
        matches = [e for e in self.catalog if iri.startswith(e["term_namespace"])]
        entry = max(matches, key=lambda e: len(e["term_namespace"])) if matches else None
        # Unknown slash namespaces are cached per document, never as a complete namespace.
        key = entry["ontology_iri"] if entry else urldefrag(iri)[0]
        store, origin = None, None
        if not self.refresh and not force_download:
            for candidate, label in ((self.cache, "cache"), (self.bundle, "bundle")):
                if candidate is not None and candidate.document(key) and candidate.lookup(key, iri):
                    store, origin = candidate, label
                    break
            if store is None:          # a document added by hand (URL/upload) under any key
                hit = self._lookup_any(iri)
                if hit:
                    store, origin, key = hit
        if store is None:
            if self.offline or local_only:
                return {**result, "status": "unverified", "detail": "No snapshot available offline"}
            if self._out_of_time():
                return {**result, "status": "unverified", "detail": "Time budget for network lookups used up"}
            if key not in self.attempted:
                urls = [entry["download_url"], entry["ontology_iri"]] if entry else [key]
                try:
                    graph, url, body = download_graph(urls, self.timeout, self.max_mb, self.failed_hosts)
                    self.cache.save(key, graph, url, body)
                    self.attempted[key] = None
                except ValueError as exc:
                    self.attempted[key] = str(exc)[:300]
            if self.attempted[key] is not None:
                return {**result, "status": "unverified", "detail": self.attempted[key]}
            store, origin = self.cache, "download"
        document = store.document(key)
        age = self._expired(document["fetched_at"]) if origin in ("cache", "bundle") else None
        if age is not None and not self.offline and not self._out_of_time():
            err = self._refresh_document(key, entry, document)
            if err is None:                      # fresh copy now in the cache
                store, origin = self.cache, "refreshed"
                document = store.document(key)
                age = None
        term = store.lookup(key, iri)
        meta = json.loads(document["metadata"])
        result.update(snapshot=origin, source_url=document["source_url"], fetched_at=document["fetched_at"],
                      sha256=document["sha256"], ontology_metadata=meta,
                      release={"source": origin, "ontology_iri": (meta.get("ontology_iris") or [None])[0],
                               "version_iri": (meta.get("version_iris") or [None])[0], "sha256": document["sha256"],
                               "fetched_at": document["fetched_at"], "source_url": document["source_url"]})
        if age is not None:
            result.update(stale=True, age_days=round(age, 1))
        if term is None:
            return {**result, "status": "not_declared_in_snapshot"}
        types = set(term["types"])
        mismatches = []
        if "class" in roles and not types & CLASS_TYPES:
            mismatches.append("class")
        if "class_or_datatype" in roles and not types & (CLASS_TYPES | {str(RDFS.Datatype)}):
            mismatches.append("class_or_datatype")
        if "property" in roles and not types & PROPERTY_TYPES:
            mismatches.append("property")
        return {**result, "status": "type_not_declared" if mismatches else "deprecated" if term["deprecated"] else "valid",
                "types": term["types"], "labels": term["labels"], "deprecated": term["deprecated"],
                "missing_expected_types": mismatches}

    def _lookup_any(self, iri):
        """A term in any stored document (e.g. one added by URL or upload in the app)."""
        for store, label in ((self.cache, "cache"), (self.bundle, "bundle")):
            if store is None:
                continue
            row = store.db.execute("SELECT document_key FROM terms WHERE iri=? LIMIT 1", (iri,)).fetchone()
            if row:
                return store, label, row[0]
        return None
