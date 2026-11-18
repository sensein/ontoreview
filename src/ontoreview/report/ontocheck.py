"""OntoCheck results → a metrics table (by category) plus findings for the review.

Every metric becomes a row in ``ExternalReport.metrics`` (category, metric, value, status). Results
that point at something to fix also become findings. Most are ``info``: missing labels and
definitions, duplicate labels and missing domains/ranges are already graded by the built-in rules
and ROBOT, so OntoCheck adds its view without counting the same problem twice as a warning.
"""

from __future__ import annotations

from typing import Any

from .models import ExternalItem, ExternalReport, new_report, sort_items

# metric -> (category, title, what it measures)
METRICS: dict[str, tuple[str, str, str]] = {
    "checkLabel": ("Labeling", "Labels", "Named classes with an rdfs:label"),
    "altLabelCheck": ("Labeling", "Alternative labels", "Named classes with a skos:altLabel"),
    "definitionCheck": ("Labeling", "Definitions", "Named classes with a skos:definition"),
    "isolatedElements": ("Structural", "Isolated elements",
                         "Classes and properties not connected to anything else"),
    "classConnections": ("Structural", "Class connections",
                         "Separate groups of classes (subClassOf, equivalentClass, disjointWith); 1 means fully connected"),
    "missingDomainRange": ("Structural", "Domain and range", "Object and datatype properties without rdfs:domain / rdfs:range"),
    "leafNodeCheck": ("Structural", "Leaf classes", "Classes with no subclasses"),
    "semanticConnection": ("Structural", "Upper-ontology links", "Top-level classes connected to BFO or CCO"),
    "sparqlEndpoint": ("Accessibility", "SPARQL endpoint", "Declared SPARQL endpoints that answer a query"),
    "rdfDump": ("Accessibility", "RDF dump", "Declared RDF dump URLs that can be downloaded"),
    "humanLicense": ("Accessibility", "Human-readable license", "License or copyright text in the ontology"),
    "externalLinks": ("Accessibility", "External links",
                      "Entities linked to external resources (owl:sameAs, rdfs:seeAlso, SKOS mappings, …)"),
    "classCapitalCheck": ("Naming convention", "Capitalised class names", "Class names that start with a capital letter"),
    "classSpaceCheck": ("Naming convention", "Spaces in class names", "Class names containing spaces in the Turtle source"),
    "spellCheck": ("Naming convention", "Spelling",
                   "Words in English (or untagged) labels, definitions and comments not found in an English dictionary"),
    "duplicateLabels": ("Naming convention", "Duplicate labels", "Classes and properties sharing an rdfs:label (case-insensitive)"),
    "searchClass": ("Naming convention", "Class search", "Classes whose name contains the configured search term"),
}
GROUPS = ["Labeling", "Structural", "Accessibility", "Naming convention"]


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _pct(part: float, whole: float) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "–"


def _coverage(v: dict, noun: str = "classes") -> tuple[str, bool]:
    return f"{v['with']} of {v['total']} {noun} ({_pct(v['with'], v['total'])})", v["with"] == v["total"]


def _row(name: str, res: dict[str, Any]) -> dict[str, str]:  # noqa: C901
    """One metrics-table row: value text and status (ok | warn | info | skipped | error)."""
    group, title, what = METRICS[name]
    row = {"group": group, "metric": name, "title": title, "about": what, "value": "", "status": "info"}
    if res.get("error"):
        return row | {"value": f"Could not run: {res['error']}", "status": "error"}
    if res.get("skipped"):
        return row | {"value": f"Skipped: {res['skipped']}", "status": "skipped"}
    v = res.get("value")
    if name in ("checkLabel", "definitionCheck"):
        text, full = _coverage(v)
        return row | {"value": text, "status": "ok" if full else "warn"}
    if name == "altLabelCheck":
        return row | {"value": _coverage(v)[0], "status": "info"}
    if name == "classCapitalCheck":
        text, full = _coverage(v)
        return row | {"value": text, "status": "ok" if full else "info"}
    if name == "isolatedElements":
        n = v["classes"] + v["properties"]
        return row | {"value": f"{_n(v['classes'], 'class', 'classes')}, {_n(v['properties'], 'property', 'properties')}",
                      "status": "ok" if n == 0 else "warn"}
    if name == "classConnections":
        return row | {"value": f"{v} group{'s' if v != 1 else ''}", "status": "ok" if v <= 1 else "info"}
    if name == "missingDomainRange":
        n = v["missing_domain"] + v["missing_range"]
        return row | {"value": f"{v['missing_domain']} without domain, {v['missing_range']} without range",
                      "status": "ok" if n == 0 else "warn"}
    if name == "leafNodeCheck":
        return row | {"value": f"{v['leaves']} of {v['total']} classes"}
    if name == "semanticConnection":
        return row | {"value": f"{v['connected']} of {v['roots']} top-level classes"}
    if name in ("sparqlEndpoint", "rdfDump"):
        if not v["declared"]:
            return row | {"value": "None declared"}
        ok = round(v["ratio"] * v["declared"])
        return row | {"value": f"{ok} of {v['declared']} reachable", "status": "ok" if ok == v["declared"] else "warn"}
    if name == "humanLicense":
        return row | {"value": "Found" if v else "Not found", "status": "ok" if v else "warn"}
    if name == "externalLinks":
        return row | {"value": f"{100 * v:.1f}% of entities"}
    if name == "classSpaceCheck":
        return row | {"value": "None" if not v else f"{v} class name{'s' if v != 1 else ''}", "status": "ok" if not v else "error"}
    if name == "spellCheck":
        return row | {"value": f"{v['errors']} possible misspellings in {v['checked']} words ({100 * v['rate']:.1f}%)",
                      "status": "ok" if not v["errors"] else "info"}
    if name == "duplicateLabels":
        return row | {"value": "None" if not v else f"{v} label{'s' if v != 1 else ''} shared", "status": "ok" if not v else "warn"}
    if name == "searchClass":
        term = (res.get("detail") or {}).get("term", "")
        return row | {"value": f"{v} class{'es' if v != 1 else ''} match “{term}”"}
    return row | {"value": str(v)}


