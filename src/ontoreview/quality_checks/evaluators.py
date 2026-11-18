"""Runs the external quality checks in order: ROBOT report, reasoner consistency check (both on
this machine, locally or in Docker), then the OOPS! web service as a fallback, or always with
``evaluation.oops = "on"``.

The checkers are looked up through their modules so tests can replace them.
"""

from __future__ import annotations

import logging

from rdflib import Graph

from ..report.models import ExternalReport, unavailable
from . import logical_consistency, oops, robot

log = logging.getLogger(__name__)


def run_evaluations(graph: Graph, config) -> list[ExternalReport]:
    ev = config.evaluation
    out: list[ExternalReport] = []
    robot_ok = False
    if ev.robot != "off":
        r = robot.run_robot(graph, ev.robot_path, ev.robot_profile, image=ev.robot_image)
        if r is None:
            if ev.robot == "on":
                out.append(unavailable("robot", ev.robot_image))
        else:
            out.append(r)
            robot_ok = r.error is None
        lc = logical_consistency.check_consistency(graph, ev)
        if lc is not None:
            out.append(lc)
    fallback = ev.oops == "auto" and ev.robot != "off" and not robot_ok
    if ev.oops == "on" or fallback:
        if fallback:
            log.info("ROBOT could not run; using the OOPS! web service instead (uploads the ontology "
                     "to oops.linkeddata.es; set evaluation.oops = \"off\" to disable).")
        out.append(oops.run_oops(graph, ev.oops_timeout, ev.oops_endpoint or oops.OOPS_ENDPOINT))
    for r in out:
        if r.error:
            log.warning(r.error)
    return out
