"""Export the documentation model as Markdown (MkDocs/Docusaurus) or MyST (Sphinx)."""

from __future__ import annotations

from pathlib import Path

from .model.axioms import expr_text
from .model.entities import KIND_SLUGS, Ontology, Ref, Term
from .telemetry import api as _api


def _link(r: Ref, myst: bool) -> str:
    if r.internal and r.anchor and r.kind:
        page = KIND_SLUGS[r.kind]
        if myst:
            return f"[{r.label}]({page}.md#{r.anchor.lower()})"
        return f"[{r.label}]({page}.md#{r.anchor.lower()})"
    return f"[{r.label}]({r.iri})"


def _expr_md(expr, myst: bool) -> str:
    out = []
    for k, v in expr:
        if k == "ref":
            out.append(_link(v, myst))
        elif k == "kw":
            out.append(f"*{v}*")
        elif k == "lit":
            out.append(f"`{v}`")
        else:
            out.append(str(v))
    return "".join(out)


def _term_md(t: Term, myst: bool) -> str:
    lines = []
    if myst:
        lines.append(f"({t.anchor.lower()})=")
    dep = " ~~deprecated~~" if t.deprecated else ""
    lines.append(f"### {t.label}{dep}")
    lines.append("")
    lines.append(f"**IRI:** `{t.iri}`" + (f" · `{t.curie}`" if t.curie else ""))
    lines.append("")
    if t.definition:
        lines += [t.definition, ""]
    for c in t.comments:
        lines += [c, ""]
    rows: list[tuple[str, str]] = []

    def refs(label, items):
        if items:
            rows.append((label, ", ".join(_link(r, myst) for r in items)))

    def exprs(label, items):
        if items:
            rows.append((label, "; ".join(_expr_md(e, myst) for e in items)))

    refs("Superclasses", t.superclasses)
    exprs("Restrictions", t.restrictions)
    exprs("Equivalent to", t.equivalent)
    refs("Subclasses", t.subclasses)
    refs("Disjoint with", t.disjoint)
    refs("Super-properties", t.super_properties)
    refs("Sub-properties", t.sub_properties)
    exprs("Domain", t.domain)
    exprs("Range", t.range)
    if t.characteristics:
        rows.append(("Characteristics", ", ".join(t.characteristics)))
    exprs("Inverse of", t.inverse_of)
    exprs("Property chain", t.chains)
    exprs("Types", t.types)
    refs("Broader", t.broader)
    refs("Narrower", t.narrower)
    refs("Instances", t.instances)
    if t.used_in:
        rows.append(("Used in", "; ".join(f"{u.role} {_link(u.ref, myst)}" for u in t.used_in)))
    if t.examples:
        rows.append(("Examples", "; ".join(f"`{e}`" for e in t.examples)))
    for a in t.annotations:
        rows.append((a.prop.label, "; ".join(expr_text(v) for v in a.values)))
    if rows:
        lines += ["| | |", "|---|---|"]
        for k, v in rows:
            cell = v.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {k} | {cell} |")
        lines.append("")
    return "\n".join(lines)


@_api("export_markdown")
def export_markdown(onto: Ontology, out: Path, myst: bool = False, cqs=None) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    m = onto.metadata
    written = []
    idx = [f"# {m.title or 'Ontology'}", ""]
    if m.iri:
        idx += [f"**IRI:** `{m.iri}`", ""]
    if m.version_info:
        idx += [f"**Version:** {m.version_info}", ""]
    if m.creators:
        idx += ["**Authors:** " + ", ".join(a.name for a in m.creators), ""]
    if m.license:
        idx += [f"**License:** [{m.license_label or m.license}]({m.license})", ""]
    if m.abstract:
        idx += [m.abstract, ""]
    if m.description:
        idx += [m.description, ""]
    idx += ["## Contents", ""]
    for kind in onto.kinds_present():
        from .model.entities import KIND_LABELS

        idx.append(f"- [{KIND_LABELS[kind][1]}]({KIND_SLUGS[kind]}.md) ({onto.stats.get(kind, 0)})")
    if cqs is not None and cqs.questions:
        idx.append(f"- [Competency questions](competency-questions.md) ({len(cqs.questions)})")
    if myst:
        pages = [KIND_SLUGS[k] for k in onto.kinds_present()]
        if cqs is not None and cqs.questions:
            pages.append("competency-questions")
        idx += ["", "```{toctree}", ":hidden:", ""] + pages + ["```"]
    p = out / "index.md"
    p.write_text("\n".join(idx) + "\n", "utf-8")
    written.append(p)
    for kind in onto.kinds_present():
        from .model.entities import KIND_LABELS

        body = [f"# {KIND_LABELS[kind][1]}", ""]
        for t in onto.by_kind(kind):
            body.append(_term_md(t, myst))
        p = out / f"{KIND_SLUGS[kind]}.md"
        p.write_text("\n".join(body) + "\n", "utf-8")
        written.append(p)
    if cqs is not None and cqs.questions:
        p = out / "competency-questions.md"
        p.write_text(cq_markdown(cqs, myst), "utf-8")
        written.append(p)
    return written


STATUS_TEXT = {"passed": "answerable", "failed": "not answerable", "error": "query error",
               "untested": "not tested"}


