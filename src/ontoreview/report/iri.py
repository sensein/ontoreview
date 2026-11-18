"""IRI check results → metrics (scorecard) and findings for the review."""

from __future__ import annotations

import re

from .models import ExternalItem, new_report, sort_items

STATUS_TEXT = {"valid": "valid", "deprecated": "deprecated", "type_not_declared": "wrong type",
               "unverified": "unverified", "invalid_iri": "malformed"}
SOURCE_TEXT = {"bundle": "bundled", "cache": "cache", "download": "downloaded", "refreshed": "refreshed", "ols": "OLS",
               "bioportal": "BioPortal", "none": "no source"}


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def iri_report(*, all_iris: int, invalid, headers, version_iris, resolution, offline, results, local_namespaces,
               run_id, db, seconds, error=None, resolve_enabled=True, mismatches=None, max_age_days=30,
               settings=None, checked_at=None):
    metrics, items = [], []

    def metric(title, value, status, about, metric_id):
        metrics.append({"group": "IRI", "metric": metric_id, "title": title, "value": value,
                        "status": status, "about": about})

    # syntax
    metric("IRI syntax", "No malformed IRIs" if not invalid else f"{_plural(len(invalid), 'malformed IRI')} of {all_iris}",
           "ok" if not invalid else "error", f"All {all_iris} IRIs checked for spaces, forbidden characters, "
           "bad percent escapes, missing scheme or host", "syntax")
    if invalid:
        items.append(ExternalItem("invalid_iri", "Malformed IRIs", "error",
                                  "These IRIs contain spaces, forbidden characters, invalid percent escapes or "
                                  "lack a scheme or host. Most RDF tools reject or mangle them.",
                                  affected=[i for i, _ in invalid],
                                  note="; ".join(f"{i}: {why}" for i, why in invalid[:5])[:300]))

    # header
    if len(headers) == 1:
        metric("Ontology header", headers[0], "ok", "Exactly one named owl:Ontology", "header")
    elif not headers:
        metric("Ontology header", "None", "warn", "Exactly one named owl:Ontology", "header")
        items.append(ExternalItem("no_ontology_header", "No owl:Ontology header", "warning",
                                  "Without a named owl:Ontology the ontology has no identifier to cite, version or import."))
    else:
        metric("Ontology header", f"{len(headers)} headers", "warn", "Exactly one named owl:Ontology", "header")
        items.append(ExternalItem("multiple_ontology_headers", "Several owl:Ontology headers", "warning",
                                  "One document should declare one ontology.", affected=headers))
    if headers:
        same = [v for v in version_iris if v in headers]
        metric("Version IRI", version_iris[0] if len(version_iris) == 1 else
               (f"{len(version_iris)} version IRIs" if version_iris else "None"),
               "ok" if version_iris and not same else "info", "owl:versionIRI, distinct from the ontology IRI", "version")
        if same:
            items.append(ExternalItem("version_iri_equals_ontology_iri", "Version IRI equals the ontology IRI", "info",
                                      "owl:versionIRI should identify one release, e.g. …/1.2.0/, not the ontology itself.",
                                      affected=same))

    # resolution
    if resolution is None:
        why = ("network lookups are off" if offline else "turned off" if not resolve_enabled
               else "no single http(s) ontology IRI")
        metric("Ontology IRI resolves", f"Not checked ({why})", "skipped", "The ontology IRI returns RDF "
               "(content negotiation) whose header matches it", "resolves")
    else:
        st, ident = resolution["status"], resolution.get("identity")
        if st == "rdf" and ident == "match":
            value, status = f"Yes ({resolution.get('format')}, HTTP {resolution.get('http_status')})", "ok"
        elif st == "rdf":
            value, status = "Returns RDF, but its header is " + ("different" if ident == "mismatch" else "missing"), "warn"
        elif st == "html_only":
            value, status = "Returns an HTML page, not RDF", "warn"
        else:
            value, status = "Not reachable", "warn"
        metric("Ontology IRI resolves", value, status, "The ontology IRI returns RDF (content negotiation) whose "
               "header matches it", "resolves")
        if status != "ok":
            items.append(ExternalItem("ontology_iri_not_resolvable", "Ontology IRI does not resolve to this ontology",
                                      "info", "Published ontologies should return RDF for their IRI (content "
                                      "negotiation). Expected for unpublished or in-development ontologies.",
                                      affected=[resolution["iri"]],
                                      note=(resolution.get("detail") or (f"final URL {resolution.get('final_url')}"
                                                                         if resolution.get("final_url") else ""))[:300]))

    # external terms
    by: dict[str, list[dict]] = {}
    for r in results:
        by.setdefault(r["status"], []).append(r)
    if error:
        metric("External terms", f"Could not run: {error}", "error", "Classes and properties reused from other "
               "vocabularies exist there, with the expected type, and are not deprecated", "external")
    elif not results:
        metric("External terms", "None referenced", "ok", "Classes and properties reused from other vocabularies",
               "external")
    else:
        parts = [f"{len(by[s])} {STATUS_TEXT.get(s, s)}" for s in ("valid", "deprecated", "type_not_declared",
                                                                    "unverified") if by.get(s)]
        bad = by.get("deprecated") or by.get("type_not_declared")
        metric("External terms", f"{len(results)} checked: " + ", ".join(parts),
               "warn" if bad else "info" if by.get("unverified") else "ok",
               "Classes and properties reused from other vocabularies exist there, with the expected type, and are "
               "not deprecated", "external")
        sources: dict[str, int] = {}
        for r in results:
            if r["status"] == "invalid_iri":
                continue
            s = r.get("snapshot") if r["status"] != "unverified" else "none"
            sources[s or "none"] = sources.get(s or "none", 0) + 1
        metric("Lookup sources", ", ".join(f"{SOURCE_TEXT.get(k, k)} {v}" for k, v in sorted(sources.items())),
               "info", "Where each external term was verified: bundled SQLite, local cache, OLS, BioPortal, "
               "or a direct download", "sources")
    if results and not error:
        stale = [r for r in results if r.get("stale")]
        limit = f"{max_age_days:g} days" if max_age_days else "no limit"
        metric("Freshness", "All lookups current" if not stale else
               f"{len(stale)} term{'s' if len(stale) != 1 else ''} from entries older than {limit}",
               "ok" if not stale else "info", f"Cached and bundled entries are refreshed after {limit}; entries "
               "that could not be refreshed are used but flagged", "freshness")
        releases: dict[str, int] = {}
        for r in results:
            rel = r.get("release") or {}
            name = rel.get("version_iri") or (f"{rel.get('ontology')} {rel.get('version')}".strip()
                                              if rel.get("version") else None)
            if name:
                releases[name] = releases.get(name, 0) + 1
        if releases:
            shown = ", ".join(f"{k} ({v})" for k, v in sorted(releases.items(), key=lambda kv: -kv[1])[:4])
            metric("Releases verified against", shown + (f" and {len(releases) - 4} more" if len(releases) > 4 else ""),
                   "warn" if mismatches else "info", "The vocabulary release (version IRI / version) each external "
                   "term was checked against", "releases")
        if stale:
            items.append(ExternalItem("stale_term_lookup", "Verified from expired cache entries", "info",
                                      f"These terms were confirmed by entries older than {limit} that could not be "
                                      "refreshed (offline, time budget, or the source did not answer).",
                                      affected=[r["iri"] for r in stale],
                                      note="; ".join(f"{r['iri'].rsplit('/', 1)[-1].rsplit('#', 1)[-1]}: "
                                                     f"{r.get('age_days', '?')} days" for r in stale[:8])[:300]))
    if mismatches:
        items.append(ExternalItem("release_mismatch", "Imported release differs from the release checked", "warning",
                                  "This ontology imports a specific release of a vocabulary, but the terms were "
                                  "verified against another release. Check the terms against the imported release, "
                                  "or update the import.", affected=sorted({m["iri"] for m in mismatches}),
                                  note="; ".join(sorted({f"imports {m['imports']}, checked {m['verified_against']}"
                                                         for m in mismatches}))[:300]))
    if by.get("deprecated"):
        items.append(ExternalItem("deprecated_external_term", "Deprecated external terms", "warning",
                                  "These reused terms are marked deprecated by their source. Use the replacement.",
                                  affected=[r["iri"] for r in by["deprecated"]]))
    if by.get("type_not_declared"):
        wrong = by["type_not_declared"]
        items.append(ExternalItem("external_term_wrong_type", "External terms used as a different kind of term",
                                  "warning", "Used as a class or property here, but not declared as such in the "
                                  "source vocabulary.", affected=[r["iri"] for r in wrong],
                                  note="; ".join(f"{r['iri'].rsplit('/', 1)[-1].rsplit('#', 1)[-1]}: expected "
                                                 f"{', '.join(r.get('missing_expected_types', []))}" for r in wrong[:8])[:300]))
    if by.get("unverified"):
        reasons: dict[str, int] = {}
        for r in by["unverified"]:
            d = re.sub(r"^\S+: ", "", (r.get("detail") or "not found").split(";")[0])
            d = re.sub(r" for url: \S+", "", d)[:70]
            reasons[d] = reasons.get(d, 0) + 1
        items.append(ExternalItem("unverified_external_term", "External terms that could not be verified", "info",
                                  "No checked source confirmed these terms. Coverage is incomplete, so this is not "
                                  "proof that they do not exist. Add the vocabulary on the IRI database page, or "
                                  "check that its IRIs resolve.", affected=[r["iri"] for r in by["unverified"]],
                                  note="; ".join(f"{k} ({v})" for k, v in reasons.items())[:300]))

    rep = new_report("iri", sort_items(items))
    rep.metrics = metrics
    rep.provenance = iri_provenance(results, run_id=run_id, db=db, settings=settings, checked_at=checked_at,
                                    local_namespaces=local_namespaces)
    run = f"Run #{run_id} recorded in {db}." if run_id else ""
    shown = ", ".join(local_namespaces[:3]) + (f" and {len(local_namespaces) - 3} more" if len(local_namespaces) > 3 else "")
    ns = f"Own namespaces (not checked as external): {shown or 'none detected'}."
    rep.scope = " ".join(x for x in (f"{seconds:.1f}s.", ns, run) if x)
    return rep


