"""Markdown / MyST rendering of the documentation, section for section like the website.

The section list, order, numbering and page split come from :meth:`SiteRenderer.sections` (multi-page
layout), and the wording from the same :class:`Translator`, so a Markdown export says what the website
says. The interactive Visualization (class diagram) is website-only. Each ``sections/<name>.html`` template has a ``_<name>`` method here.

Anchors are explicit, so links work in every target: MyST labels ``(anchor)=`` for Sphinx, and
``<a id="anchor"></a>`` for GitHub, MkDocs and Docusaurus. Links are ``page.md#anchor``.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model.entities import KIND_SLUGS, Ontology, Ref, Term
from ..publish import fix_attribution, term_changes
from ..report.models import tool_anchor
from .site import Section, SiteRenderer, _filesize, _prov_when

STATUS_KEYS = {"passed": "cq_passed", "failed": "cq_failed", "error": "cq_error", "untested": "cq_untested"}


def cell(s: object) -> str:
    """Text that is safe inside a Markdown table cell."""
    return str(s).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _label(s: str) -> str:
    return str(s).replace("[", "\\[").replace("]", "\\]")


def _code(s: object) -> str:
    s = str(s)
    if "`" not in s:
        return f"`{s}`"
    return f"`` {s} ``"


class MarkdownRenderer:
    def __init__(self, site: SiteRenderer, myst: bool = False):
        self.site = site
        self.myst = myst
        self.cfg, self.onto, self.t = site.cfg, site.onto, site.t
        self.meta = self.onto.metadata
        self.sections = site.sections()
        self.toc = site.toc(self.sections)
        self.cq_page = next((self._page(s) for s in self.sections if s.id == "competency-questions"), None)
        self.quality_page = next((self._page(s) for s in self.sections if s.id == "quality"), None)
        self.changes = term_changes(site.provenance)

    # ------------------------------------------------------------------ links and anchors
    @staticmethod
    def _page(s: Section) -> str:
        return s.page[:-5] + ".md" if s.page.endswith(".html") else s.page

    def anchor(self, aid: str) -> str:
        aid = aid.lower()
        return f"({aid})=" if self.myst else f'<a id="{aid}"></a>'

    def href(self, r: Ref) -> str:
        if r.internal and r.anchor and r.kind:
            return f"{KIND_SLUGS[r.kind]}.md#{r.anchor.lower()}"
        return r.iri

    def ref(self, r: Ref) -> str:
        return f"[{_label(r.label)}]({self.href(r)})"

    def refs(self, items) -> str:
        return ", ".join(self.ref(r) for r in items)

    def term_link(self, iri: str) -> str:
        t = self.onto.terms.get(iri)
        return self.ref(t.ref()) if t is not None else _code(iri)

    def expr(self, e) -> str:
        out = []
        for k, v in e:
            if k == "ref":
                out.append(self.ref(v))
            elif k == "kw":
                out.append(f"*{v}*")
            elif k == "lit":
                out.append(_code(v))
            elif k == "url":
                out.append(f"<{v}>")
            else:
                out.append(str(v))
        return "".join(out)

    def exprs(self, items) -> str:
        return "; ".join(self.expr(e) for e in items)

    def link_or_text(self, v: str | None) -> str:
        v = str(v or "")
        return f"<{v}>" if v.startswith(("http://", "https://")) else v

    def agent(self, a) -> str:
        url = a.homepage or a.iri
        s = f"[{_label(a.name)}]({url})" if url else a.name
        if a.orcid and a.orcid != url:
            s += f" ([ORCID]({a.orcid}))"
        if a.affiliation:
            s += f", {a.affiliation}"
        return s

    def agents(self, items) -> str:
        return "; ".join(self.agent(a) for a in items)

    @staticmethod
    def table(rows: list[tuple[str, str]], head: tuple[str, str] = ("", "")) -> list[str]:
        if not rows:
            return []
        out = [f"| {head[0]} | {head[1]} |", "|---|---|"]
        out += [f"| {cell(k)} | {cell(v)} |" for k, v in rows]
        return out + [""]

    @staticmethod
    def grid(head: list[str], rows: list[list[str]], align: str = "") -> list[str]:
        if not rows:
            return []
        sep = ["---:" if str(c) in align else "---" for c in range(len(head))]
        out = ["| " + " | ".join(cell(h) for h in head) + " |", "| " + " | ".join(sep) + " |"]
        out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
        return out + [""]

    # ------------------------------------------------------------------ pages
    def render(self, out: Path) -> list[Path]:
        pages: dict[str, list[Section]] = {"index.md": []}
        for s in self.sections:
            pages.setdefault(self._page(s), []).append(s)
        written = []
        for page, secs in pages.items():
            if page == "index.md":
                lines = self._header()
                lines += self._contents(list(pages)[1:])
                for s in secs:
                    lines += self._section(s, 2)
            else:
                lines = []
                for i, s in enumerate(secs):
                    lines += self._section(s, 1 if i == 0 else 2)
            text = "\n".join(lines).rstrip() + "\n"
            text = re.sub(r"\n{3,}", "\n\n", text)
            p = out / page
            p.write_text(text, "utf-8")
            written.append(p)
        return written

    def _contents(self, pages: list[str]) -> list[str]:
        out = [f"## {self.t('contents')}", ""]
        for e in self.toc:
            first = e.section or e.children[0].section          # a group links to its first member
            target = f"{self._page(first)}#{first.id}"
            count = f" ({e.count})" if e.count is not None else ""
            out.append(f"- [{e.number} {_label(e.title)}]({self._local(target)}){count}")
            for c in e.children:
                cc = f" ({c.count})" if c.count is not None else ""
                out.append(f"  - [{c.number} {_label(c.title)}]({self._local(f'{self._page(c.section)}#{c.id}')}){cc}")
        out.append("")
        if self.myst and pages:
            out += ["```{toctree}", ":hidden:", ""] + [p[:-3] for p in pages] + ["```", ""]
        return out

    @staticmethod
    def _local(target: str) -> str:
        return target[len("index.md"):] if target.startswith("index.md#") else target

    def _header(self) -> list[str]:
        m, t = self.meta, self.t
        kicker = t("spec_kicker") + (f" · {m.status}" if m.status else "") + (
            f" · {t('linkml_source')}" if self.onto.source_kind == "linkml" else "")
        out = [self.anchor("top"), f"# {m.title or 'Ontology documentation'}", "", f"*{kicker}*", ""]
        if m.subtitle:
            out += [f"**{m.subtitle}**", ""]
        lede = m.abstract or m.description
        if lede:
            out += [str(lede).strip(), ""]
        rows = []
        if m.iri:
            rows.append((t("iri"), _code(m.iri)))
        if m.version_info or m.version_iri:
            rows.append((t("version"), " · ".join(x for x in (m.version_info or "", self.link_or_text(m.version_iri))
                                                  if x)))
        if m.prior_version:
            rows.append((t("prior_version"), self.link_or_text(m.prior_version)))
        if m.preferred_namespace:
            rows.append((t("namespace"), _code(m.preferred_namespace)
                         + (f" ({t('prefix')} {_code(m.preferred_prefix + ':')})" if m.preferred_prefix else "")))
        for key, items in (("creators", m.creators), ("contributors", m.contributors), ("publishers", m.publishers)):
            if items:
                rows.append((t(key), self.agents(items)))
        if m.license:
            rows.append((t("license"), f"[{_label(m.license_label or m.license)}]({m.license})"
                         + (f". {m.rights}" if m.rights else "")))
        if m.issued or m.modified or m.created:
            key = "modified" if m.modified else ("issued" if m.issued else "created")
            v = m.modified or m.issued or m.created
            if m.created and (m.modified or m.issued):
                v += f" ({t('created').lower()} {m.created})"
            rows.append((t(key), v))
        if m.doi:
            rows.append((t("doi"), self.link_or_text(m.doi)))
        if m.imports:
            rows.append((t("imports"), self.refs(m.imports)))
        out += self.table(rows)
        if self.site.downloads:
            out += [f"**{t('download')}:** " + " · ".join(
                f"[{_label(d['label'])}]({d['file']}) ({d['file'].rsplit('.', 1)[-1]}, {_filesize(d.get('size') or 0)})"
                for d in self.site.downloads), ""]
        cite = next((s for s in self.sections if s.id == "citation"), None)
        if cite:
            out += [f"[{t('cite')} →]({self._local(self._page(cite) + '#citation')})", ""]
        more = []
        if m.funders:
            more.append((t("funders"), self.agents(m.funders)))
        if m.homepage:
            more.append((t("homepage"), self.link_or_text(m.homepage)))
        if m.repository:
            more.append((t("repository"), self.link_or_text(m.repository)))
        if m.keywords:
            more.append((t("keywords"), ", ".join(m.keywords)))
        for key in ("backward_compatible_with", "incompatible_with", "see_also", "source"):
            vals = getattr(m, key)
            if vals:
                more.append((t(key), "; ".join(self.link_or_text(v) for v in vals)))
        for a in m.other:
            more.append((self.ref(a.prop), self.exprs(a.values)))
        if more:
            out += [f"**{t('more_metadata')}**", ""] + self.table(more)
        return out

    # ------------------------------------------------------------------ sections
    def _section(self, s: Section, h: int) -> list[str]:
        name = s.template.rsplit(".", 1)[0]
        fn = getattr(self, "_" + name.replace("-", "_"), None)
        if fn is None:          # a plugin section (HTML template): not rendered in Markdown
            return []
        head = [self.anchor(s.id), f"{'#' * h} {s.number} {s.title}".replace("  ", " "), ""]
        return head + fn(s, h) + [""]

    def _introduction(self, s: Section, h: int) -> list[str]:
        return [s.context.get("text") or "", ""]

    def _custom(self, s: Section, h: int) -> list[str]:
        return [s.context.get("text") or "", ""]

    def _overview(self, s: Section, h: int) -> list[str]:
        t, st = self.t, s.context["stats"]
        rows = []
        by_id = {x.id: x for x in self.sections}
        for k in st["kinds"]:
            ks = by_id.get(k["section"])
            label = f"[{t.kind_title(k['kind'])}]({self._page(ks)}#{ks.id})" if ks else t.kind_title(k["kind"])
            rows.append([str(k["count"]), label])
        qpage = self.quality_page
        if st["checks_run"] is not None:
            rows.append([str(st["checks_run"]), f"[{t('checks_run')}]({qpage}#quality)" if qpage else t("checks_run")])
        for sc in st["scores"]:
            val = sc["display"] or f"{sc['value']:.2f}"
            note = sc["note"] or (t("score_pass" if sc["passed"] else "score_fail", theta=sc["threshold"])
                                  if sc["threshold"] is not None and sc["passed"] is not None else "")
            label = f"[{sc['tool']}]({qpage}#{sc['anchor']})" if qpage else sc["tool"]
            rows.append([val, label + (f" ({note})" if note else "")])
        out = self.grid(["", ""], rows)
        if s.context.get("index"):
            out += [f"{'#' * (h + 1)} {t('term_index')}", ""]
            for kind in self.onto.kinds_present():
                items = self.onto.by_kind(kind)
                links = ", ".join(self.ref(x.ref()) + ("\\*" if x.external or x.imported else "")
                                  + ("" if not x.deprecated else f" ({t('deprecated')})") for x in items)
                out += [f"**{t.kind_title(kind)}** ({len(items)}): {links}", ""]
            if any(x.external for x in self.onto.terms.values()):
                out += [f"\\* {t('external')}: declared in this ontology, outside its namespace.", ""]
        return out

    def _namespaces(self, s: Section, h: int) -> list[str]:
        t = self.t
        return self.grid([t("prefix"), t("namespace")], [[_code(p), _code(ns)] for p, ns in self.onto.prefixes])

    def _terms(self, s: Section, h: int) -> list[str]:
        out = []
        for x in s.context["terms"]:
            out += self.term(x, h + 1)
        return out

    def term(self, x: Term, h: int) -> list[str]:
        t = self.t
        flags = [x.kind_label]
        if x.deprecated:
            flags.append(f"**{t('deprecated')}**")
        if x.imported:
            flags.append(t("imported"))
        elif x.undeclared:
            flags.append(t("undeclared"))
        elif x.external:
            flags.append(t("external"))
        if x.status:
            flags.append(x.status)
        title = f"~~{x.label}~~" if x.deprecated else x.label
        out = [self.anchor(x.anchor), f"{'#' * h} {title}", "", "*" + " · ".join(flags) + "*", "",
               f"**{t('iri')}:** {_code(x.iri)}", ""]
        if x.definition:
            ai = self.site._ai_terms().get(x.iri)
            out += [x.definition.strip() + (f" *(AI-assisted: {ai})*" if ai else ""), ""]
        for c in x.comments:
            out += [c.strip(), ""]
        if x.replaced_by:
            out += [f"{t('replaced_by')}: {self.refs(x.replaced_by)}", ""]
        rows: list[tuple[str, str]] = []

        def add(key: str, value: str) -> None:
            if value:
                rows.append((t(key) if key else "", value))

        if x.curie:
            rows.append(("CURIE", _code(x.curie)))
        if x.undeclared and x.use_count:
            add("used_on", t("used_on_n", n=x.use_count))
        add("alt_labels", ", ".join(x.alt_labels))
        add("superclasses", self.refs(x.superclasses))
        add("inferred_superclasses", self.refs(x.inferred_superclasses))
        add("restrictions", self.exprs(x.restrictions))
        add("equivalent", self.exprs(x.equivalent))
        add("subclasses", self.refs(x.subclasses))
        add("disjoint", self.refs(x.disjoint))
        add("disjoint_union", self.exprs(x.disjoint_union))
        add("keys", self.exprs(x.keys))
        add("super_properties", self.refs(x.super_properties))
        add("sub_properties", self.refs(x.sub_properties))
        add("domain", self.exprs(x.domain))
        add("range", self.exprs(x.range))
        add("characteristics", ", ".join(x.characteristics))
        add("inverse_of", self.exprs(x.inverse_of))
        add("equivalent_properties", self.refs(x.equivalent_properties))
        add("disjoint_properties", self.refs(x.disjoint_properties))
        add("chains", self.exprs(x.chains))
        add("types", self.exprs(x.types))
        add("facts", "; ".join(f"{self.ref(p)} {self.expr(v)}" for p, v in x.facts))
        add("same_as", self.refs(x.same_as))
        add("top_concepts", self.refs(x.top_concepts))
        add("broader", self.refs(x.broader))
        add("narrower", self.refs(x.narrower))
        add("related", self.refs(x.related))
        add("in_scheme", self.refs(x.in_scheme))
        for label, items in x.mappings.items():
            rows.append((label[:1].upper() + label[1:], self.refs(items)))
        add("instances", self.refs(x.instances))
        if x.used_in:
            groups: dict[str, list[Ref]] = {}
            for u in x.used_in:
                groups.setdefault(u.role, []).append(u.ref)
            add("used_in", "; ".join(f"{role} {self.refs(items)}" for role, items in groups.items()))
        add("examples", "; ".join(_code(e) for e in x.examples))
        for label, notes in x.notes.items():
            rows.append((label, " ".join(n.strip() for n in notes)))
        add("see_also", self.exprs(x.see_also))
        add("source", self.exprs(x.source))
        add("is_defined_by", self.refs(x.is_defined_by))
        for a in x.annotations:
            rows.append((self.ref(a.prop), self.exprs(a.values)))
        if x.iri in self.changes:
            add("changes_applied", "; ".join(
                f"{c['title']}" + (f": {c['option']}" if c["option"] else "") + f" ({c['label']}; "
                + c["decided"].lower() + (f", {_prov_when({'when': c['accepted_at']})}" if c["accepted_at"] else "")
                + ")" + (" **AI-assisted**" if c["ai_assisted"] else "") for c in self.changes[x.iri]))
        if x.competency_questions and self.cq_page:
            add("competency_questions", ", ".join(f"[{cid}]({self.cq_page}#{anchor.lower()})"
                                                  for cid, anchor in x.competency_questions))
        out += self.table(rows)
        for block in x.extra_blocks:            # plugin-provided HTML, as on the website
            out += [block, ""]
        return out

    def _cq(self, s: Section, h: int) -> list[str]:
        t, cqs = self.t, s.context["cqs"]
        sm = cqs.summary
        parts = [f"{sm.get('passed', 0)} {t('cq_passed')}"]
        for k in ("failed", "error", "untested"):
            if sm.get(k):
                parts.append(f"{sm[k]} {t('cq_' + k)}")
        out = [f"{len(cqs.questions)} {t('competency_questions').lower()}: {', '.join(parts)}. Each query is run "
               f"against the ontology{' and its example data' if cqs.example_data else ''} when this document is "
               "generated.", ""]
        for q in cqs.questions:
            out += [self.anchor(q.anchor), f"{'#' * (h + 1)} {q.id}. {q.question}", ""]
            status = t(STATUS_KEYS.get(q.status, q.status))
            if q.status in ("passed", "failed") and q.columns != ["answer"]:
                status += f" · {q.total_rows} {'result' if q.total_rows == 1 else 'results'}"
            rows = [(t("cq_status"), status)]
            if q.term_refs:
                rows.append((t("cq_terms"), self.refs(q.term_refs)))
            if q.answer:
                rows.append((t("cq_answer"), q.answer))
            if q.notes:
                rows.append((t("cq_notes"), q.notes))
            out += self.table(rows)
            if q.sparql:
                out += ["```sparql", q.sparql.strip(), "```", ""]
            if q.error:
                out += [f"> {q.error}", ""]
            if q.rows:
                more = f" ({len(q.rows)} of {q.total_rows})" if q.total_rows > len(q.rows) else ""
                out += [f"**{t('cq_results')}**{more}", ""]
                out += self.grid(list(q.columns), [[_code(v) for v in r] for r in q.rows])
        return out

    def _changelog(self, s: Section, h: int) -> list[str]:
        t, log = self.t, s.context["log"]
        out = [f"{t('compared_with')} {log.old_version or 'the previous version'}: {len(log.added)} "
               f"{t('added').lower()}, {len(log.removed)} {t('removed').lower()}, {len(log.modified)} "
               f"{t('changed').lower()}.", ""]
        if log.empty:
            return out + [t("no_changes"), ""]

        def name(c) -> str:
            if c.anchor and c.kind in KIND_SLUGS:
                return f"[{_label(c.label)}]({KIND_SLUGS[c.kind]}.md#{c.anchor.lower()})"
            return c.label

        rows = [["+", name(c), c.kind.replace("_", " "), _code(c.curie or c.iri)] for c in log.added]
        rows += [["−", c.label, c.kind.replace("_", " "), _code(c.curie or c.iri)] for c in log.removed]
        for c in log.metadata_changes + log.modified:
            detail = "; ".join([f"− {_code(p)} {v}" for p, v in c.removed] + [f"+ {_code(p)} {v}" for p, v in c.added])
            rows.append(["~", name(c), c.kind.replace("_", " "), detail])
        return out + self.grid(["", "Term", "Kind", "Details"], rows)

    def _quality(self, s: Section, h: int) -> list[str]:
        t, r = self.t, s.context["report"]
        sub = "#" * (h + 1)
        ps = r.plain_summary()
        if ps["issues"] == 0:
            line = t("qs_none").replace("{checks}", str(ps["checks"]))
        else:
            parts = [f"**{ps['by'][k]}** {t(lbl)}" for k, lbl in
                     (("error", "qs_errors"), ("warning", "qs_warnings"), ("info", "qs_infos")) if ps["by"][k]]
            line = (t("qs_found").replace("{checks}", str(ps["checks"])).replace("{n}", str(ps["issues"]))
                    + " " + ", ".join(parts) + ".")
            if ps["overlap"]:
                line += " " + t("qs_overlap").replace("{raw}", str(ps["raw"])).replace("{n}", str(ps["overlap"]))
        if ps["consistent"] is True:
            line += " " + t("qs_consistent")
        elif ps["consistent"] is False:
            line += f" **{t('qs_inconsistent')}**"
        if ps["failed"]:
            line += f" {t('qs_failed')}: {', '.join(ps['failed'])}."
        out = [line, ""]
        if ps["top"] and ps["by"]["error"] + ps["by"]["warning"]:
            out += [f"{t('qs_start')}: " + ", ".join(
                f"*{i['title']}*" + (f" ({len(i['elements'])})" if i["elements"] else "") for i in ps["top"]) + ".", ""]

        issues = r.merged_issues()
        if issues:
            out += [self.anchor("quality-issues"), f"{sub} {t('qs_issues')}", "", f"*{t('qs_issues_note')}*", ""]
            rows = []
            for i in issues:
                els = i["elements"]
                aff = ", ".join(self.term_link(e) for e in els[:4]) + (f" +{len(els) - 4}" if len(els) > 4 else "") \
                    if els else f"*{t('qs_whole')}*"
                by = ", ".join(f"[{b}](#{a})" for b, a in zip(i["found_by"], i["anchors"], strict=True))
                rows.append([i["title"], t("sev_" + i["severity"]), aff, by])
            out += self.grid([t("qs_issue"), t("qs_severity"), t("qs_affected"), t("qs_found_by")], rows)

        if r.external:
            out += [f"{sub} {t('qs_checks')}", "", f"*{t('quality_overview')}*", ""]
            rows = []
            for row in r.check_rows():
                name = f"[{row['tool'] or t('quality_builtin')}](#{row['anchor']})"
                if row["error"]:
                    rows.append([name, row["about"], t("not_run"), "", ""])
                elif row["count"] is None:
                    rows.append([name, row["about"], (row["note"] + " " if row["note"] else "") + t("see_report"), "",
                                 ""])
                else:
                    rows.append([name, row["about"], str(row["errors"]), str(row["warnings"]), str(row["infos"])])
            out += self.grid([t("check"), t("qs_what"), t("qs_col_err"), t("qs_col_warn"), t("qs_col_info")], rows, align="234")
            out += [self.anchor("quality-builtin"), f"{sub} {t('quality_builtin')}", ""]
        for rule, findings in r.by_rule():
            out += [f"**{findings[0].severity}** · {rule.title} ({len(findings)}) {_code(rule.id)}", "",
                    f"*{rule.description}*", ""]
            for f in findings:
                link = f" ([§]({self.href(self.onto.terms[f.subject].ref())}))" \
                    if f.anchor and f.subject in self.onto.terms else ""
                out.append(f"- {f.message}{link}")
            out.append("")
        for ext in r.external:
            out += self._external(ext, sub)
        return out

    def _external(self, ext, sub: str) -> list[str]:
        t = self.t
        out = [self.anchor(tool_anchor(ext.tool)), f"{sub} {ext.tool}", ""]
        if ext.url:
            out += [f"<{ext.url}>", ""]
        if ext.scope:
            out += [f"*{ext.scope}*", ""]
        if ext.metrics:
            rows, group = [], None
            for m in ext.metrics:
                if m.get("group") != group:
                    group = m.get("group")
                    rows.append([f"**{group}**", "", ""])
                rows.append([f"{m['title']} {_code(m['metric'])}", f"{m['value']} ({m['status']})", m.get("about", "")])
            out += self.grid(["Metric", "Result", "What it measures"], rows)
        prov = ext.provenance or {}
        if prov.get("releases_in"):
            out += [f"*{'Also checked against' if prov.get('releases') else 'Checked against'}: the releases listed "
                    f"under [Cross-domain interoperability](#{tool_anchor('Cross-domain interoperability')}); "
                    f"recorded once, in {prov['releases_in']}.*", ""]
        if prov.get("releases"):
            recfile = prov.get("record_file") or "iri-checks.json"
            when = (prov.get("checked_at") or "")[:19].replace("T", " ")
            out += [f"*{prov.get('label') or 'Verified against'} (frozen at build time, {when} UTC; full record in "
                    f"[{recfile}]({recfile}))*", ""]
            used = any(rel.get("used_in") for rel in prov["releases"])
            rows = []
            for rel in prov["releases"]:
                name = rel.get("version_iri") or ((rel.get("ontology") or rel.get("ontology_iri") or "")
                                                  + (" " + rel["version"] if rel.get("version") else "")) \
                    or "release not recorded"
                first = (f"{rel['title']}: " if rel.get("title") else "") + _code(name)
                if rel.get("sha256"):
                    first += f" (sha256 {rel['sha256'][:16]}…)"
                row = [first, rel.get("source", "") + (f" {rel['source_url']}" if rel.get("source_url") else ""),
                       (rel.get("retrieved") or "")[:10], str(rel.get("terms", ""))]
                if used:
                    row.append(", ".join(u.replace("cdi", "Cross-domain").replace("si", "Scientific")
                                         for u in rel.get("used_in") or []))
                rows.append(row)
            out += self.grid(["Release", "Source", "Retrieved", "Terms"] + (["Used in"] if used else []), rows)
        if ext.error:
            out += [f"> {ext.error}", ""]
        elif not ext.items:
            out += [ext.note or t("no_findings"), ""]
        else:
            for it in ext.items:
                out += [f"**{it.severity}** · {it.name}" + (f" ({len(it.affected)})" if it.affected else "")
                        + f" {_code(it.code)}", ""]
                if it.description:
                    out += [f"*{it.description}*", ""]
                if it.note:
                    out += [it.note, ""]
                for iri in it.affected[:200]:
                    term = self.onto.terms.get(iri)
                    out.append(f"- {self.ref(term.ref())} {_code(term.curie or iri)}" if term else f"- {_code(iri)}")
                if len(it.affected) > 200:
                    out.append(f"- … {len(it.affected) - 200} more")
                out.append("")
        return out

    def _downloads(self, s: Section, h: int) -> list[str]:
        t = self.t
        rows = [[f"[{_label(d['label'])}]({d['file']})", _code(d["file"]), _code(d["media"]),
                 _filesize(d.get("size") or 0)] for d in self.site.downloads]
        return [t("download_as"), ""] + self.grid([t("format"), t("file"), t("media_type"), t("size")], rows, "3")

    def _citation(self, s: Section, h: int) -> list[str]:
        t = self.t
        return [t("cite_as"), "", f"> {s.context['cite']}", "", "[CITATION.cff](CITATION.cff)", "",
                "```bibtex", s.context["bibtex"].strip(), "```", ""]

    def _provenance(self, s: Section, h: int) -> list[str]:
        t, m, rec = self.t, self.meta, s.context.get("record")
        sub = "#" * (h + 1)
        rows = []
        for key, val in (("creators", self.agents(m.creators)), ("contributors", self.agents(m.contributors)),
                         ("created", m.created), ("issued", m.issued), ("modified", m.modified),
                         ("this_version", self.link_or_text(m.version_iri) if m.version_iri else ""),
                         ("prior_version", self.link_or_text(m.prior_version) if m.prior_version else "")):
            if val:
                rows.append((t(key), val))
        out = self.table(rows)
        if rec:
            out += [self.anchor("provenance-timeline"), f"{sub} {t('prov_timeline')}", ""]
            for e in rec.get("events", []):
                out.append(f"- **{_prov_when(e)}** {e.get('title', '')}" + (f": {e['detail']}" if e.get("detail") else ""))
            out.append("")
            fixes = rec.get("fixes")
            if fixes:
                out += [self.anchor("provenance-fixes"), f"{sub} {t('prov_fixes')}", "",
                        t("prov_fixes_intro", original=(fixes.get("derived_from") or {}).get("name") or "?",
                          n=len(fixes.get("applied", []))), ""]
                rows2 = []
                for a in fixes.get("applied", []):
                    term = self.onto.terms.get(a.get("subject")) if a.get("subject") else None
                    who = fix_attribution(a)
                    change = a.get("title", "") + (" **AI-assisted**" if who["ai_assisted"] else "") + (
                        f": {a['option']}" if a.get("option") else "")
                    rows2.append([self.ref(term.ref()) if term else t("prov_fix_ontology"), change, who["label"],
                                  who["decided"], _prov_when({"when": a.get("accepted_at", "")})])
                out += self.grid([t("prov_fix_term"), t("prov_fix_change"), t("prov_fix_by"), t("prov_fix_decided"),
                                  t("prov_fix_at")], rows2)
            out += [self.anchor("provenance-build"), f"{sub} {t('prov_build')}", ""]
            src = rec.get("source") or {}
            rows3 = []
            if src.get("name"):
                rows3.append((t("prov_source"), src["name"] + (f" ({_filesize(src['size'])})" if src.get("size") else "")))
            if src.get("sha256"):
                rows3.append(("SHA-256", _code(src["sha256"])))
            tool = rec.get("tool") or {}
            rows3.append((t("prov_tool"), f"{tool.get('name', '')} {tool.get('version', '')}".strip()))
            rows3.append((t("prov_started"), _prov_when({"when": rec.get("started", "")})))
            rows3.append((t("prov_finished"), _prov_when({"when": rec.get("generated", "")})
                          + (f" ({rec['seconds']} s)" if rec.get("seconds") is not None else "")))
            if rec.get("checks"):
                rows3.append((t("prov_checks"), ", ".join(rec["checks"])))
            out += self.table(rows3)
        from .. import __version__

        source = "a LinkML schema" if self.onto.source_kind == "linkml" else "the ontology source"
        out += [t("prov_generated", source=source, version=__version__)
                + " Machine-readable: [provenance.ttl](provenance.ttl) (W3C PROV-O).", ""]
        return out


def render_markdown(site: SiteRenderer, out: Path, myst: bool = False) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    return MarkdownRenderer(site, myst).render(out)


__all__ = ["MarkdownRenderer", "render_markdown", "cell", "Ontology"]
