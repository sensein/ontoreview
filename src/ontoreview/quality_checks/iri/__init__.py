"""IRI checks: syntax, ontology header, ontology-IRI resolution and external-term validation.

* :mod:`.http`: IRI syntax, retrieval with RDF content negotiation, safe parsing.
* :mod:`.store`: SQLite term snapshots (bundled, read-only + writable user cache) and run tracking.
* :mod:`.providers`: exact-IRI lookups in OLS and BioPortal.
* :mod:`.validate`: finds external class/property references and validates them
  (local SQLite → OLS → BioPortal → direct download, with caching).

Adapted from the ``ontology_quality`` reference implementation. The report (metrics + findings) is
built by :mod:`ontoreview.report.iri`. Every run is recorded in the writable database.
"""

from __future__ import annotations

import json
import logging
import re
import time
from importlib.resources import as_file, files
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ...report.iri import iri_report
from ...report.models import ExternalReport
from .http import host_of, iri_issue, ontology_headers, resolve_ontology_iri
from .store import TermStore, age_days, default_cache_path
from .validate import Validator, download_graph, references

log = logging.getLogger(__name__)

DATA = "data/iri"


def data_file(name: str):
    return files("ontoreview").joinpath(f"{DATA}/{name}")


def load_catalog(path: str | Path | None = None) -> list[dict]:
    text = Path(path).expanduser().read_text("utf-8") if path else data_file("ontologies.json").read_text("utf-8")
    return json.loads(text)["ontologies"]


def cache_path(ev=None) -> Path:
    custom = getattr(ev, "iri_db", None) if ev is not None else None
    return Path(custom).expanduser() if custom else default_cache_path()


def _ns(iri: str) -> str | None:
    m = re.match(r"^(.*[#/])[^#/]+$", iri)
    return m.group(1) if m else None


def local_namespaces(graph: Graph, namespace: str | None, extra: list[str] | None = None,
                     catalog: list[dict] | None = None) -> list[str]:
    """Namespaces owned by this ontology, which are not checked as external.

    The detected namespace, configured ones, the ontology IRI's, plus every namespace in which this
    ontology declares terms *on the same host* as its ontology IRI / namespace, unless the namespace
    belongs to a catalogued vocabulary (e.g. OBO ontologies reusing BFO on purl.obolibrary.org).
    """
    out = [ns for ns in [namespace, *(extra or [])] if ns]
    headers = ontology_headers(graph)
    for h in headers:
        base = h.rstrip("#/")
        out += [base + "#", base + "/"]
    hosts = {host_of(x) for x in [*headers, *out] if host_of(x)}
    known = [e["term_namespace"] for e in (catalog or [])]
    for s in set(graph.subjects(RDF.type, None)) - {URIRef(h) for h in headers}:
        if isinstance(s, URIRef) and host_of(str(s)) in hosts:
            ns = _ns(str(s))
            if ns and not any(str(s).startswith(k) for k in known):
                out.append(ns)
    return [ns for ns in dict.fromkeys(out) if not iri_issue(ns)]


def run_iri_checks(graph: Graph, ev, source: str | None = None, namespace: str | None = None) -> ExternalReport:
    """Run all IRI checks as configured in ``[evaluation]`` (``ev``) and record the run."""
    log.info("Checking IRIs")
    t0 = time.perf_counter()
    offline = not ev.iri_network
    timeout, max_mb = float(ev.iri_timeout), float(ev.iri_max_mb)
    headers = ontology_headers(graph)
    ontology_iri = headers[0] if len(headers) == 1 else None

    # 1. syntax of every IRI in the graph
    all_iris = {str(t) for triple in graph for t in triple if isinstance(t, URIRef)}
    invalid = sorted((i, iri_issue(i)) for i in all_iris if iri_issue(i))

    # 2. header: version IRIs
    version_iris = sorted({str(o) for h in headers for o in graph.objects(URIRef(h), OWL.versionIRI)})

    # 3. does the ontology IRI resolve to RDF describing this ontology?
    resolution = None
    if ontology_iri and ev.iri_resolve and not offline and ontology_iri.startswith(("http://", "https://")):
        resolution = resolve_ontology_iri(ontology_iri, timeout, int(max_mb * 1024 * 1024))

    # 4. external class/property references
    results: list[dict] = []
    mismatches: list[dict] = []
    db = cache_path(ev)
    run_id, error, locals_ = None, None, []
    try:
        catalog = load_catalog(ev.iri_catalog)
        locals_ = local_namespaces(graph, namespace, ev.iri_local_namespaces, catalog)
        refs = references(graph, locals_)
        with as_file(data_file("top_terms.sqlite3")) as bundle_path:
            bundle, cache = TermStore(bundle_path, readonly=True), TermStore(db)
            try:
                settings = {"offline": offline, "refresh": ev.iri_refresh, "repositories": ev.iri_repositories,
                            "resolve": ev.iri_resolve, "local_namespaces": locals_, "budget": ev.iri_budget}
                run_id = cache.start_run(source, ontology_iri, settings)
                validator = Validator(bundle, cache, catalog, offline=offline, refresh=ev.iri_refresh and not offline,
                                      timeout=timeout, max_mb=max_mb,
                                      providers=None if ev.iri_repositories else [], budget=ev.iri_budget,
                                      max_age_days=ev.iri_cache_days)
                for iri, roles in sorted(refs.items()):
                    results.append(validator.validate(iri, roles))
                mismatches = release_mismatches(graph, results)
                summary = _summary(results, invalid, len(all_iris))
                cache.finish_run(run_id, results, summary)
            finally:
                bundle.close()
                cache.close()
    except Exception as e:  # noqa: BLE001 - the rest of the review must still be produced
        error = f"{type(e).__name__}: {e}"
        log.warning("IRI term validation failed: %s", error)
    return iri_report(
        all_iris=len(all_iris), invalid=invalid, headers=headers, version_iris=version_iris,
        resolution=resolution, offline=offline, results=results, local_namespaces=locals_,
        run_id=run_id, db=str(db), seconds=time.perf_counter() - t0, error=error,
        resolve_enabled=bool(ev.iri_resolve), mismatches=mismatches, max_age_days=ev.iri_cache_days)


