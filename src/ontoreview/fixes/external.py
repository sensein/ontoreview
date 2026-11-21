"""Fixes for the other checks of the quality report: ROBOT, the reasoner, IRI checks, OntoCheck and
OOPS! (the interoperability scores are measurements, not defects, and get no fixes).

A finding that means the same as a built-in rule (ROBOT missing_label, OntoCheck checkLabel, OOPS! P08 …)
reuses that rule's fixer for every element it names; when the suggestion already exists it is merged and
tagged with the check ("also reported by ROBOT"). Findings without an automatic fix become manual items
that carry the checker's own explanation, so every finding of the report appears in the review.
"""

from __future__ import annotations

from ..report.models import Finding
from .model import Suggestion
from .rules import FIXERS

INTEROP = ("Cross-domain interoperability", "Scientific interoperability")

# (check, code) -> built-in rule(s) whose fixer handles each element the finding names
MAP: dict[tuple[str, str], tuple[str, ...]] = {
    ("ROBOT", "missing_label"): ("OB010",), ("ROBOT", "missing_definition"): ("OB011",),
    ("ROBOT", "multiple_labels"): ("OB017",), ("ROBOT", "missing_superclass"): ("OB023",),
    ("ROBOT", "missing_ontology_title"): ("OB001",), ("ROBOT", "missing_ontology_description"): ("OB002",),
    ("ROBOT", "missing_ontology_license"): ("OB003",), ("ROBOT", "label_whitespace"): ("FX001",),
    ("ROBOT", "annotation_whitespace"): ("FX001",), ("ROBOT", "lowercase_definition"): ("FX002",),
    ("OntoCheck", "checkLabel"): ("OB010",), ("OntoCheck", "definitionCheck"): ("OB011",),
    ("OntoCheck", "isolatedElements"): ("OB023",), ("OntoCheck", "missingDomainRange"): ("OB012", "OB013"),
    ("OntoCheck", "humanLicense"): ("OB003",),
    ("OOPS!", "P04"): ("OB023",), ("OOPS!", "P08"): ("OB010", "OB011"), ("OOPS!", "P11"): ("OB012", "OB013"),
    ("OOPS!", "P34"): ("OB015",), ("OOPS!", "P35"): ("OB015",), ("OOPS!", "P41"): ("OB003",),
    ("OOPS!", "P22"): ("OB019",), ("OOPS!", "P19"): ("OB028",), ("OOPS!", "P38"): ("OB001",),
    ("IRI checks", "no_ontology_header"): ("OB001",),
}
# the same problem as a built-in rule that has no automatic fix: merged in the quality report's
# "Issues at a glance", but not turned into fix suggestions
SAME_ISSUE: dict[tuple[str, str], tuple[str, ...]] = {
    ("ROBOT", "duplicate_label"): ("OB016",), ("OntoCheck", "duplicateLabels"): ("OB016",),
    ("OOPS!", "P32"): ("OB016",),
}
ONTOLOGY_LEVEL = ("OB001", "OB002", "OB003", "OB004", "OB005", "OB006")


def _applies(rule: str, iri: str | None, session) -> bool:
    """Whether a built-in rule's fix makes sense for this element (P08 means label *or* definition)."""
    t = session.onto.terms.get(iri or "")
    if rule == "OB010":
        return t is not None and not t.labels
    if rule == "OB011":
        return t is not None and not t.definition
    if rule in ("OB012", "OB013"):
        return t is not None and not (t.domain if rule == "OB012" else t.range)
    return True


def external_suggestions(session, reports) -> list[Suggestion]:
    """Merge the findings of the other checks into the session; returns the suggestions added."""
    added: list[Suggestion] = []
    by_key = {(x.rule, x.subject): x for x in session.suggestions}
    onto_iri = session.onto.metadata.iri
    for rep in reports or []:
        if rep.tool in INTEROP or rep.error:
            continue
        for item in rep.items:
            tag = f"{rep.tool} · {item.code}"
            rules = MAP.get((rep.tool, item.code))
            targets = item.affected or [None]
            handled = False
            for rule in rules or ():
                for iri in targets:
                    subject = onto_iri if rule in ONTOLOGY_LEVEL else iri
                    if not _applies(rule, subject, session):
                        continue
                    existing = by_key.get((rule, subject)) or (
                        next((x for x in session.suggestions if x.rule == rule), None) if rule in ONTOLOGY_LEVEL else None)
                    if existing is not None:
                        if tag not in existing.reported_by:
                            existing.reported_by.append(tag)
                        handled = True
                        continue
                    fn = FIXERS.get(rule)
                    if fn is None or (rule not in ONTOLOGY_LEVEL and subject is None):
                        continue
                    msg = f"`{subject}` is used but not declared." if rule == "OB015" else item.name
                    s = fn(Finding(rule, item.name, item.severity, msg, subject=subject), session.graph, session.onto)
                    if s is None:
                        continue
                    s.reported_by.append(tag)
                    s.severity = item.severity
                    session.suggestions.append(s)
                    by_key[(s.rule, s.subject)] = s
                    added.append(s)
                    handled = True
            if not handled:         # no automatic fix: show the checker's explanation
                names = [session.onto.terms[a].label if a in session.onto.terms else a for a in item.affected[:10]]
                more = f" … and {len(item.affected) - 10} more" if len(item.affected) > 10 else ""
                text = " ".join(x for x in (item.description, item.note) if x)
                if names:
                    text += f" Affected: {', '.join(names)}{more}."
                s = Suggestion(f"{rep.tool}:{item.code}", item.affected[0] if len(item.affected) == 1 else None, "M",
                               item.name, text.strip() or f"Reported by {rep.tool}.",
                               made_by={"type": "check", "id": tag}, reported_by=[tag], severity=item.severity)
                if s.id not in {x.id for x in session.suggestions}:
                    session.suggestions.append(s)
                    added.append(s)
    return added


__all__ = ["INTEROP", "MAP", "external_suggestions"]
