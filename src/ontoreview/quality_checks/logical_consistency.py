"""Logical consistency: run an OWL DL reasoner over the ontology.

Uses ``robot reason`` (http://robot.obolibrary.org/reason) through the same ROBOT set-up as the
ROBOT report: a local ``robot`` command, or the ``obolibrary/robot`` Docker image. Nothing is
uploaded anywhere.

This module only runs the reasoner; :mod:`ontoreview.report.reasoner` turns its output into findings (both errors):

* ``inconsistent_ontology``: the ontology has no model, so every conclusion is trivially true.
  Usually caused by an individual that belongs to two disjoint classes, or by conflicting
  property assertions.
* ``unsatisfiable_class``: classes that can never have members (for example, a subclass of two
  disjoint classes). The affected classes are listed.

Reasoners: ``hermit`` (default; complete for OWL 2 DL) or ``elk`` (fast, OWL 2 EL only, so it can
miss problems that need more expressive axioms).
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from rdflib import Graph

from ..report.models import REASONERS, ExternalReport, new_report, unavailable
from ..report.reasoner import reasoner_report
from .robot import robot_command, robot_invocation

log = logging.getLogger(__name__)


def run_reasoner(graph: Graph, reasoner: str = "hermit", robot: str | None = None,
                 image: str | None = None, timeout: int = 600, pull: bool = True) -> ExternalReport | None:
    """Check consistency and class satisfiability with ``robot reason``.

    Returns None when ROBOT is not available (no local ``robot`` and no Docker).
    """
    reasoner = reasoner.lower()
    if reasoner not in REASONERS:
        raise ValueError(f"unknown reasoner {reasoner!r}; use one of {', '.join(REASONERS)}")
    resolved = robot_command(robot, image, pull)
    if resolved is None:
        return None
    mode, cmd = resolved
    label = REASONERS[reasoner]
    log.info("Checking logical consistency with %s (ROBOT%s)", label, " in Docker" if mode == "docker" else "")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "ontology.owl"
        graph.serialize(destination=str(src), format="xml")
        base, where = robot_invocation(mode, cmd, tmp)
        args = base + ["reason", "--input", where(src), "--reasoner", reasoner]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return new_report("reasoner", error=f"{label} did not finish within {timeout} seconds.")
        except Exception as e:  # noqa: BLE001
            return new_report("reasoner", error=f"ROBOT failed to run: {e}")
    return reasoner_report(proc.returncode, f"{proc.stdout}\n{proc.stderr}", reasoner)


def check_consistency(graph: Graph, ev) -> ExternalReport | None:
    """Run the reasoner configured in ``[evaluation]`` (``ev``); None when turned off or skipped."""
    if ev.reasoner == "off" or ev.robot == "off":
        return None
    r = run_reasoner(graph, ev.reasoner, ev.robot_path, ev.robot_image, timeout=ev.reasoner_timeout)
    if r is None and ev.robot == "on":
        return unavailable("reasoner", ev.robot_image)
    return r


__all__ = ["check_consistency", "run_reasoner"]