def _stem(iri: str) -> str:
    s = iri.rstrip("#/")
    for ext in (".owl", ".ttl", ".rdf", ".nt", ".jsonld", ".xml"):
        if s.endswith(ext):
            return s[: -len(ext)]
    return s


def release_mismatches(graph: Graph, results: list[dict]) -> list[dict]:
    """External terms verified against a different release than the one this ontology imports.

    An ``owl:imports`` IRI counts as a release of a vocabulary when it starts with the vocabulary's
    ontology IRI (without trailing ``#``/``/`` or file extension) but is not that IRI itself, e.g.
    ``…/obo/go/releases/2024-01-01/go.owl`` for ``…/obo/go.owl``.
    """
    imports = sorted({str(o) for o in graph.objects(None, OWL.imports) if isinstance(o, URIRef)})
    if not imports:
        return []
    out = []
    for r in results:
        rel = r.get("release") or {}
        onto, version = rel.get("ontology_iri"), rel.get("version_iri")
        if not onto or not version:
            continue
        stem = _stem(onto)
        for imp in imports:
            if imp.startswith(stem) and imp not in (onto, version) and _stem(imp) != stem:
                out.append({"iri": r["iri"], "imports": imp, "verified_against": version, "source": rel.get("source")})
    return out


def _summary(results: list[dict], invalid, n_iris: int) -> dict:
    counts: dict[str, int] = {}
    sources: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        src = r.get("snapshot") or "none"
        sources[src] = sources.get(src, 0) + 1
    return {"iris": n_iris, "invalid_iris": len(invalid), "external_terms": len(results),
            "statuses": counts, "sources": sources, "stale": sum(1 for r in results if r.get("stale")),
            "releases": sorted({(r.get("release") or {}).get("version_iri") or (r.get("release") or {}).get("version")
                                or "" for r in results} - {""})}


def check_iris(graph: Graph, ev, source: str | None = None, namespace: str | None = None) -> ExternalReport | None:
    """Run the IRI checks unless turned off (``evaluation.iri_checks = "off"``)."""
    if ev.iri_checks == "off":
        return None
    return run_iri_checks(graph, ev, source, namespace)


# ------------------------------------------------------------------ term database (app page / CLI)
def open_stores(db: str | Path | None = None):
    """(bundle, cache) stores; the caller closes both."""
    bundle_res = data_file("top_terms.sqlite3")
    with as_file(bundle_res) as bundle_path:
        return TermStore(bundle_path, readonly=True), TermStore(Path(db) if db else default_cache_path())


def list_documents(db: str | Path | None = None) -> list[dict]:
    """Every stored vocabulary snapshot: where it is (bundled / cached), its source and term count."""
    bundle, cache = open_stores(db)
    try:
        out = []
        for store, where in ((bundle, "bundled"), (cache, "cache")):
            for r in store.db.execute(
                    "SELECT d.key, d.source_url, d.fetched_at, d.sha256, d.metadata, count(t.iri) AS terms "
                    "FROM documents d LEFT JOIN terms t ON t.document_key = d.key GROUP BY d.key ORDER BY d.key"):
                meta = json.loads(r["metadata"] or "{}")
                out.append({"key": r["key"], "where": where, "source_url": r["source_url"],
                            "fetched_at": r["fetched_at"], "sha256": r["sha256"], "terms": r["terms"],
                            "age_days": age_days(r["fetched_at"]),
                            "ontology_iris": meta.get("ontology_iris", []), "version_iris": meta.get("version_iris", []),
                            "licenses": meta.get("licenses", [])})
        return out
    finally:
        bundle.close()
        cache.close()


