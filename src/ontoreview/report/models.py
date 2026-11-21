"""Result types for quality reports, and the registry of external checkers.

* :class:`Finding` / :class:`Report`: built-in rule findings, plus the external reports.
* :class:`ExternalItem` / :class:`ExternalReport`: one external checker's results (ROBOT report,
  logical consistency, OOPS!).
* :data:`TOOLS`: each external checker's display name and reference URL.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..quality_checks import Rule

Severity = Literal["error", "warning", "info"]
SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}      # higher = worse
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}     # display order


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
class ExternalItem:
    code: str
    name: str
    severity: Severity
    description: str = ""
    affected: list[str] = field(default_factory=list)
    note: str = ""  # free-text affected elements (OOPS! sometimes returns prose)


@dataclass
class ExternalReport:
    tool: str
    url: str
    items: list[ExternalItem] = field(default_factory=list)
    error: str | None = None
    note: str = ""  # shown when there are no findings, e.g. "Consistent; ... (HermiT)."
    scope: str = ""  # what was (not) checked, e.g. which OOPS! pitfalls were left to ROBOT
    metrics: list[dict] = field(default_factory=list)  # scorecard rows (OntoCheck): group, title, value, status
    provenance: dict = field(default_factory=dict)    # frozen record of what was checked against (IRI checks)

    @property
    def summary(self) -> dict[str, int]:
        """Counts per severity, one per affected element (like the built-in rules, which report
        one finding per term); a finding without listed elements counts once."""
        out = {"error": 0, "warning": 0, "info": 0}
        for i in self.items:
            out[i.severity] = out.get(i.severity, 0) + max(len(i.affected), 1)
        return out

    def to_dict(self) -> dict:
        return asdict(self) | {"summary": self.summary}


# ------------------------------------------------------------------------ tools
@dataclass(frozen=True)
class Tool:
    name: str  # shown as the section title in reports and in the app's Issues table
    url: str   # reference documentation, linked from the section title ("" = none)
    score: str = ""    # key in provenance["summary"] holding a 0..1 score shown as an Overview tile
    verdict: str = ""  # key in provenance["summary"] holding whether the score passes its threshold


TOOLS: dict[str, Tool] = {
    "robot": Tool("ROBOT", "http://robot.obolibrary.org/report"),
    "reasoner": Tool("Logical consistency", "http://robot.obolibrary.org/reason"),
    "ontocheck": Tool("OntoCheck", "https://ontocheck.readthedocs.io"),
    "iri": Tool("IRI checks", "https://www.w3.org/TR/cooluris/"),
    "oops": Tool("OOPS!", "https://oops.linkeddata.es"),
    # OntoReview's own check: no external reference
    "cdi": Tool("Cross-domain interoperability", "", score="cdi", verdict="interoperable"),
    "si": Tool("Scientific interoperability", "", score="si", verdict="interoperable"),
}


def tool_anchor(name: str) -> str:
    """Fragment id of a checker's section in the quality report, e.g. ``quality-oops``."""
    return "quality-" + name.lower().replace("!", "").replace(" ", "-")
REASONERS = {"hermit": "HermiT", "elk": "ELK"}


def new_report(tool: str, items: list[ExternalItem] | None = None, *, error: str | None = None,
               note: str = "", scope: str = "") -> ExternalReport:
    """An empty (or pre-filled) report for one of :data:`TOOLS`."""
    t = TOOLS[tool]
    return ExternalReport(t.name, t.url, items=list(items or []), error=error, note=note, scope=scope)


def unavailable(tool: str, image: str) -> ExternalReport:
    """Report for a ROBOT-based check that could not run because ROBOT is missing."""
    what = "ROBOT is not available" if tool == "robot" else "Reasoner not run: ROBOT is not available"
    return new_report(tool, error=f"{what}: start Docker (image {image}) or put `robot` on PATH.")


def sort_items(items: list[ExternalItem]) -> list[ExternalItem]:
    for i in items:
        i.affected = sorted(set(i.affected))
    return sorted(items, key=lambda i: (SEVERITY_ORDER.get(i.severity, 3), i.code))


