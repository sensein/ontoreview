"""Quality checks: everything that evaluates an ontology.

* :mod:`.rules`: built-in rules OB001–OB028 (registered with :func:`rule`, run by :func:`run_checks`).
* :mod:`.robot`, :mod:`.logical_consistency`, :mod:`.oops`: run ROBOT report, the reasoner and the
  OOPS! service; :mod:`.evaluators` runs them in order.

Turning results into reports (types, parsers, console/HTML/table output) is in :mod:`ontoreview.report`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from rdflib import Graph

from ..config import Config
from ..model.entities import Ontology
from ..report.models import SEVERITY_RANK, Finding, Report, Severity

__all__ = ["CheckContext", "Finding", "Report", "Rule", "Severity", "rule", "run_checks"]


@dataclass
class CheckContext:
    ontology: Ontology
    graph: Graph
    config: Config


@dataclass
class Rule:
    id: str
    title: str
    severity: Severity
    description: str
    fn: Callable[[CheckContext], Iterable[Finding | tuple]]
    reference: str | None = None


REGISTRY: list[Rule] = []


def rule(id: str, title: str, severity: Severity, description: str, reference: str | None = None):
    def deco(fn):
        REGISTRY.append(Rule(id, title, severity, description, fn, reference))
        return fn

    return deco


def run_checks(ontology: Ontology, graph: Graph, config: Config,
               extra_rules: list[Rule] | None = None) -> Report:
    from . import rules as _rules  # noqa: F401  (registers built-in rules)

    ctx = CheckContext(ontology, graph, config)
    report = Report()
    disabled = set(config.checks.disable)
    for r in [*REGISTRY, *(extra_rules or [])]:
        if r.id in disabled:
            continue
        severity = config.checks.severity.get(r.id, r.severity)
        report.rules_run.append(r)
        for item in r.fn(ctx):
            if isinstance(item, tuple):
                subject, message = item
                term = ontology.terms.get(subject) if subject else None
                item = Finding(
                    rule=r.id, title=r.title, severity=severity, message=message, subject=subject,
                    subject_label=term.label if term else None, anchor=term.anchor if term else None,
                )
            else:
                item.severity = severity
            report.findings.append(item)
    report.findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.rule, f.subject or ""))
    return report
