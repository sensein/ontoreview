"""Compare two ontology versions (Bubastis-style changelog, computed locally)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from rdflib import BNode, Graph, Literal, URIRef

from ..config import Config
from ..loader import LoadedOntology, load_ontology
from ..model.axioms import ExpressionRenderer, expr_text, literal_text
from ..model.entities import Ref
from ..model.extract import Extractor, local_name


@dataclass
class TermChange:
    iri: str
    label: str
    kind: str
    curie: str | None = None
    anchor: str | None = None
    added: list[tuple[str, str]] = field(default_factory=list)  # (predicate, value)
    removed: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Changelog:
    old_version: str | None
    new_version: str | None
    added: list[TermChange] = field(default_factory=list)
    removed: list[TermChange] = field(default_factory=list)
    modified: list[TermChange] = field(default_factory=list)
    metadata_changes: list[TermChange] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.modified or self.metadata_changes)

    @property
    def summary(self) -> dict[str, int]:
        return {"added": len(self.added), "removed": len(self.removed), "modified": len(self.modified)}

    def to_dict(self) -> dict:
        return asdict(self) | {"summary": self.summary}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [f"# Changelog: {self.old_version or 'previous'} → {self.new_version or 'current'}", ""]
        for title, items in (("Added", self.added), ("Removed", self.removed), ("Modified", self.modified)):
            lines.append(f"## {title} ({len(items)})")
            lines.append("")
            for c in items:
                lines.append(f"- **{c.label}** (`{c.curie or c.iri}`, {c.kind.replace('_', ' ')})")
                if title == "Modified":
                    for p, v in c.added:
                        lines.append(f"  - ➕ {p}: {v}")
                    for p, v in c.removed:
                        lines.append(f"  - ➖ {p}: {v}")
            lines.append("")
        return "\n".join(lines)


def _statements(ext: Extractor, subject: URIRef) -> set[tuple[str, str]]:
    g = ext.g
    rend: ExpressionRenderer = ext.renderer
    out = set()
    for p, o in g.predicate_objects(subject):
        pname = ext.curie_or_iri(str(p))
        if isinstance(o, BNode):
            val = expr_text(rend.render(o))
        elif isinstance(o, Literal):
            val = literal_text(o, ext.curie_or_iri)
        else:
            val = ext.curie_or_iri(str(o))
        out.add((pname, val))
    # inverse structural statements carried by blank-node axioms are part of the subject anyway
    return out


def _onto_node(g: Graph):
    from ..loader import ontology_iri

    return ontology_iri(g)


def compare(old: LoadedOntology, new: LoadedOntology, config: Config | None = None) -> Changelog:
    config = config or Config()
    cfg = config.model_copy(update={"include_external": True, "include_individuals": True,
                                    "include_annotation_properties": True, "reason": False})
    e_old, e_new = Extractor(old, cfg), Extractor(new, cfg)
    o_old, o_new = e_old.extract(), e_new.extract()

    def change(t, ext) -> TermChange:
        return TermChange(t.iri, t.label, t.kind, t.curie, t.anchor)

    log = Changelog(o_old.metadata.version_info or o_old.metadata.version_iri,
                    o_new.metadata.version_info or o_new.metadata.version_iri)
    old_iris, new_iris = set(o_old.terms), set(o_new.terms)
    for iri in sorted(new_iris - old_iris, key=lambda i: o_new.terms[i].label.lower()):
        log.added.append(change(o_new.terms[iri], e_new))
    for iri in sorted(old_iris - new_iris, key=lambda i: o_old.terms[i].label.lower()):
        log.removed.append(change(o_old.terms[iri], e_old))
    for iri in sorted(old_iris & new_iris, key=lambda i: o_new.terms[i].label.lower()):
        a = _statements(e_old, URIRef(iri))
        b = _statements(e_new, URIRef(iri))
        if a != b:
            c = change(o_new.terms[iri], e_new)
            c.added = sorted(b - a)
            c.removed = sorted(a - b)
            log.modified.append(c)
    on, nn = _onto_node(old.graph), _onto_node(new.graph)
    if on is not None and nn is not None:
        a, b = _statements(e_old, on), _statements(e_new, nn)
        if a != b:
            c = TermChange(str(nn), "Ontology metadata", "ontology")
            c.added, c.removed = sorted(b - a), sorted(a - b)
            log.metadata_changes.append(c)
    return log


def compare_files(old: str, new: str, config: Config | None = None) -> Changelog:
    return compare(load_ontology(old), load_ontology(new), config)


__all__ = ["Changelog", "TermChange", "compare", "compare_files", "Ref", "local_name"]
