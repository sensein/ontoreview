"""``robot reason`` output (HermiT / ELK log) → logical-consistency findings."""

from __future__ import annotations

import re

from .models import REASONERS, ExternalItem, ExternalReport, new_report, sort_items
from .robot import robot_message

_UNSAT = re.compile(r"unsatisfiable:\s*(\S+)")
_INCONSISTENT = re.compile(r"ontology is inconsistent", re.I)
# HermiT refuses ontologies that break OWL 2 DL's global restrictions (e.g. a transitive property in a
# cardinality restriction); that is a problem with the ontology, so it is reported as a finding.
_NOT_DL = re.compile(r"non-simple property|not (?:in|an?) OWL 2 DL|OWL 2 DL", re.I)


def parse_reason_output(text: str, reasoner: str = "hermit") -> list[ExternalItem]:
    """Findings from ``robot reason`` output (stderr/stdout). Empty when the ontology is consistent."""
    name = REASONERS.get(reasoner, reasoner)
    items: list[ExternalItem] = []
    if _INCONSISTENT.search(text):
        items.append(ExternalItem(
            code="inconsistent_ontology", name="Ontology is inconsistent", severity="error",
            description=f"{name} found that the ontology has no model, so no reasoning results can be "
                        "trusted. Common causes: an individual typed with two disjoint classes, or "
                        "property assertions that contradict a domain, range or cardinality. Open the "
                        "ontology in Protégé and use “Explain inconsistency” to find the axioms involved."))
    unsat = [m.group(1).strip("<>") for m in _UNSAT.finditer(text)]
    if unsat:
        items.append(ExternalItem(
            code="unsatisfiable_class", name="Unsatisfiable classes", severity="error",
            description=f"{name} found classes that can never have members, for example a class that is "
                        "a subclass of two disjoint classes. Any individual typed with one of them "
                        "would make the ontology inconsistent.",
            affected=unsat))
    return sort_items(items)


def reasoner_report(returncode: int, output: str, reasoner: str = "hermit") -> ExternalReport:
    """Report from a finished ``robot reason`` run (exit code + combined stdout/stderr)."""
    label = REASONERS.get(reasoner, reasoner)
    items = parse_reason_output(output, reasoner)
    if items:
        return new_report("reasoner", items)
    if returncode == 0:
        return new_report("reasoner", note=f"Consistent; all classes satisfiable ({label}).")
    msg = robot_message(output)
    if reasoner == "hermit" and _NOT_DL.search(msg):
        return new_report("reasoner", [ExternalItem(
            code="outside_owl2_dl", name="Ontology is outside OWL 2 DL", severity="warning",
            description="HermiT only reasons over OWL 2 DL ontologies, so consistency was not checked. "
                        "Fix the axiom below, or choose ELK in Settings › Quality checks (ELK skips "
                        "axioms it does not support).", note=msg)])
    return new_report("reasoner", error=f"{label} could not reason over the ontology" + (f": {msg}" if msg else ""))
