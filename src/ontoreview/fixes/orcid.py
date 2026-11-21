"""Find ORCID iDs for a creator's name in the public ORCID registry (no token needed).

The results are candidates: the user picks the right person (or none); nothing is filled in on its own.

    search_orcid("Josiah Carberry")  →  [{"orcid": "0000-0002-1825-0097", "name": "Josiah Carberry",
                                          "institutions": ["Brown University"], "url": "https://orcid.org/…"}]
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

API = "https://pub.orcid.org/v3.0/expanded-search/"
USER_AGENT = "OntoReview (ontology documentation tool)"


def query_for(name: str) -> str:
    """ORCID's Solr query for a person's name: given + family name when there are two or more words."""
    parts = [p for p in name.replace(",", " ").split() if p]
    if not parts:
        return ""
    esc = lambda s: s.replace('"', "")  # noqa: E731
    if len(parts) == 1:
        return f'family-name:"{esc(parts[0])}" OR given-names:"{esc(parts[0])}"'
    given, family = " ".join(parts[:-1]), parts[-1]
    return f'given-and-family-names:"{esc(given)} {esc(family)}" OR (given-names:"{esc(given)}" AND family-name:"{esc(family)}")'


def parse(data: dict, limit: int = 5) -> list[dict]:
    out = []
    for r in (data or {}).get("expanded-result") or []:
        oid = r.get("orcid-id")
        if not oid:
            continue
        name = " ".join(x for x in (r.get("given-names"), r.get("family-names")) if x) or r.get("credit-name") or oid
        out.append({"orcid": oid, "name": name, "institutions": list(dict.fromkeys(r.get("institution-name") or []))[:3],
                    "url": f"https://orcid.org/{oid}"})
        if len(out) >= limit:
            break
    return out


def search_orcid(name: str, limit: int = 5, timeout: float = 10) -> list[dict]:
    """Up to ``limit`` people whose ORCID record matches ``name``; [] for an empty name. Raises OSError
    (or ValueError) when the registry cannot be reached."""
    q = query_for(name)
    if not q:
        return []
    url = f"{API}?{urllib.parse.urlencode({'q': q, 'rows': limit})}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https endpoint
        return parse(json.loads(r.read().decode("utf-8")), limit)


__all__ = ["parse", "query_for", "search_orcid"]
