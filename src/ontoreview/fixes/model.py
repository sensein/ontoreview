"""Suggestions: what a fix would change, as triples to add and remove, never applied by itself.

Triples are kept as N3 strings (``<iri>``, ``"text"@en``) so a suggestion can be saved, shown and
compared without the graph; blank nodes are not used.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from rdflib import Graph
from rdflib.term import Node
from rdflib.util import from_n3

Triple = tuple[str, str, str]          # N3: subject, predicate, object

KINDS = {"D": "Rule", "A": "Aligner", "U": "Your input", "L": "AI draft", "M": "Manual"}


def n3(t: tuple[Node, Node, Node]) -> Triple:
    return (t[0].n3(), t[1].n3(), t[2].n3())


def term(s: str) -> Node:
    return from_n3(s)


@dataclass
class Option:
    """One way to fix a finding."""
    label: str
    add: list[Triple] = field(default_factory=list)
    remove: list[Triple] = field(default_factory=list)
    confidence: str = "high"        # high | medium | low
    reason: str = ""

    def apply_to(self, g: Graph) -> None:
        for s, p, o in self.remove:
            g.remove((term(s), term(p), term(o)))
        for s, p, o in self.add:
            g.add((term(s), term(p), term(o)))

    def turtle_diff(self) -> str:
        return "\n".join([f"- {s} {p} {o} ." for s, p, o in self.remove] + [f"+ {s} {p} {o} ." for s, p, o in self.add])


@dataclass
class Field_:
    """A value only the user knows (title, license, …), asked in a form."""
    name: str
    label: str
    kind: str = "text"              # text | textarea | license | creators | choice
    choices: list[tuple[str, str]] = field(default_factory=list)   # (value, label)
    value: str = ""                 # pre-filled guess, if any
    hint: str = ""


@dataclass
class Suggestion:
    rule: str                       # finding code, e.g. OB003, FX001
    subject: str | None             # term IRI, or the ontology IRI for header fixes
    kind: str                       # D | A | U | L | M
    title: str
    explanation: str = ""
    options: list[Option] = field(default_factory=list)
    fields: list[Field_] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)      # safe | guess | breaking
    required: bool = False          # docs are not generated until this is fixed
    made_by: dict = field(default_factory=dict)         # rule id, or AI source/model/revision
    checked: dict = field(default_factory=dict)         # pre-check: {"new_findings": [...]} per option
    reported_by: list[str] = field(default_factory=list)   # checks that found it: "ROBOT · missing_label", …
    severity: str = ""              # for findings from other checks (built-in ones use the report's)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            basis = f"{self.rule}|{self.subject}|{self.title}"
            self.id = hashlib.sha256(basis.encode()).hexdigest()[:12]

    @property
    def safe(self) -> bool:
        return "safe" in self.flags and len(self.options) == 1

    @property
    def source(self) -> str:
        return KINDS.get(self.kind, self.kind)

    def to_dict(self) -> dict:
        return asdict(self) | {"source": self.source}


def suggestion_from_dict(d: dict) -> Suggestion:
    """A suggestion saved with ``to_dict`` (e.g. an AI draft kept with a review that waits for later)."""
    d = {k: v for k, v in d.items() if k != "source"}
    opts = [Option(o["label"], [tuple(t) for t in o.get("add", [])], [tuple(t) for t in o.get("remove", [])],
                   o.get("confidence", "high"), o.get("reason", "")) for o in d.pop("options", [])]
    flds = [Field_(**{**f, "choices": [tuple(c) for c in f.get("choices", [])]}) for f in d.pop("fields", [])]
    return Suggestion(**d, options=opts, fields=flds)


__all__ = ["suggestion_from_dict", "Field_", "KINDS", "Option", "Suggestion", "Triple", "n3", "term"]
