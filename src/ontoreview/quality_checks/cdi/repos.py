"""Find ontologies in OLS or an OntoPortal service (BioPortal, AgroPortal, …) by name, so users can
name reference ontologies instead of uploading them. Results are reference specs such as
``ols:envo`` or ``bioportal:NCIT``, the same strings the cross-domain and scientific
interoperability checks accept.

The repository's ontology list is fetched once per service and kept in memory for a day; the
search itself runs locally over ids, titles, prefixes and descriptions.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from .core import BIOPORTAL_BASE, OLS_BASE, USER_AGENT

CACHE_SECONDS = 24 * 3600
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()


@dataclass
class RepoOntology:
    spec: str           # what goes into the reference list, e.g. "ols:envo"
    id: str             # repository id or acronym
    title: str
    description: str = ""
    repository: str = "ols"

    def to_dict(self) -> dict:
        return asdict(self)


def _text(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_text(x) for x in v if x)
    if isinstance(v, dict):
        return _text(v.get("value") or v.get("en") or next(iter(v.values()), ""))
    return "" if v is None else str(v)


def _get(url: str, params: dict, headers: dict | None = None, timeout: float = 30):
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(f"{url}?{q}" if q else url,
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})})
    from ... import netstate

    if netstate.is_down(url):
        raise ConnectionError(netstate.not_available(url))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https endpoints or user-set base
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        if netstate.is_unavailable(e):
            netstate.mark_down(url)
            raise ConnectionError(netstate.not_available(url)) from None
        raise


def _ols_list(base: str, timeout: float) -> list[dict]:
    data = _get(f"{base}/v2/ontologies", {"size": 1000}, timeout=timeout)
    out = []
    for e in data.get("elements", []):
        oid = e.get("ontologyId")
        if oid:
            out.append({"id": oid, "title": _text(e.get("title")) or oid, "description": _text(e.get("description")),
                        "prefix": _text(e.get("preferredPrefix"))})
    return out


def _ontoportal_list(base: str, api_key: str, timeout: float) -> list[dict]:
    data = _get(f"{base}/ontologies", {"display_context": "false", "display_links": "false"},
                {"Authorization": f"apikey token={api_key}"}, timeout=timeout)
    return [{"id": e.get("acronym"), "title": e.get("name") or e.get("acronym"), "description": "", "prefix": ""}
            for e in (data if isinstance(data, list) else []) if e.get("acronym")]


def ontology_list(repository: str = "ols", api_key: str = "", base: str | None = None,
                  timeout: float = 30) -> list[dict]:
    """Every ontology the service offers (cached for a day). Raises OSError/ValueError on failure."""
    kind = "ols" if repository.startswith("ols") else "bioportal"
    base = (base or (OLS_BASE if kind == "ols" else BIOPORTAL_BASE)).rstrip("/")
    key = f"{kind}@{base}"
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    if kind == "bioportal" and not api_key:
        raise ValueError("BioPortal and other OntoPortal services need an API key (Settings › Quality checks, "
                         "or BIOPORTAL_API_KEY / ONTOPORTAL_API_KEY)")
    rows = _ols_list(base, timeout) if kind == "ols" else _ontoportal_list(base, api_key, timeout)
    with _lock:
        _cache[key] = (time.time(), rows)
    return rows


def search_ontologies(query: str, repository: str = "ols", api_key: str = "", base: str | None = None,
                      limit: int = 15, timeout: float = 30) -> list[RepoOntology]:
    """Ontologies whose id, title, prefix or description match ``query`` (case-insensitive), best
    first: exact id, id prefix, title, then description."""
    kind = "ols" if repository.startswith("ols") else "bioportal"
    q = query.strip().lower()
    if not q:
        return []
    rows = ontology_list(kind, api_key, base, timeout)

    def rank(r: dict) -> int | None:
        oid, title = r["id"].lower(), r["title"].lower()
        if q in (oid, r["prefix"].lower()):
            return 0
        if oid.startswith(q):
            return 1
        if q in title:
            return 2
        if q in oid or q in r["description"].lower():
            return 3
        return None

    hits = sorted(((rk, r) for r in rows if (rk := rank(r)) is not None), key=lambda x: (x[0], x[1]["id"].lower()))
    suffix = f"@{base}" if base else ""
    return [RepoOntology(f"{kind}:{r['id']}{suffix}", r["id"], r["title"], r["description"][:300], kind)
            for _, r in hits[:limit]]


__all__ = ["RepoOntology", "ontology_list", "search_ontologies"]