def search_terms(query: str, db: str | Path | None = None, limit: int = 200, document: str | None = None) -> list[dict]:
    """Terms whose IRI or label contains ``query`` (case-insensitive), in bundled and cached snapshots."""
    q = f"%{query.strip().lower()}%"
    bundle, cache = open_stores(db)
    try:
        out = []
        for store, where in ((cache, "cache"), (bundle, "bundled")):
            sql = ("SELECT document_key, iri, types, labels, deprecated FROM terms "
                   "WHERE (lower(iri) LIKE ? OR lower(labels) LIKE ?)" + (" AND document_key = ?" if document else "")
                   + " ORDER BY iri LIMIT ?")
            args = (q, q, document, limit) if document else (q, q, limit)
            for r in store.db.execute(sql, args):
                out.append({"iri": r["iri"], "document": r["document_key"], "where": where,
                            "types": json.loads(r["types"]), "labels": json.loads(r["labels"]),
                            "deprecated": bool(r["deprecated"])})
        return out[:limit]
    finally:
        bundle.close()
        cache.close()


def add_document(*, url: str | None = None, path: str | Path | None = None, key: str | None = None,
                 db: str | Path | None = None, timeout: float = 30, max_mb: float = 50) -> dict:
    """Index an ontology into the writable database, from a URL (content negotiation) or a local file.

    ``key`` defaults to the document's ``owl:Ontology`` IRI (else the URL / file URI). Returns a
    summary dict. Re-adding the same key replaces its terms.
    """
    if bool(url) == bool(path):
        raise ValueError("Give either a URL or a file")
    if url:
        issue = iri_issue(url, http_only=True)
        if issue:
            raise ValueError(f"Not a usable URL: {issue}")
        graph, final_url, body = download_graph([url], timeout, max_mb)
        source = final_url
    else:
        p = Path(path).expanduser()
        body = p.read_bytes()
        graph = Graph()
        try:
            graph.parse(p)          # format from the extension (Turtle, RDF/XML, N-Triples, JSON-LD, …)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Could not parse {p.name}: {e}") from None
        source = p.resolve().as_uri()
    headers = sorted(str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef))
    key = key or (headers[0] if headers else source)
    cache = TermStore(Path(db) if db else default_cache_path())
    try:
        n = cache.save(key, graph, source, body)
    finally:
        cache.close()
    if not n:
        raise ValueError("No typed terms (classes, properties, individuals) found in that document")
    return {"key": key, "source_url": source, "terms": n, "ontology_iris": headers}


def refresh_document(key: str, db: str | Path | None = None, timeout: float = 30, max_mb: float = 50) -> dict:
    """Fetch a stored vocabulary again (bundled or cached) into the writable database."""
    bundle, cache = open_stores(db)
    try:
        doc = cache.document(key) or bundle.document(key)
        if doc is None:
            raise ValueError(f"No stored vocabulary {key}")
        entry = next((e for e in load_catalog() if e["ontology_iri"] == key), None)
        v = Validator(bundle, cache, load_catalog(), timeout=timeout, max_mb=max_mb, providers=[])
        err = v._refresh_document(key, entry, doc)
        if err:
            raise ValueError(err)
        new = cache.document(key)
        n = cache.db.execute("SELECT count(*) FROM terms WHERE document_key=?", (key,)).fetchone()[0]
        return {"key": key, "terms": n, "source_url": new["source_url"], "fetched_at": new["fetched_at"],
                "changed": new["sha256"] != doc["sha256"]}
    finally:
        bundle.close()
        cache.close()


def remove_document(key: str, db: str | Path | None = None) -> bool:
    """Remove a cached snapshot (bundled snapshots are read-only)."""
    cache = TermStore(Path(db) if db else default_cache_path())
    try:
        with cache.db:
            cur = cache.db.execute("DELETE FROM documents WHERE key=?", (key,))
        return cur.rowcount > 0
    finally:
        cache.close()


def recent_runs(db: str | Path | None = None, limit: int = 50) -> list[dict]:
    cache = TermStore(Path(db) if db else default_cache_path())
    try:
        return cache.recent_runs(limit)
    finally:
        cache.close()


__all__ = ["add_document", "check_iris", "list_documents", "load_catalog", "recent_runs", "refresh_document",
           "release_mismatches", "remove_document",
           "run_iri_checks", "search_terms"]
