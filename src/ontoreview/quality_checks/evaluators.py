"""Runs the external quality checks in order: ROBOT report, reasoner consistency check (both on
this machine, locally or in Docker), IRI checks, OntoCheck metrics (in-process), cross-domain
interoperability (when turned on), then the OOPS! web service. With ``evaluation.oops = "auto"``
(default) OOPS! complements ROBOT: pitfalls the ROBOT report covers are left out, and the full
catalogue runs when ROBOT did not. ``"on"`` always runs the full catalogue; ``"off"`` never uploads.

The checkers are looked up through their modules so tests can replace them.
"""

from __future__ import annotations

import logging

from rdflib import Graph

from ..report.models import ExternalReport, unavailable
from . import cdi, iri, logical_consistency, ontocheck, oops, robot

log = logging.getLogger(__name__)


def run_evaluations(graph: Graph, config, source: str | None = None,
                    namespace: str | None = None) -> list[ExternalReport]:
    ev = config.evaluation
    out: list[ExternalReport] = []
    robot_state = "off"
    if ev.robot != "off":
        r = robot.run_robot(graph, ev.robot_path, ev.robot_profile, image=ev.robot_image)
        if r is None:
            robot_state = "unavailable"
            if ev.robot == "on":
                out.append(unavailable("robot", ev.robot_image))
        else:
            out.append(r)
            robot_state = "ok" if r.error is None else "failed"
        lc = logical_consistency.check_consistency(graph, ev)
        if lc is not None:
            out.append(lc)
    ir = iri.check_iris(graph, ev, source, namespace)       # SQLite first; network per evaluation.iri_*
    if ir is not None:
        out.append(ir)
    oc = ontocheck.check_ontocheck(graph, ev, source)       # local, in-process (network: declared endpoints)
    if oc is not None:
        out.append(oc)
    # cross-domain and scientific interoperability: one run, on by default; references per cdi_references
    out += cdi.check_cdi(graph, ev, source, namespace)
    if ev.oops != "off":
        # auto: complement ROBOT (skip what its report covers); full catalogue when ROBOT did not run
        skip = oops.ROBOT_COVERED if ev.oops == "auto" and robot_state == "ok" else None
        log.info("OOPS! uploads the ontology to oops.linkeddata.es; set evaluation.oops = \"off\" to keep it local.")
        out.append(oops.run_oops(graph, ev.oops_timeout, ev.oops_endpoint or oops.OOPS_ENDPOINT,
                                 skip=skip, robot_state=robot_state))
    for r in out:
        if r.error:
            log.warning(r.error)
    from .. import telemetry

    telemetry.note_evaluations(config, out)
    return out
