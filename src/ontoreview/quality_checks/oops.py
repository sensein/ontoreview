"""OOPS! pitfall scanner (https://oops.linkeddata.es/webservice.html), a web service.

Only sends the ontology and returns the response; :mod:`ontoreview.report.oops` turns it into
findings. The ontology is uploaded to the service. :mod:`.evaluators` decides whether it runs and
which part of the catalogue: alongside a successful ROBOT report the pitfalls ROBOT already checks
(:data:`ROBOT_COVERED`) are left out; without ROBOT the full catalogue runs.
"""

from __future__ import annotations

import logging
import urllib.request

from rdflib import Graph

from ..report.models import ExternalReport
from ..report.oops import oops_report, oops_scope

log = logging.getLogger(__name__)

OOPS_ENDPOINT = "https://oops.linkeddata.es/rest"
PITFALLS = [f"P{n:02d}" for n in range(1, 42)]           # the catalogue: P01 to P41
# pitfalls the ROBOT report already covers: code -> (pitfall name, ROBOT report rules)
ROBOT_COVERED: dict[str, tuple[str, str]] = {
    "P08": ("Missing annotations", "missing_label, missing_definition"),
    "P32": ("Several classes with the same label", "duplicate_label"),
    "P41": ("No license declared", "missing_ontology_license"),
}


def run_oops(graph: Graph, timeout: int = 90, endpoint: str = OOPS_ENDPOINT, *,
             skip: dict[str, tuple[str, str]] | None = None, robot_state: str = "ok") -> ExternalReport:
    """Scan with OOPS!. ``skip`` leaves those pitfalls out (an empty request list means all)."""
    pitfalls = ",".join(p for p in PITFALLS if p not in skip) if skip else ""
    scope = oops_scope(skip, robot_state)
    log.info("Running OOPS! pitfall scan (%s; %s)", endpoint,
             f"without {', '.join(skip)}, covered by ROBOT" if skip else "full catalogue")
    rdfxml = graph.serialize(format="xml")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<OOPSRequest><OntologyURI></OntologyURI>'
        f"<OntologyContent><![CDATA[{rdfxml.replace(']]>', ']]]]><![CDATA[>')}]]></OntologyContent>"
        f"<Pitfalls>{pitfalls}</Pitfalls><OutputFormat>RDF/XML</OutputFormat></OOPSRequest>"
    )
    req = urllib.request.Request(endpoint, data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/xml",
                                          "User-Agent": "ontoreview (ontology documentation)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return oops_report(None, f"OOPS! request failed: {e}", scope)
    return oops_report(text, scope=scope)