def _items(name: str, res: dict[str, Any]) -> list[ExternalItem]:
    """Findings for results that point at something to fix."""
    if res.get("error") or res.get("skipped"):
        return []
    v, items, detail = res.get("value"), res.get("items") or [], res.get("detail") or {}
    title = METRICS[name][1]

    def item(sev: str, label: str, desc: str, affected=None, note: str = "") -> list[ExternalItem]:
        return [ExternalItem(code=name, name=label, severity=sev, description=desc, affected=list(affected or []), note=note)]

    if name == "checkLabel" and items:
        return item("info", "Classes without rdfs:label", "OntoCheck checkLabel: these named classes have no rdfs:label.", items)
    if name == "definitionCheck" and items:
        return item("info", "Classes without skos:definition",
                    "OntoCheck definitionCheck looks for skos:definition only (not IAO:0000115 or rdfs:comment).", items)
    if name == "isolatedElements" and items:
        return item("info", "Isolated classes and properties",
                    "OntoCheck isolatedElements: not related to any other class or property.", items)
    if name == "missingDomainRange" and items:
        return item("info", "Properties without domain or range",
                    f"{v['missing_domain']} without rdfs:domain, {v['missing_range']} without rdfs:range.", items)
    if name == "classCapitalCheck" and items:
        return item("info", "Class names not starting with a capital letter", "OntoCheck classCapitalCheck.", items)
    if name == "duplicateLabels" and v:
        labels = detail.get("labels") or {}
        return item("info", "Shared labels", "OntoCheck duplicateLabels (case-insensitive rdfs:label).", items,
                    "; ".join(f"“{k}”: {len(u)} entities" for k, u in labels.items())[:300])
    if name == "spellCheck" and v["errors"]:
        words = detail.get("words") or {}
        shown = ", ".join(f"{w} → {f}" if f and f != w else w for w, f in list(words.items())[:25])
        return item("info", "Possible misspellings",
                    "OntoCheck spellCheck (English dictionary) in rdfs:label, skos:definition and rdfs:comment. "
                    "Domain terms and abbreviations are often flagged; review before changing.", items,
                    shown + (" …" if len(words) > 25 else ""))
    if name == "humanLicense" and not v:
        return item("warning", "No human-readable license", "No license or copyright text was found in the ontology.")
    if name in ("sparqlEndpoint", "rdfDump") and v["declared"] and round(v["ratio"] * v["declared"]) < v["declared"]:
        return item("warning", f"{title}: not reachable",
                    "Some declared URLs did not respond with HTTP 200.", detail.get("urls"))
    if name == "classSpaceCheck" and v:
        return item("error", "Class names containing spaces", "OntoCheck classSpaceCheck.",
                    note="; ".join(detail.get("names", []))[:300])
    return []


def ontocheck_report(results: dict[str, dict[str, Any]], error: str | None = None) -> ExternalReport:
    """The OntoCheck section of the review."""
    if error:
        return new_report("ontocheck", error=error)
    metrics, items = [], []
    for name in METRICS:
        if name in results:
            metrics.append(_row(name, results[name]))
            items += _items(name, results[name])
    rep = new_report("ontocheck", sort_items(items))
    rep.metrics = metrics
    failed = [m["metric"] for m in metrics if m["status"] == "error"]
    if failed:
        rep.scope = f"Some metrics could not run: {', '.join(failed)}."
    return rep


__all__ = ["GROUPS", "METRICS", "ontocheck_report"]
