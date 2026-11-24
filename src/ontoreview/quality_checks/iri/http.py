"""IRI syntax, HTTP retrieval with RDF content negotiation, and safe RDF parsing.

Adapted from the ``ontology_quality`` reference implementation (``check_ontologies.py``).
IRI syntax is validated against the full RFC 3987 grammar (:mod:`.rfc3987`).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from . import rfc3987

ACCEPT = "text/turtle, application/rdf+xml;q=0.9, application/n-triples;q=0.8"
USER_AGENT = "ontoreview (ontology documentation; IRI checks)"


def iri_issue(value, http_only: bool = False) -> str | None:
    """Why ``value`` is not a valid absolute IRI (RFC 3987 grammar + web checks), or None."""
    return rfc3987.check(value, http_only)


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def fetch(url: str, timeout: float, max_bytes: int) -> tuple[dict, bytes | None]:
    """GET with RDF content negotiation; follows redirects, keeps status and final URL."""
    import requests

    result: dict = {"requested_url": url}
    issue = iri_issue(url, http_only=True)
    if issue:
        return {**result, "error": issue}, None
    try:
        with requests.get(url, headers={"Accept": ACCEPT, "User-Agent": USER_AGENT},
                          timeout=(min(timeout, 10), timeout), stream=True) as response:
            result.update(http_status=response.status_code, final_url=response.url,
                          content_type=response.headers.get("Content-Type", ""),
                          redirects=[{"url": r.url, "status": r.status_code, "location": r.headers.get("Location")}
                                     for r in response.history])
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > max_bytes:
                    return {**result, "error": "download exceeds byte limit"}, None
                chunks.append(chunk)
            result["bytes"] = size
            return result, b"".join(chunks)
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 0) or 0
        if not isinstance(exc, requests.HTTPError) or status >= 500:
            return {**result, "error": "the server was not available, so it could not be checked",
                    "network_error": True}, None
        return {**result, "error": type(exc).__name__ + (f": {exc}" if str(exc) else ""),
                "network_error": False}, None


def parse_rdf(data: bytes, base: str, content_type: str) -> tuple[Graph, str]:
    """Parse Turtle, RDF/XML or N-Triples. Rejects HTML pages and XML DTD/entity declarations."""
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        if data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
            raise ValueError("HTML landing page returned instead of RDF")
        raise ValueError("XML DTD/entity declarations are not supported")
    if "html" in content_type.lower() or data.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("HTML landing page returned instead of RDF")
    formats = ["xml", "turtle", "nt"] if ("xml" in content_type or data.lstrip().startswith(b"<")) else ["turtle", "xml", "nt"]
    errors = []
    for fmt in formats:
        graph = Graph()
        try:
            graph.parse(data=data, format=fmt, publicID=base)
            if not len(graph):
                raise ValueError("empty RDF graph")
            return graph, fmt
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fmt}: {str(exc)[:180]}")
    raise ValueError("; ".join(errors))


def ontology_headers(graph: Graph) -> list[str]:
    return sorted(str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef))


def resolve_ontology_iri(iri: str, timeout: float, max_bytes: int) -> dict:
    """Dereference the ontology IRI and compare the retrieved header with it (exact match)."""
    info, body = fetch(iri, timeout, max_bytes)
    out = {"iri": iri, "http_status": info.get("http_status"), "final_url": info.get("final_url"),
           "content_type": info.get("content_type", ""), "redirects": len(info.get("redirects") or [])}
    if body is None:
        return {**out, "status": "unreachable", "detail": info.get("error", "no data")}
    try:
        graph, fmt = parse_rdf(body, info["final_url"], info.get("content_type", ""))
    except ValueError as exc:
        status = "html_only" if "HTML" in str(exc) else "unparseable"
        return {**out, "status": status, "detail": str(exc)[:200]}
    headers = ontology_headers(graph)
    identity = "match" if iri in headers else "mismatch" if headers else "no_named_ontology_header"
    return {**out, "status": "rdf", "format": fmt, "identity": identity, "headers": headers[:5]}