def _release_key(rel: dict) -> tuple:
    # documents of one vocabulary (e.g. per-term CIDOC CRM files) are one release when versions agree
    return (rel.get("source"), rel.get("ontology_iri") or rel.get("ontology") or rel.get("namespace"),
            rel.get("version_iri"), rel.get("version"))


def iri_provenance(results, *, run_id=None, db=None, settings=None, checked_at=None, local_namespaces=None) -> dict:
    """A self-contained record of the IRI check, written into the documentation output.

    It names the exact release (version IRI or version, and the SHA-256, URL and retrieval time of
    every snapshot document) each external term was verified against, so the published docs keep
    their provenance even after the local cache expires or is refreshed. Terms verified from records
    that carry no release information are listed as such, never dropped.
    """
    releases: dict[tuple, dict] = {}
    unrecorded: dict[str, int] = {}
    terms = []
    for r in results:
        rel = r.get("release") or {}
        if rel:
            e = releases.setdefault(_release_key(rel), {
                "title": rel.get("title"), "source": rel.get("source"),
                "ontology_iri": rel.get("ontology_iri") or rel.get("namespace"), "ontology": rel.get("ontology"),
                "version_iri": rel.get("version_iri"), "version": rel.get("version"),
                "retrieved": rel.get("fetched_at") or rel.get("loaded") or rel.get("released"),
                "terms": 0, "documents": {}})
            e["terms"] += 1
            e["title"] = e["title"] or rel.get("title")
            if rel.get("sha256"):
                e["documents"][rel.get("document") or rel.get("source_url")] = {
                    "source_url": rel.get("source_url"), "sha256": rel["sha256"], "retrieved": rel.get("fetched_at")}
        elif r.get("status") in ("valid", "deprecated", "type_not_declared"):
            src = r.get("snapshot") or r.get("provider") or "unknown"
            unrecorded[src] = unrecorded.get(src, 0) + 1
        terms.append({k: r.get(k) for k in ("iri", "roles", "status", "snapshot", "stale", "age_days", "detail")
                      if r.get(k) is not None} | ({"release": rel} if rel else {})
                     | ({"attempts": r["attempts"]} if r.get("attempts") else {}))
    out = []
    for e in releases.values():
        docs = list(e.pop("documents").values())
        if len(docs) == 1:
            e.update(sha256=docs[0]["sha256"], source_url=docs[0]["source_url"])
        elif docs:
            e.update(documents=docs, sha256=None, source_url=None)
        out.append(e)
    for src, n in unrecorded.items():
        out.append({"title": None, "source": src, "ontology_iri": None, "version_iri": None, "version": None,
                    "retrieved": None, "terms": n, "release_recorded": False,
                    "note": "verified from a cached record that predates release tracking; refresh to record it"})
    return {"checked_at": checked_at, "run_id": run_id, "database": db, "settings": settings or {},
            "own_namespaces": local_namespaces or [],
            "releases": sorted(out, key=lambda x: (x.get("release_recorded") is False, -x["terms"],
                                                   str(x.get("title") or x.get("ontology_iri")))),
            "terms": terms}