def cq_markdown(cqs, myst: bool = False) -> str:
    lines = ["# Competency questions", ""]
    for q in cqs.questions:
        if myst:
            lines.append(f"({q.anchor})=")
        lines += [f"### {q.id}. {q.question}", "", f"**Status:** {STATUS_TEXT.get(q.status, q.status)}"
                  + (f" ({q.total_rows} results)" if q.status in ("passed", "failed") else ""), ""]
        if q.term_refs:
            lines += ["**Terms:** " + ", ".join(_link(r, myst) for r in q.term_refs), ""]
        if q.answer:
            lines += [f"**Expected answer:** {q.answer}", ""]
        if q.notes:
            lines += [q.notes, ""]
        if q.sparql:
            lines += ["```sparql", q.sparql.strip(), "```", ""]
        if q.error:
            lines += [f"Error: {q.error}", ""]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------- LLM / agent files
def _term_json(t: Term) -> dict:
    def refs(items):
        return [r.curie or r.iri for r in items]

    def exprs(items):
        return [expr_text(e) for e in items]

    d = {
        "iri": t.iri, "curie": t.curie, "kind": t.kind, "label": t.label,
        "definition": t.definition, "comments": t.comments, "synonyms": t.alt_labels,
        "examples": t.examples, "deprecated": t.deprecated,
        "superclasses": refs(t.superclasses), "subclasses": refs(t.subclasses),
        "restrictions": exprs(t.restrictions), "equivalent_to": exprs(t.equivalent),
        "disjoint_with": refs(t.disjoint), "super_properties": refs(t.super_properties),
        "sub_properties": refs(t.sub_properties), "domain": exprs(t.domain), "range": exprs(t.range),
        "characteristics": t.characteristics, "inverse_of": exprs(t.inverse_of),
        "types": exprs(t.types), "broader": refs(t.broader), "narrower": refs(t.narrower),
        "replaced_by": refs(t.replaced_by),
        "competency_questions": [cid for cid, _ in t.competency_questions],
    }
    return {k: v for k, v in d.items() if v not in (None, [], False, "")} | {"iri": t.iri, "kind": t.kind}


def ontology_json(onto: Ontology, cqs=None) -> dict:
    m = onto.metadata
    return {
        "title": m.title, "iri": m.iri, "version": m.version_info, "namespace": m.preferred_namespace,
        "prefix": m.preferred_prefix, "description": m.abstract or m.description,
        "license": m.license, "creators": [a.name for a in m.creators],
        "prefixes": dict(onto.prefixes), "counts": onto.stats,
        "terms": [_term_json(t) for k in onto.kinds_present() for t in onto.by_kind(k)],
        "competency_questions": [
            {"id": q.id, "question": q.question, "sparql": q.sparql, "status": q.status}
            for q in (cqs.questions if cqs is not None else [])
        ],
    }


def llms_txt(onto: Ontology, base_url: str | None, downloads: list[dict], cqs=None) -> str:
    """An llms.txt index (https://llmstxt.org): summary + links to Markdown versions."""
    m = onto.metadata
    base = (base_url.rstrip("/") + "/") if base_url else ""
    title = m.title or "Ontology"
    summary = " ".join((m.abstract or m.description or "").split())
    lines = [f"# {title}", ""]
    if summary:
        lines += [f"> {summary[:600]}", ""]
    facts = []
    if m.iri:
        facts.append(f"- Ontology IRI: {m.iri}")
    if m.preferred_namespace:
        facts.append(f"- Namespace: {m.preferred_namespace}" + (f" (prefix `{m.preferred_prefix}:`)" if m.preferred_prefix else ""))
    if m.version_info:
        facts.append(f"- Version: {m.version_info}")
    if m.license:
        facts.append(f"- License: {m.license_label or m.license}")
    from .render.i18n import Translator

    tr = Translator("en")
    counts = ", ".join(tr.kind_count(k, n) for k, n in onto.stats.items() if k != "triples")
    if counts:
        facts.append(f"- Contents: {counts}")
    lines += facts + ["", "Terms are identified by IRI; use the CURIEs and labels below when writing SPARQL or RDF.", ""]
    lines += ["## Documentation", "", f"- [Overview]({base}index.md): metadata and contents"]
    from .model.entities import KIND_LABELS

    for kind in onto.kinds_present():
        lines.append(f"- [{KIND_LABELS[kind][1]}]({base}{KIND_SLUGS[kind]}.md): "
                     f"{tr.kind_count(kind, onto.stats.get(kind, 0))} with definitions and axioms")
    if cqs is not None and cqs.questions:
        lines.append(f"- [Competency questions]({base}competency-questions.md): example questions with SPARQL queries")
    lines += ["", "## Machine-readable", "",
              f"- [ontology.json]({base}ontology.json): all terms as JSON (IRI, label, definition, hierarchy, domain/range)",
              f"- [llms-full.txt]({base}llms-full.txt): the complete documentation as one Markdown file"]
    for d in downloads:
        lines.append(f"- [{d['label']}]({base}{d['file']}): the ontology source ({d['media']})")
    return "\n".join(lines) + "\n"


def llms_full_txt(md_files: list[Path]) -> str:
    parts = []
    for p in md_files:
        parts.append(p.read_text("utf-8").strip())
    return "\n\n---\n\n".join(parts) + "\n"


def write_llm_files(onto: Ontology, out: Path, base_url: str | None, downloads: list[dict],
                    cqs=None) -> list[Path]:
    import json

    md = export_markdown(onto, out, myst=False, cqs=cqs)
    (out / "llms.txt").write_text(llms_txt(onto, base_url, downloads, cqs), "utf-8")
    (out / "llms-full.txt").write_text(llms_full_txt(md), "utf-8")
    (out / "ontology.json").write_text(json.dumps(ontology_json(onto, cqs), indent=1, ensure_ascii=False), "utf-8")
    return md + [out / "llms.txt", out / "llms-full.txt", out / "ontology.json"]
