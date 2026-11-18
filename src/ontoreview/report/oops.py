"""OOPS! web service response (RDF/XML) → pitfall findings."""

from __future__ import annotations

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from .models import SEVERITY_ORDER, ExternalItem, ExternalReport, new_report

OOPS = Namespace("http://oops.linkeddata.es/def#")
# the web service documentation's RDF/XML responses use this namespace; accept both
OOPS_OEG = Namespace("http://www.oeg-upm.net/oops#")
OOPS_LEVELS = {"critical": "error", "important": "warning", "minor": "info"}


def parse_oops(rdfxml: str) -> list[ExternalItem]:
    """Findings from an OOPS! RDF/XML response (pitfalls, warnings and suggestions)."""
    g = Graph()
    g.parse(data=rdfxml, format="xml")
    items: list[ExternalItem] = []
    for ns in (OOPS, OOPS_OEG):
        items += _parse_oops_ns(g, ns)
    return sorted(items, key=lambda i: (SEVERITY_ORDER[i.severity], i.code))


def _parse_oops_ns(g: Graph, OOPS: Namespace) -> list[ExternalItem]:  # noqa: N803
    items: list[ExternalItem] = []
    for kind, default_sev in ((OOPS.pitfall, None), (OOPS.warning, "warning"), (OOPS.suggestion, "info")):
        for node in g.subjects(RDF.type, kind):
            code = str(g.value(node, OOPS.hasCode) or ("Warning" if default_sev == "warning" else
                                                       "Suggestion" if default_sev == "info" else ""))
            level = str(g.value(node, OOPS.hasImportanceLevel) or "").lower()
            sev = OOPS_LEVELS.get(level, default_sev or "info")
            affected, note = [], []
            for a in g.objects(node, OOPS.hasAffectedElement):
                s = str(a).strip()
                (affected if s.startswith(("http://", "https://", "urn:")) and " " not in s else note).append(s)
            for p in (OOPS.mightBeEquivalentProperty, OOPS.mightBeEquivalentAttribute, OOPS.mightNotBeInverseOf):
                for grp in g.objects(node, p):
                    affected += [str(x) for x in g.objects(grp, OOPS.hasAffectedElement)]
            items.append(ExternalItem(
                code=code, name=str(g.value(node, OOPS.hasName) or code), severity=sev,
                description=" ".join(str(g.value(node, OOPS.hasDescription) or "").split()),
                affected=sorted(set(affected)), note=" ".join(note),
            ))
    return items


ROBOT_STATES = {
    "unavailable": "ROBOT was not available",
    "failed": "the ROBOT report failed",
    "off": "ROBOT is turned off",
}


def oops_scope(skipped: dict[str, tuple[str, str]] | None, robot_state: str = "ok") -> str:
    """Which part of the OOPS! catalogue ran. ``skipped`` maps pitfall code -> (name, ROBOT rules)."""
    if skipped:
        parts = [f"{code} {name} (ROBOT {rules})" for code, (name, rules) in skipped.items()]
        return "Run alongside ROBOT. Not run here because ROBOT already checks them: " + "; ".join(parts) + "."
    reason = ROBOT_STATES.get(robot_state)
    return f"Full pitfall catalogue ({reason})." if reason else "Full pitfall catalogue."


def oops_report(response: str | None, failure: str | None = None, scope: str = "") -> ExternalReport:
    """Report from the OOPS! service: its RDF/XML response, or why the request failed."""
    if response is None:
        return new_report("oops", error=failure or "OOPS! request failed", scope=scope)
    try:
        return new_report("oops", parse_oops(response), scope=scope)
    except Exception as e:  # noqa: BLE001
        return new_report("oops", error=f"Could not parse the OOPS! response: {e}", scope=scope)
