"""OOPS! pitfall scanner (https://oops.linkeddata.es/webservice.html), a web service.

Only sends the ontology and returns the response; :mod:`ontoreview.report.oops` turns it into findings. The
ontology is uploaded to the service. Whether it runs is decided in :mod:`.evaluators`
(``evaluation.oops``: auto = only when ROBOT cannot run, on = always, off = never).
"""

from __future__ import annotations

import logging
import urllib.request

from rdflib import Graph

from ..report.models import ExternalReport
from ..report.oops import oops_report

log = logging.getLogger(__name__)

OOPS_ENDPOINT = "https://oops.linkeddata.es/rest"


def run_oops(graph: Graph, timeout: int = 90, endpoint: str = OOPS_ENDPOINT) -> ExternalReport:
    log.info("Running OOPS! pitfall scan (%s)", endpoint)
    rdfxml = graph.serialize(format="xml")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<OOPSRequest><OntologyURI></OntologyURI>'
        f"<OntologyContent><![CDATA[{rdfxml.replace(']]>', ']]]]><![CDATA[>')}]]></OntologyContent>"
        "<Pitfalls></Pitfalls><OutputFormat>RDF/XML</OutputFormat></OOPSRequest>"
    )
    req = urllib.request.Request(endpoint, data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/xml",
                                          "User-Agent": "ontoreview (ontology documentation)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return oops_report(None, f"OOPS! request failed: {e}")
    return oops_report(text)
