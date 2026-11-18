"""Exact-IRI repository lookups (OLS, BioPortal). No fuzzy label matches are accepted.

Adapted from the ``ontology_quality`` reference implementation (``providers.py``). Only the
external term IRI is sent. BioPortal needs ``BIOPORTAL_API_KEY`` in the environment; the key is
sent as an Authorization header and never stored or reported.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from rdflib.namespace import OWL, RDF

from .http import USER_AGENT

OLS_API = "https://www.ebi.ac.uk/ols4/api"
BIOPORTAL_API = "https://data.bioontology.org"


def get_json(url, params, timeout, headers=None):
    import requests

    try:
        with requests.get(url, params=params, headers={"Accept": "application/json", "User-Agent": USER_AGENT,
                                                       **(headers or {})},
                          timeout=(min(timeout, 10), timeout), stream=True) as response:
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            body = bytearray()
            for chunk in response.iter_content(65536):
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024:
                    raise ValueError("API response exceeds 5 MiB")
            return json.loads(body)
    except requests.RequestException as exc:
        # Do not emit headers or exception representations containing credentials.
        raise ValueError(type(exc).__name__) from None
    except (TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError("Malformed API response") from None


def needs(roles):
    return ([("terms", str(OWL.Class))] * bool(set(roles) & {"class", "class_or_datatype"})
            + [("properties", str(RDF.Property))] * ("property" in roles))


def record(provider, iri, types, labels, deprecated, evidence):
    return {"iri": iri, "status": "deprecated" if deprecated is True else "valid",
            "provider": provider, "types": sorted(set(types)), "labels": sorted(set(labels)),
            "deprecated": deprecated, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "repository_evidence": evidence, "snapshot": provider}


class OLSProvider:
    name = "ols"

    def lookup(self, iri, roles, timeout=20):
        types, labels, obsolete, evidence = [], [], [], []
        try:
            for kind, term_type in needs(roles):
                url = f"{OLS_API}/{kind}/findByIdAndIsDefiningOntology"
                data = get_json(url, {"iri": iri}, timeout)
                if data is None:
                    return None, {"provider": self.name, "status": "not_found"}
                embedded = data.get("_embedded", {}).get(kind, [])
                # Some deployments return a single entity instead of HAL collections.
                candidates = embedded if embedded else [data] if data.get("iri") else []
                matches = [r for r in candidates if r.get("iri") == iri]
                if not matches:
                    return None, {"provider": self.name, "status": "not_found"}
                selected = matches[0]
                types.append(term_type)
                if selected.get("label"):
                    labels.append(selected["label"])
                obsolete.append(selected.get("is_obsolete"))
                evidence.append({"lookup_url": url, "ontology_iri": selected.get("ontology_iri"),
                                 "ontology_name": selected.get("ontology_name"),
                                 "is_defining_ontology": selected.get("is_defining_ontology"),
                                 "replacement": selected.get("term_replaced_by")})
            deprecated = True if True in obsolete else False if obsolete and all(x is False for x in obsolete) else None
            return record(self.name, iri, types, labels, deprecated, evidence), {"provider": self.name, "status": "found"}
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, {"provider": self.name, "status": "unavailable"}


class BioPortalProvider:
    name = "bioportal"

    def __init__(self, api_key=None):
        self.api_key = api_key if api_key is not None else os.environ.get("BIOPORTAL_API_KEY")

    def lookup(self, iri, roles, timeout=20):
        if not self.api_key:
            return None, {"provider": self.name, "status": "not_configured", "detail": "Set BIOPORTAL_API_KEY"}
        types, labels, obsolete, evidence = [], [], [], []
        try:
            for kind, term_type in needs(roles):
                url = f"{BIOPORTAL_API}/{'search' if kind == 'terms' else 'property_search'}"
                params = {"q": iri, "require_exact_match": "true", "pagesize": 100,
                          "display_context": "false", "display_links": "false"}
                if kind == "terms":
                    params["also_search_obsolete"] = "true"
                data = get_json(url, params, timeout, {"Authorization": f"apikey token={self.api_key}"})
                if data is None:
                    return None, {"provider": self.name, "status": "not_found"}
                matches = [r for r in data.get("collection", []) if r.get("@id") == iri]
                if not matches:
                    return None, {"provider": self.name, "status": "not_found_in_returned_page"}
                selected = matches[0]
                types.append(term_type)
                label = selected.get("prefLabel") or selected.get("label")
                if isinstance(label, str):
                    labels.append(label)
                obsolete.append(selected.get("obsolete"))
                evidence.append({"lookup_url": url, "returned_id": selected["@id"],
                                 "reported_type": selected.get("@type")})
            deprecated = True if True in obsolete else False if obsolete and all(x is False for x in obsolete) else None
            return record(self.name, iri, types, labels, deprecated, evidence), {"provider": self.name, "status": "found"}
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, {"provider": self.name, "status": "unavailable"}
