"""A fix session: findings → suggestions → user decisions → a new ontology file.

    s = FixSession("a.ttl")
    s.accept(sid)                         # an exact fix (option 0)
    s.accept(sid, values={"license": …})  # a value only the user knows
    s.accept(sid, text="A cell that …")   # an AI draft, possibly edited
    result = s.write()                    # a-v1.ttl + a-v1.patch.ru + a-v1.fixes.json; a.ttl untouched

Every suggestion is tested on a copy before it is shown (``precheck``) and the written file is
checked again. Nothing is applied without ``accept``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rdflib import Graph

from .. import __version__
from .model import Option, Suggestion, term
from .rules import FIXERS, missing_values, resolve_fields, text_scans

FORMATS = {".ttl": "turtle", ".owl": "xml", ".rdf": "xml", ".xml": "xml", ".jsonld": "json-ld", ".nt": "nt",
           ".n3": "n3", ".trig": "trig"}
VERSION_RE = re.compile(r"^(?P<stem>.+)-v(?P<n>\d+)$")
LINKML = (".yaml", ".yml")
LINKML_RULES = ("OB001", "OB002", "OB003", "OB004", "OB005")      # schema-level values a YAML copy can carry
LINKML_TERM_RULES = ("OB010", "OB011", "OB012", "OB013", "FX010")  # per class/slot/enum: title, description, …


class FixError(ValueError):
    """A fix cannot be applied (missing value, LinkML source, …); the message says why."""


class MissingMetadata(ValueError):
    """The docs are not generated while required metadata is missing."""

    def __init__(self, missing: list[str], source: str = ""):
        self.missing = missing
        super().__init__(
            f"Docs not generated: {Path(source).name or 'the ontology'} has no {', '.join(missing)}. Add them in the "
            "app's review step, with `ontoreview fix apply` (writes a fixed copy), or in ontoreview.toml [metadata]. "
            "To build anyway, set require_metadata = false.")


def check_required(onto, cfg, source: str = "") -> None:
    """Raise MissingMetadata when the config requires metadata that the ontology lacks."""
    if getattr(cfg, "require_metadata", True):
        missing = required_missing(onto)
        if missing:
            raise MissingMetadata(missing, source)


def required_missing(onto) -> list[str]:
    """The required metadata the docs cannot be generated without (ontology or [metadata])."""
    m = onto.metadata
    return [name for name, ok in (("title", m.title), ("description", m.description or m.abstract),
                                  ("license", m.license), ("creators", m.creators)) if not ok]


def next_version(source: Path) -> Path:
    """a.ttl → a-v1.ttl; a-v1.ttl → a-v2.ttl; never an existing file."""
    m = VERSION_RE.match(source.stem)
    stem, n = (m.group("stem"), int(m.group("n")) + 1) if m else (source.stem, 1)
    suffix = source.suffix if source.suffix.lower() in FORMATS or source.suffix.lower() in LINKML else ".ttl"
    while (out := source.with_name(f"{stem}-v{n}{suffix}")).exists():
        n += 1
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _keyed(report) -> dict[tuple, str]:
    """Findings by (rule, term), or (rule, message) for ontology-level ones: a fix that only rewords
    a finding (a new label appears in its message) is not counted as a new problem."""
    return {(f.rule, f.subject or f.message): f"{f.rule} {f.message}" for f in report.findings}


def _diff(before, after) -> tuple[list[str], list[str]]:
    """(fixed, new) finding messages between two reports."""
    b, a = _keyed(before), _keyed(after)
    return sorted(b[k] for k in b.keys() - a.keys()), sorted(a[k] for k in a.keys() - b.keys())


@dataclass
class Accepted:
    suggestion: Suggestion
    option: Option
    edited: bool = False
    values: dict = field(default_factory=dict)          # what the user typed, for U fixes
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


@dataclass
class WriteResult:
    path: Path
    patch: Path
    record: Path
    applied: int
    not_applied: int
    fixed: list[str]
    new_findings: list[str]
    before: dict
    after: dict


class FixSession:
    def __init__(self, source: str | Path, config=None, **overrides):
        from ..build import load, resolve_config
        from ..model.extract import extract
        from ..quality_checks import run_checks

        self._extract, self._run_checks = extract, run_checks
        self.cfg = resolve_config(source, config, **overrides)
        self.loaded = load(self.cfg)
        self.source = Path(self.loaded.source)
        self.graph: Graph = self.loaded.graph
        self.onto = extract(self.loaded, self.cfg)
        self.report = run_checks(self.onto, self.graph, self.cfg)
        self.accepted: dict[str, Accepted] = {}
        self.external: list | None = None              # reports of the other checks, once run
        self.suggestions: list[Suggestion] = []
        seen = set()
        for f in self.report.findings:
            fn = FIXERS.get(f.rule)
            s = fn(f, self.graph, self.onto) if fn else None
            if s is not None and s.id not in seen:
                seen.add(s.id)
                self.suggestions.append(s)
        for s in text_scans(self.graph, self.onto):
            if s.id not in seen:
                seen.add(s.id)
                self.suggestions.append(s)
        order = {"U": 0, "D": 1, "A": 2, "L": 3, "M": 4}
        self.suggestions.sort(key=lambda s: (not s.required, order.get(s.kind, 9), s.rule, s.subject or ""))

    # ------------------------------------------------------------ the other checks
    def run_external(self) -> list:
        """Run ROBOT, the reasoner, IRI checks, OntoCheck and OOPS! (as configured; not the interoperability
        scores) and merge their findings as suggestions. Returns the reports (errors included)."""
        from ..quality_checks.evaluators import run_evaluations
        from .external import external_suggestions
        ev = self.cfg.evaluation.model_copy(update={"cdi": "off", "si": "off"})
        cfg = self.cfg.model_copy(update={"evaluation": ev})
        reports = run_evaluations(self.loaded.graph, cfg, self.loaded.source, self.onto.namespace)
        added = external_suggestions(self, reports)
        self.precheck([x for x in added if x.options])
        self.external = reports
        return reports

    # ------------------------------------------------------------ queries
    def get(self, sid: str) -> Suggestion:
        for s in self.suggestions:
            if s.id == sid:
                return s
        raise FixError(f"No suggestion {sid}.")

    def required_open(self) -> list[Suggestion]:
        """Required metadata not yet fixed: the docs wait for these."""
        return [s for s in self.suggestions if s.required and s.id not in self.accepted]

    def replace(self, s: Suggestion) -> Suggestion:
        """Add ``s`` instead of the open suggestions for the same finding and term (e.g. an AI draft
        replacing the empty "type a definition" field)."""
        self.suggestions = [x for x in self.suggestions
                            if not (x.rule == s.rule and x.subject == s.subject and x.id not in self.accepted)]
        self.suggestions.append(s)
        return s

    def add(self, s: Suggestion) -> Suggestion:
        """Add a suggestion made elsewhere (e.g. an AI draft)."""
        if s.id not in {x.id for x in self.suggestions}:
            self.suggestions.append(s)
        return s

    # ------------------------------------------------------------ pre-check on a copy
    def _copy(self) -> tuple[Graph, Graph]:
        g = Graph()
        for p, n in self.graph.namespaces():
            g.bind(p, n, override=True, replace=True)       # keeps the default ":" prefix
        g += self.graph
        full = Graph()
        full += self.loaded.full_graph
        return g, full

    def _findings_after(self, options: list[Option]):
        g, full = self._copy()
        for o in options:
            o.apply_to(g)
            o.apply_to(full)
        loaded = dataclasses.replace(self.loaded, graph=g, full_graph=full)
        onto = self._extract(loaded, self.cfg)
        return self._run_checks(onto, g, self.cfg), g

    def baseline(self):
        """The findings of an unchanged copy: compared with each fixed copy, only real changes differ."""
        if getattr(self, "_baseline", None) is None:
            self._baseline, _ = self._findings_after([])
        return self._baseline

    def precheck(self, suggestions: list[Suggestion] | None = None) -> None:
        """Test each option on a copy: record findings it would add (shown as a warning)."""
        before = self.baseline()
        for s in suggestions or self.suggestions:
            if not s.options:
                continue
            s.checked = {"options": []}
            for o in s.options:
                after, _ = self._findings_after([o])
                fixed, new = _diff(before, after)
                s.checked["options"].append({"fixed": fixed, "new_findings": new})

    # ------------------------------------------------------------ decisions
    def accept(self, sid: str, option: int = 0, values: dict | None = None, text: str | None = None) -> Accepted:
        s = self.get(sid)
        if s.kind == "M":
            raise FixError("Manual issues have no automatic fix; edit the ontology yourself.")
        if s.fields:
            missing = missing_values(s, values or {})
            if missing:
                raise FixError(f"Fill in: {', '.join(missing)}.")
            chosen = resolve_fields(s, values or {}, self.graph, self.onto)
            edited = True
        elif text is not None and s.kind == "L":
            o = s.options[option]
            chosen = Option(o.label, add=[(a, b, term_text(c, text)) for a, b, c in o.add], remove=o.remove,
                            confidence=o.confidence, reason=o.reason)
            edited = text.strip() != literal_text(o.add[0][2]) if o.add else True
        else:
            chosen, edited = s.options[option], False
        self.accepted[sid] = Accepted(s, chosen, edited, dict(values or {}))
        return self.accepted[sid]

    def accept_safe(self) -> int:
        n = 0
        for s in self.suggestions:
            if s.safe and s.id not in self.accepted:
                self.accept(s.id)
                n += 1
        return n

    def reject(self, sid: str) -> None:
        self.accepted.pop(sid, None)

    # ------------------------------------------------------------ write
    @property
    def is_linkml(self) -> bool:
        return self.loaded.source_kind == "linkml"

    def supported(self, s: Suggestion) -> bool:
        """Whether the fix can be written for this source. LinkML: schema-level values, and the title,
        description, domain and range of classes, slots and enums defined in this file (not imported ones)."""
        if not self.is_linkml or s.rule in LINKML_RULES:
            return True
        return s.rule in LINKML_TERM_RULES and linkml_element(self._linkml_data(), s.subject) is not None

    def _linkml_data(self) -> dict:
        if getattr(self, "_yaml", None) is None:
            import yaml
            try:
                self._yaml = yaml.safe_load(self.source.read_text("utf-8")) or {}
            except (OSError, yaml.YAMLError):
                self._yaml = {}
        return self._yaml

    def write(self, out: str | Path | None = None) -> WriteResult:
        if not self.accepted:
            raise FixError("No fix accepted.")
        unsupported = [a.suggestion.title for a in self.accepted.values() if not self.supported(a.suggestion)]
        if unsupported:
            raise FixError(f"These cannot be written into the LinkML schema (terms from imported files, or a change "
                           f"LinkML has no key for): {', '.join(unsupported)}.")
        order = {"U": 0, "L": 1, "D": 2, "A": 3}        # annotations first, logical changes after
        accepted = sorted(self.accepted.values(), key=lambda a: order.get(a.suggestion.kind, 9))
        stale = [a.suggestion.title for a in accepted
                 for s_, p_, o_ in a.option.remove if (term(s_), term(p_), term(o_)) not in self.graph]
        if stale:
            raise FixError(f"The ontology changed since the check; run it again ({stale[0]}).")
        after, g = self._findings_after([a.option for a in accepted])
        path = Path(out) if out else next_version(self.source)
        if self.is_linkml:
            patch = path.with_name(path.stem + ".patch.yaml")
            write_linkml(self.source, path, patch, accepted)
        else:
            fmt = FORMATS.get(path.suffix.lower(), "turtle")
            g.serialize(destination=str(path), format=fmt)
            patch = path.with_name(path.stem + ".patch.ru")
            patch.write_text(sparql_update(accepted), "utf-8")
        fixed, new = _diff(self.baseline(), after)
        record = path.with_name(path.stem + ".fixes.json")
        not_applied = [s for s in self.suggestions if s.id not in self.accepted and s.kind != "M"]
        record.write_text(json.dumps({
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "tool": {"name": "OntoReview", "version": __version__},
            "source": {"path": str(self.source), "name": self.source.name, "sha256": sha256(self.source)},
            "output": {"path": str(path), "name": path.name, "sha256": sha256(path)},
            "applied": [{"id": a.suggestion.id, "rule": a.suggestion.rule, "subject": a.suggestion.subject,
                         "kind": a.suggestion.kind, "source": a.suggestion.source, "title": a.suggestion.title,
                         "option": a.option.label, "add": a.option.add, "remove": a.option.remove,
                         "edited": a.edited, "made_by": a.suggestion.made_by, "accepted_at": a.at,
                         "ai_assisted": a.suggestion.made_by.get("type") == "llm"} for a in accepted],
            "not_applied": [{"id": s.id, "rule": s.rule, "subject": s.subject, "title": s.title} for s in not_applied],
            "checks": {"before": self.report.summary, "after": after.summary, "fixed": fixed, "new": new},
        }, indent=2, ensure_ascii=False), "utf-8")
        return WriteResult(path, patch, record, len(accepted), len(not_applied), fixed, new,
                           self.report.summary, after.summary)


def linkml_values(accepted: list[Accepted]) -> dict:
    """The schema keys the accepted fixes set: title, description, license, version, created_by."""
    from .rules import creator_text, parse_creators
    keys: dict = {}
    for a in accepted:
        v = a.values
        if a.suggestion.rule == "OB001":
            keys["title"] = v.get("title", "").strip()
        elif a.suggestion.rule == "OB002":
            keys["description"] = v.get("description", "").strip()
        elif a.suggestion.rule == "OB003":
            keys["license"] = v.get("license", "").strip()
        elif a.suggestion.rule == "OB004":
            keys["version"] = v.get("version", "").strip()
        elif a.suggestion.rule == "OB005":
            keys["created_by"] = [creator_text(c) for c in parse_creators(v.get("creators", ""))]
    return {k: x for k, x in keys.items() if x}


def _local(iri: str) -> str:
    return str(iri).rstrip("/").rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def linkml_element(data: dict, iri: str | None) -> tuple[str, str] | None:
    """(section, name) of the class, slot or enum in this schema file that a term IRI stands for."""
    if not iri or not isinstance(data, dict):
        return None
    name = _local(iri)
    for section in ("classes", "slots", "enums"):
        items = data.get(section) or {}
        if isinstance(items, dict):
            for key in items:
                if key == name or str(key).replace(" ", "_") == name or str(key).replace(" ", "") == name:
                    return section, key
    return None


XSD_TO_LINKML = {"string": "string", "boolean": "boolean", "integer": "integer", "int": "integer",
                 "decimal": "decimal", "double": "double", "float": "float", "dateTime": "datetime", "date": "date",
                 "anyURI": "uri", "time": "time"}
DEF_PREDS = ("http://www.w3.org/2004/02/skos/core#definition", "http://purl.obolibrary.org/obo/IAO_0000115",
             "http://www.w3.org/2000/01/rdf-schema#comment")
LABEL_PREDS = ("http://www.w3.org/2000/01/rdf-schema#label", "http://www.w3.org/2004/02/skos/core#prefLabel")


def linkml_term_edits(data: dict, accepted: list[Accepted]) -> dict:
    """{section: {name: {key: value}}} for the accepted term fixes: description, title, domain, range."""
    edits: dict = {}
    for a in accepted:
        if a.suggestion.rule not in LINKML_TERM_RULES:
            continue
        for s_, p_, o_ in a.option.add:
            subj, pred, obj = term(s_), str(term(p_)), term(o_)
            where = linkml_element(data, str(subj))
            if where is None:
                continue
            if pred in DEF_PREDS:
                key, val = "description", str(obj)
            elif pred in LABEL_PREDS:
                key, val = "title", str(obj)
            elif pred.endswith("#domain") or pred.endswith("#range"):
                key = "domain" if pred.endswith("#domain") else "range"
                loc = _local(str(obj))
                val = XSD_TO_LINKML.get(loc, loc) if "XMLSchema" in str(obj) else \
                    ((linkml_element(data, str(obj)) or (None, loc))[1])
            else:
                continue
            edits.setdefault(where[0], {}).setdefault(where[1], {})[key] = val
    return edits


def write_linkml(source: Path, path: Path, patch: Path, accepted: list[Accepted]) -> None:
    """A copy of the LinkML schema with the fixed keys: schema-level values and, per class/slot/enum,
    description, title, domain and range (comments are not kept: the patch lists exactly what was set,
    to copy into the original by hand if preferred)."""
    import yaml
    data = yaml.safe_load(source.read_text("utf-8")) or {}
    keys = linkml_values(accepted)
    data.update(keys)
    edits = linkml_term_edits(data, accepted)
    for section, items in edits.items():
        for name, vals in items.items():
            el = data[section].get(name)
            if not isinstance(el, dict):
                el = data[section][name] = {}
            el.update(vals)
    done = list(keys) + [f"{n}.{k}" for items in edits.values() for n, v in items.items() for k in v]
    header = (f"# Generated by OntoReview from {source.name}: the original is unchanged. Fixed keys: "
              f"{', '.join(done[:12])}{' …' if len(done) > 12 else ''}.\n")
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), "utf-8")
    patch.write_text("# Generated by OntoReview: the keys added to the schema.\n"
                     + yaml.safe_dump({**keys, **edits}, sort_keys=False, allow_unicode=True, width=100), "utf-8")


def literal_text(n3_text: str) -> str:
    return str(term(n3_text))


def term_text(n3_text: str, text: str) -> str:
    """Replace the text of an N3 literal, keeping its language or datatype."""
    from rdflib import Literal
    old = term(n3_text)
    return Literal(text.strip(), lang=getattr(old, "language", None),
                   datatype=getattr(old, "datatype", None)).n3()


def sparql_update(accepted: list[Accepted]) -> str:
    """The accepted changes as SPARQL Update, to apply in another editor or triple store."""
    rem = list(dict.fromkeys(f"  {s} {p} {o} ." for a in accepted for s, p, o in a.option.remove))
    add = list(dict.fromkeys(f"  {s} {p} {o} ." for a in accepted for s, p, o in a.option.add))
    parts = ["# Generated by OntoReview: the accepted fixes as SPARQL Update."]
    if rem:
        parts.append("DELETE DATA {\n" + "\n".join(rem) + "\n} ;")
    if add:
        parts.append("INSERT DATA {\n" + "\n".join(add) + "\n}")
    return "\n".join(parts) + "\n"


def fixes_record(source: str | Path) -> dict | None:
    """The record written with a fixed version (a-v1.fixes.json next to a-v1.ttl), if any."""
    p = Path(str(source))
    rec = p.with_name(p.stem + ".fixes.json")
    if rec.is_file():
        try:
            return json.loads(rec.read_text("utf-8"))
        except ValueError:
            return None
    return None


__all__ = ["Accepted", "MissingMetadata", "check_required", "FixError", "FixSession", "WriteResult", "fixes_record", "next_version", "required_missing",
           "sparql_update"]
