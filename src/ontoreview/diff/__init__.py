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

    def to_html(self, title: str = "", old_label: str = "", new_label: str = "") -> str:
        """A standalone, accessible HTML report (no external resources; prints well)."""
        import html as _h
        from datetime import date

        from .. import __version__

        e = _h.escape
        old_v, new_v = self.old_version or old_label or "previous", self.new_version or new_label or "current"
        modified = self.metadata_changes + self.modified
        counts = {"added": len(self.added), "removed": len(self.removed), "modified": len(modified)}

        def term_rows(kind: str, items: list[TermChange]) -> str:
            rows = []
            for c in items:
                det = "".join([f'<li class="plus"><span class="sr">added </span>+ {e(p)}: {e(v)}</li>' for p, v in c.added]
                              + [f'<li class="minus"><span class="sr">removed </span>− {e(p)}: {e(v)}</li>' for p, v in c.removed])
                rows.append(f'<tr><td><span class="badge {kind}">{kind.capitalize()}</span></td>'
                            f'<th scope="row">{e(c.label)}<div class="id">{e(c.curie or c.iri)}</div></th>'
                            f'<td>{e(c.kind.replace("_", " "))}</td><td>{f"<ul>{det}</ul>" if det else ""}</td></tr>')
            return "".join(rows)

        body = term_rows("added", self.added) + term_rows("removed", self.removed) + term_rows("modified", modified)
        table = (f'<table><caption>All changes, {sum(counts.values())} in total</caption><thead><tr>'
                 '<th scope="col">Change</th><th scope="col">Term</th><th scope="col">Kind</th>'
                 f'<th scope="col">Details</th></tr></thead><tbody>{body}</tbody></table>'
                 if body else '<p class="none">No differences between the two versions.</p>')
        heading = e(title or "Ontology changes")
        files = (f'<p class="files">{e(old_label)} → {e(new_label)}</p>' if old_label or new_label else "")
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="OntoReview {__version__}"><title>{heading}: {e(old_v)} → {e(new_v)}</title>
<style>
:root{{--bg:#fff;--ink:#101828;--muted:#5B6675;--line:#E2E7EC;--soft:#F4F6F8;--ok-bg:#ECFDF3;--ok:#067647;--err-bg:#FEF3F2;--err:#B42318;--warn-bg:#FFFAEB;--warn:#93370D;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#121A26;--ink:#E6EAF0;--muted:#98A2B3;--line:#253041;--soft:#1B2533;--ok-bg:#0B2A1C;--ok:#6CE9A6;--err-bg:#3A1410;--err:#FDA29B;--warn-bg:#3A2A0A;--warn:#FEC84B;color-scheme:dark}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:40px 20px}}h1{{margin:0 0 4px;font-size:26px}}.sub,.files,.foot{{color:var(--muted);margin:0}}
.files{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;margin-top:6px;word-break:break-all}}
.tiles{{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}}.tile{{flex:1 1 160px;border-radius:10px;padding:14px 16px}}
.tile b{{display:block;font-size:28px}}.tile.added{{background:var(--ok-bg);color:var(--ok)}}.tile.removed{{background:var(--err-bg);color:var(--err)}}.tile.modified{{background:var(--warn-bg);color:var(--warn)}}
table{{width:100%;border-collapse:collapse;font-size:14px}}caption{{text-align:left;color:var(--muted);padding-bottom:8px}}
thead th{{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);background:var(--soft);padding:8px 10px}}
td,tbody th{{text-align:left;vertical-align:top;padding:10px;border-top:1px solid var(--line);font-weight:400}}tbody th{{font-weight:600}}
.id{{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:var(--muted);font-weight:400;word-break:break-all}}
ul{{margin:0;padding:0;list-style:none;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px}}li{{word-break:break-word}}
.plus{{color:var(--ok)}}.minus{{color:var(--err)}}.badge{{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600}}
.badge.added{{background:var(--ok-bg);color:var(--ok)}}.badge.removed{{background:var(--err-bg);color:var(--err)}}.badge.modified{{background:var(--warn-bg);color:var(--warn)}}
.sr{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}.none{{padding:24px;background:var(--soft);border-radius:10px}}
.foot{{margin-top:28px;font-size:13px}}@media print{{body{{background:#fff;color:#000}}tr{{break-inside:avoid}}}}
</style></head><body><main>
<h1>{heading}</h1><p class="sub">Version {e(old_v)} → {e(new_v)} · compared {date.today().isoformat()}</p>{files}
<div class="tiles" role="list"><div class="tile added" role="listitem"><b>{counts['added']}</b>added</div>
<div class="tile removed" role="listitem"><b>{counts['removed']}</b>removed</div>
<div class="tile modified" role="listitem"><b>{counts['modified']}</b>modified</div></div>
{table}
<p class="foot">Terms are matched by IRI; modified terms list the statements added (+) and removed (−). Generated by OntoReview {__version__}.</p>
</main></body></html>
"""

    def to_markdown(self) -> str:
        lines = [f"# Changelog: {self.old_version or 'previous'} → {self.new_version or 'current'}", ""]
        for title, items in (("Added", self.added), ("Removed", self.removed),
                             ("Modified", self.metadata_changes + self.modified)):
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


def _shared_prefixes(old: list[tuple[str, str]], new: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Prefixes for writing the new version: the previous version's prefix for every namespace both
    use, so renaming a prefix (same IRIs) is not reported as a change; new namespaces keep their own
    prefix unless that name already means something else."""
    by_ns = {ns: p for p, ns in old}
    names = {p for p, _ in old}
    out = list(old)
    for p, ns in new:
        if ns not in by_ns and p not in names:
            out.append((p, ns))
            names.add(p)
    return sorted(out, key=lambda x: -len(x[1]))


def _onto_node(g: Graph):
    from ..loader import ontology_iri

    return ontology_iri(g)


def compare(old: LoadedOntology, new: LoadedOntology, config: Config | None = None) -> Changelog:
    config = config or Config()
    cfg = config.model_copy(update={"include_external": True, "include_individuals": True,
                                    "include_annotation_properties": True,
                                    "include_used_annotation_properties": False, "reason": False})
    e_old, e_new = Extractor(old, cfg), Extractor(new, cfg)
    e_new._prefixes = _shared_prefixes(e_old._prefixes, e_new._prefixes)
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