def curie_for(iri: str, ontology) -> tuple[str, str | None]:
    """Display label + internal anchor for an affected element."""
    t = ontology.terms.get(iri)
    if t is not None:
        return t.label, t.anchor
    return iri, None


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    rules_run: list[Rule] = field(default_factory=list)  # quality_checks.Rule
    external: list[ExternalReport] = field(default_factory=list)  # ROBOT, reasoner, OOPS!

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

    @property
    def totals(self) -> dict[str, int]:
        """Counts across all checks: built-in rules plus ROBOT, logical consistency and OOPS!.
        (:attr:`summary` is the built-in rules only.)"""
        out = dict(self.summary)
        for r in self.external:
            for k, v in r.summary.items():
                out[k] = out.get(k, 0) + v
        return out

    ABOUT = {"OntoReview": "Metadata, labels, definitions and the class hierarchy (built-in rules)",
             "ROBOT": "OBO-style quality report: labels, definitions, synonyms, references",
             "Logical consistency": "Whether a reasoner finds contradictions or impossible classes",
             "IRI checks": "Identifiers: syntax, the ontology header, whether external terms exist",
             "OntoCheck": "Metrics on labeling, structure, accessibility and naming",
             "Cross-domain interoperability": "How well the ontology connects to other domains (a score)",
             "Scientific interoperability": "In how many scientific fields it is interoperable (a score)",
             "OOPS!": "Common modelling pitfalls (OOPS! web service)"}

    def check_rows(self) -> list[dict]:
        """One row per check for the quality report's summary table. ``count`` is None when the
        check did not run (``error``) or reports a verdict rather than findings; ``share`` is the
        count relative to the largest, 0..1. The built-in row has ``tool`` None."""
        b = self.summary
        rows = [{"tool": None, "anchor": "quality-builtin", "count": len(self.findings), "error": None,
                 "about": self.ABOUT["OntoReview"], "errors": b["error"], "warnings": b["warning"], "infos": b["info"],
                 "note": ""}]
        for r in self.external:
            n = sum(r.summary.values())
            rows.append({"tool": r.tool, "anchor": tool_anchor(r.tool), "error": r.error,
                         "count": None if r.error or (not r.items and (r.note or r.metrics)) else n,
                         "about": self.ABOUT.get(r.tool, ""), "errors": r.summary["error"],
                         "warnings": r.summary["warning"], "infos": r.summary["info"],
                         "note": (r.note or "")[:120] if not r.items else ""})
        top = max((x["count"] or 0 for x in rows), default=0)
        for x in rows:
            x["share"] = (x["count"] or 0) / top if top else 0
        return rows

    def merged_issues(self) -> list[dict]:
        """Distinct issues across all checks: the same problem found by several checks (a missing
        definition from OntoReview, ROBOT, OntoCheck and OOPS!) is one issue that lists who found it.
        The interoperability scores are measurements, not defects, and are left out."""
        from ..fixes.external import INTEROP, MAP, SAME_ISSUE
        same = {**SAME_ISSUE, **MAP}
        titles = {r.id: r.title for r in self.rules_run}
        groups: dict[str, dict] = {}

        def add(key: str, title: str, sev: str, elems, by: str, anchor: str) -> None:
            g = groups.setdefault(key, {"key": key, "title": title, "severity": sev, "elements": [],
                                        "found_by": [], "anchors": []})
            if SEVERITY_RANK.get(sev, 0) > SEVERITY_RANK.get(g["severity"], 0):
                g["severity"] = sev
            for e in elems:
                if e and e not in g["elements"]:
                    g["elements"].append(e)
            if by not in g["found_by"]:
                g["found_by"].append(by)
                g["anchors"].append(anchor)

        for f in self.findings:
            add(f.rule, f.title, f.severity, [f.subject], "OntoReview", "quality-builtin")
        for ext in self.external:
            if ext.tool in INTEROP or ext.error:
                continue
            for it in ext.items:
                targets = same.get((ext.tool, it.code)) or ()
                if not targets:
                    add(f"{ext.tool}:{it.code}", it.name, it.severity, it.affected, ext.tool, tool_anchor(ext.tool))
                    continue
                if len(targets) == 1:
                    add(targets[0], titles.get(targets[0], it.name), it.severity, it.affected, ext.tool,
                        tool_anchor(ext.tool))
                    continue
                # "domain or range", "label or definition": each element goes to the issue it already has
                for e in it.affected or [None]:
                    hit = [k for k in targets if k in groups and e in groups[k]["elements"]] or list(targets[:1])
                    for key in hit:
                        add(key, titles.get(key, it.name), it.severity, [e], ext.tool, tool_anchor(ext.tool))
        return sorted(groups.values(), key=lambda g: (-SEVERITY_RANK.get(g["severity"], 0), -len(g["elements"]),
                                                      g["title"]))

    def plain_summary(self) -> dict:
        """Numbers for the plain-language summary at the top of the quality report."""
        issues = self.merged_issues()
        raw = len(self.findings) + sum(sum(x.summary.values()) for x in self.external
                                       if not x.error and x.tool not in ("Cross-domain interoperability",
                                                                         "Scientific interoperability"))
        by = {k: sum(1 for i in issues if i["severity"] == k) for k in ("error", "warning", "info")}
        overlap = [i for i in issues if len(i["found_by"]) > 1]
        reasoner = next((x for x in self.external if x.tool == TOOLS["reasoner"].name), None)
        scores = self.scores()
        return {"issues": len(issues), "raw": raw, "by": by, "checks": self.checks_run(), "top": issues[:3],
                "overlap": len(overlap), "consistent": None if reasoner is None or reasoner.error else not any(
                    i.severity == "error" for i in reasoner.items),
                "reasoner_note": (reasoner.note if reasoner else ""), "scores": scores,
                "failed": [x.tool for x in self.external if x.error]}

    def checks_run(self) -> int:
        """Built-in rules plus every external check that ran (did not end in an error)."""
        return 1 + sum(1 for r in self.external if not r.error)

    def scores(self) -> list[dict]:
        """Scores of checks whose :class:`Tool` declares one (CDI, …), for the Overview tiles."""
        by_name = {t.name: t for t in TOOLS.values() if t.score}
        out = []
        for r in self.external:
            tool = by_name.get(r.tool)
            s = (r.provenance or {}).get("summary") or {}
            if tool is None or r.error or s.get(tool.score) is None:
                continue
            out.append({"tool": r.tool, "anchor": tool_anchor(r.tool), "value": float(s[tool.score]),
                        "passed": s.get(tool.verdict) if tool.verdict else None,
                        "threshold": (s.get("params") or {}).get("theta"),
                        # a count (SI) is shown as is, with its own note; a 0..1 score with two decimals
                        "display": s.get("display"), "note": s.get("display_note")})
        return out

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "totals": self.totals,
            "external": [r.to_dict() for r in self.external],
            "findings": [asdict(f) for f in self.findings],
            "rules": [
                {"id": r.id, "title": r.title, "severity": r.severity, "description": r.description}
                for r in self.rules_run
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