def add_iri_provenance(g, provenance: dict, activity) -> None:
    """PROV-O: the build activity used each vocabulary release the IRI check verified terms against."""
    import hashlib

    from rdflib import Literal, URIRef
    from rdflib.namespace import DCTERMS, PROV, RDF, RDFS, XSD

    for rel in provenance.get("releases", []):
        if rel.get("release_recorded") is False:
            continue
        ident = rel.get("version_iri") or (f"urn:sha256:{rel['sha256']}" if rel.get("sha256") else None)
        if not ident:
            basis = f"{rel.get('source')}|{rel.get('ontology') or rel.get('ontology_iri')}|{rel.get('version')}"
            ident = "urn:ontoreview:release:" + hashlib.sha256(basis.encode()).hexdigest()[:16]
        node = URIRef(ident)
        g.add((activity, PROV.used, node))
        g.add((node, RDF.type, PROV.Entity))
        if rel.get("ontology_iri") and str(rel["ontology_iri"]).startswith(("http://", "https://")):
            g.add((node, DCTERMS.isVersionOf, URIRef(rel["ontology_iri"])))
        if rel.get("version"):
            g.add((node, DCTERMS.hasVersion, Literal(rel["version"])))
        if rel.get("title"):
            g.add((node, DCTERMS.title, Literal(rel["title"])))
        for doc in rel.get("documents") or [rel]:
            if doc.get("sha256"):
                g.add((node, DCTERMS.identifier, Literal(f"sha256:{doc['sha256']}")))
            if doc.get("source_url"):
                g.add((node, DCTERMS.source, URIRef(doc["source_url"])))
        if rel.get("retrieved"):
            g.add((node, DCTERMS.date, Literal(rel["retrieved"], datatype=XSD.string)))
        g.add((node, RDFS.comment, Literal(f"Release used to verify {rel['terms']} external term(s) "
                                           f"(via {rel.get('source')}).")))


__all__ = ["add_iri_provenance", "iri_provenance", "iri_report"]
