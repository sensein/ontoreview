"""Offline ontology quality checks (inspired by the OOPS! pitfall catalogue)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Literal

from rdflib import Graph

from ..config import Config
from ..model.entities import Ontology

Severity = Literal["error", "warning", "info"]
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


@dataclass
class Finding:
    rule: str
    title: str
    severity: Severity
    message: str
    subject: str | None = None
    subject_label: str | None = None
    anchor: str | None = None


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


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    rules_run: list[Rule] = field(default_factory=list)
    external: list = field(default_factory=list)  # evaluate.ExternalReport (OOPS!, ROBOT)

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def summary(self) -> dict[str, int]:
        return {s: self.count(s) for s in ("error", "warning", "info")}

    def worst(self) -> str | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: SEVERITY_RANK[f.severity]).severity

    def failed(self, fail_on: str) -> bool:
        sev = [f.severity for f in self.findings]
        sev += [i.severity for r in self.external for i in r.items]
        return any(SEVERITY_RANK[s] >= SEVERITY_RANK[fail_on] for s in sev)

    def by_rule(self) -> list[tuple[Rule, list[Finding]]]:
        out = []
        for r in self.rules_run:
            fs = [f for f in self.findings if f.rule == r.id]
            if fs:
                out.append((r, fs))
        out.sort(key=lambda x: (-SEVERITY_RANK[x[1][0].severity], x[0].id))
        return out

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "external": [r.to_dict() for r in self.external],
            "findings": [asdict(f) for f in self.findings],
            "rules": [
                {"id": r.id, "title": r.title, "severity": r.severity, "description": r.description}
                for r in self.rules_run
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


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
