"""Render the documentation model into a static, self-contained website."""

from __future__ import annotations

import base64
import html
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup

from .. import __version__
from ..config import Config
from ..diff import Changelog
from ..model.entities import KIND_BADGES, KIND_SLUGS, Ontology, Ref
from ..publish import bibtex, citation_text, fix_attribution, term_changes
from ..report.models import Report, tool_anchor
from .data import graph_data, jsonld, search_index
from .i18n import LANGUAGE_NAMES, Translator

THEME_DIR = Path(__file__).resolve().parent.parent / "themes" / "default"

_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": True}).enable("table")

LARGE_INDEX = 120  # kinds with more terms get a searchable list instead of columns


def markdown(text: str | None, inline: bool = False) -> Markup:
    if not text:
        return Markup("")
    text = str(text).strip()
    if inline:
        return Markup(_md.renderInline(text))
    return Markup(_md.render(text))


def _prov_when(e: dict) -> str:
    """A provenance timestamp for reading: ``2026-11-21 16:57:03 UTC``, or the date alone."""
    import datetime as dt

    try:
        d = dt.datetime.fromisoformat(str(e["when"]).replace("Z", "+00:00"))
    except ValueError:
        return str(e["when"])
    return d.strftime("%Y-%m-%d") if e.get("date_only") else d.strftime("%Y-%m-%d %H:%M:%S UTC")


def codeticks(text: str) -> Markup:
    """Escape text, then turn `backticks` into <code> (used for check messages)."""
    esc = html.escape(text)
    return Markup(re.sub(r"`([^`]+)`", r"<code>\1</code>", esc))


@dataclass
class Section:
    id: str
    title: str
    template: str
    page: str = "index.html"
    context: dict[str, Any] = field(default_factory=dict)
    nav: bool = True
    level: int = 0
    number: str = ""
    group: str | None = None  # e.g. "reference" for the per-kind term sections
    group_title: str | None = None
    group_first: bool = False
    count: int | None = None


@dataclass
class TocEntry:
    section: Section | None
    title: str
    number: str
    id: str
    page: str
    count: int | None = None
    children: list[TocEntry] = field(default_factory=list)


@dataclass
class LanguageLink:
    code: str
    name: str
    href: str
    current: bool


class SiteRenderer:
    def __init__(
        self,
        config: Config,
        ontology: Ontology,
        out_dir: Path,
        *,
        report: Report | None = None,
        changelog: Changelog | None = None,
        downloads: list[dict] | None = None,
        languages: list[LanguageLink] | None = None,
        asset_prefix: str = "assets/",
        root_prefix: str = "",
        plugin_sections: list[Section] | None = None,
        live_reload: bool = False,
        inline: bool = False,
        cqs=None,
        llm_files: list[dict] | None = None,
        provenance: dict | None = None,
    ):
        self.provenance = provenance
        self.cfg = config
        self.onto = ontology
        self.out = out_dir
        self.report = report
        self.changelog = changelog
        self.downloads = [dict(d) for d in (downloads or [])]
        self.languages = languages or []
        self.asset_prefix = asset_prefix
        self.root_prefix = root_prefix
        self.plugin_sections = plugin_sections or []
        self.live_reload = live_reload
        self.inline = inline
        self.cqs = cqs
        self.llm_files = llm_files or []
        self.t = Translator(ontology.language)
        self.multi = config.layout == "multi" and not inline
        for d in self.downloads:
            d.setdefault("href", f"{root_prefix}{d['file']}")
        self.env = self._env()

    # ------------------------------------------------------------------ jinja
    def _env(self) -> Environment:
        loaders = []
        if self.cfg.theme:
            theme = self.cfg.resolve(self.cfg.theme)
            if theme and (theme / "templates").is_dir():
                loaders.append(FileSystemLoader(str(theme / "templates")))
            elif theme and theme.is_dir():
                loaders.append(FileSystemLoader(str(theme)))
        for extra in getattr(self, "_plugin_template_dirs", []):
            loaders.append(FileSystemLoader(str(extra)))
        loaders.append(PackageLoader("ontoreview", "themes/default/templates"))
        env = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["md"] = markdown
        env.filters["mdinline"] = lambda s: markdown(s, inline=True)
        env.filters["codeticks"] = codeticks
        env.filters["slug"] = lambda k: KIND_SLUGS.get(k, k)
        env.filters["filesize"] = _filesize
        env.filters["badge"] = lambda k: KIND_BADGES.get(k, k)
        env.filters["tool_anchor"] = tool_anchor
        env.filters["prov_when"] = _prov_when
        env.filters["fix_who"] = fix_attribution
        env.globals.update(
            t=self.t,
            href=self.href,
            page_href=self.page_href,
            graph_href=self.graph_href,
            cfg=self.cfg,
            onto=self.onto,
            meta=self.onto.metadata,
            version=__version__,
            assets=self.asset_prefix,
            root=self.root_prefix,
            multi=self.multi,
            languages=self.languages,
            live_reload=self.live_reload,
            large_index=LARGE_INDEX,
            ui=self.cfg.ui,
            build_id=format(int(time.time()), "x"),
            ai_terms=self._ai_terms(),
            term_changes=term_changes(self.provenance),
        )
        return env

    def _ai_terms(self) -> dict[str, str]:
        """Terms whose text came from an accepted AI draft: IRI → "model, accepted at" (shown as AI-assisted)."""
        fixes = (getattr(self, "provenance", None) or {}).get("fixes") or {}
        out = {}
        for a in fixes.get("applied", []):
            if a.get("ai_assisted") and a.get("subject"):
                mb = a.get("made_by") or {}
                out[a["subject"]] = (f"Drafted by {mb.get('provider') or mb.get('source')} · {mb.get('model')}"
                                     + (", edited by the author" if a.get("edited") else "")
                                     + f"; accepted {str(a.get('accepted_at', ''))[:10]}")
        return out

    def href(self, ref: Ref) -> str:
        if ref.internal and ref.anchor:
            if self.multi and ref.kind:
                return f"{KIND_SLUGS[ref.kind]}.html#{ref.anchor}"
            return f"#{ref.anchor}"
        return ref.iri

    def page_href(self, section, current_page: str) -> str:
        if section.page == current_page:
            return f"#{section.id}"
        return f"{section.page}#{section.id}"

    def graph_href(self) -> str:
        return "graph.html" if self.multi else "#graph"

    # ------------------------------------------------------------------ sections
    def has_graph(self) -> bool:
        return self.cfg.sections.graph and any(
            x.kind in ("class", "concept") for x in self.onto.terms.values())

    def sections(self) -> list[Section]:
        cfg, t, onto = self.cfg, self.t, self.onto
        st = cfg.sections
        multi = self.multi
        out: list[Section] = []

        def page(name: str) -> str:
            return f"{name}.html" if multi else "index.html"

        intro = self._introduction_text() if st.introduction else None
        if intro:
            out.append(Section("introduction", t("introduction"), "introduction.html",
                               context={"intro": markdown(intro), "text": intro}))
        for cs in cfg.custom_sections:
            if cs.position == "before-terms":
                out.append(self._custom(cs))
        out += [s for s in self.plugin_sections if s.context.get("position", "before-terms") == "before-terms"]
        if st.competency_questions and self.cqs is not None and self.cqs.questions:
            out.append(Section("competency-questions", t("competency_questions"), "cq.html",
                               page=page("competency-questions"), count=len(self.cqs.questions),
                               context={"cqs": self.cqs}))
        if st.overview and onto.terms:
            out.append(Section("overview", t("overview"), "overview.html",
                               context={"stats": self._stats(),
                                        "index": cfg.ui.term_index in ("section", "both")}))
        if self.has_graph():
            out.append(Section("graph", t("graph"), "graph.html", page=page("graph")))
        if st.namespaces and onto.prefixes:      # before the terms: readers meet the prefixes first
            out.append(Section("namespaces", t("namespaces"), "namespaces.html"))
        if st.terms:
            kinds = onto.kinds_present()
            for i, kind in enumerate(kinds):
                terms = onto.by_kind(kind)
                out.append(Section(KIND_SLUGS[kind], t.kind_title(kind), "terms.html",
                                   page=page(KIND_SLUGS[kind]), count=len(terms),
                                   context={"kind": kind, "terms": terms},
                                   group="reference", group_title=t("terms"), group_first=i == 0))
        for cs in cfg.custom_sections:
            if cs.position == "after-terms":
                out.append(self._custom(cs))
        out += [s for s in self.plugin_sections if s.context.get("position") == "after-terms"]
        if st.changelog and self.changelog is not None:
            out.append(Section("changelog", t("changelog"), "changelog.html", page=page("changelog"),
                               context={"log": self.changelog}))
        if st.quality and self.report is not None:
            out.append(Section("quality", t("quality"), "quality.html", page=page("quality"),
                               context={"report": self.report}))
        if st.serializations and self.downloads:
            out.append(Section("downloads", t("serializations"), "downloads.html"))
        if self.llm_files and not self.inline:
            out.append(Section("llm", t("for_llms"), "llm.html", context={"files": self.llm_files}))
        if st.citation:
            out.append(Section("citation", t("citation"), "citation.html",
                               context={"cite": citation_text(onto.metadata, cfg.base_url),
                                        "bibtex": bibtex(onto.metadata, cfg.base_url)}))
        if st.provenance:
            out.append(Section("provenance", t("provenance"), "provenance.html",
                               context={"record": self.provenance}))
        out = self._order(out, cfg.ui.section_order)
        self._number(out)
        return out

    @staticmethod
    def _order(sections: list[Section], order: list[str]) -> list[Section]:
        if not order:
            return sections
        # 'terms' (the group's title) and 'reference' (its id) both name the term sections
        rank = {("reference" if sid == "terms" else sid): i for i, sid in enumerate(order)}

        def key(item: tuple[int, Section]) -> tuple[int, int]:
            i, s = item
            sid = s.group or s.id
            return (rank.get(sid, len(rank)), i)

        ordered = [s for _, s in sorted(enumerate(sections), key=key)]
        seen: set[str] = set()
        for s in ordered:  # recompute which term section opens the group
            if s.group:
                s.group_first = s.group not in seen
                seen.add(s.group)
        return ordered

    @staticmethod
    def _number(sections: list[Section]) -> None:
        n = 0
        sub = 0
        group = None
        for s in sections:
            if not s.nav:
                continue
            if s.group:
                if s.group != group:
                    n += 1
                    sub = 0
                    group = s.group
                sub += 1
                s.number = f"{n}.{sub}"
                s.context.setdefault("group_number", str(n))
            else:
                group = None
                n += 1
                s.number = str(n)

    def toc(self, sections: list[Section]) -> list[TocEntry]:
        entries: list[TocEntry] = []
        for s in sections:
            if not s.nav:
                continue
            if s.group:
                if not entries or entries[-1].id != s.group:
                    entries.append(TocEntry(None, s.group_title or s.group, s.number.split(".")[0],
                                            s.group, s.page,
                                            count=None))
                parent = entries[-1]
                parent.children.append(TocEntry(s, s.title, s.number, s.id, s.page, s.count))
                parent.count = (parent.count or 0) + (s.count or 0)
            else:
                entries.append(TocEntry(s, s.title, s.number, s.id, s.page, s.count))
        return entries

    def _stats(self) -> dict:
        """Overview tiles: terms per kind, quality checks run, and interoperability scores."""
        onto, r = self.onto, self.report
        kinds = [{"kind": k, "count": len(onto.by_kind(k)), "section": KIND_SLUGS[k]}
                 for k in onto.kinds_present()]
        show_quality = r is not None and self.cfg.sections.quality
        return {"kinds": kinds,
                "checks_run": r.checks_run() if show_quality else None,
                "scores": r.scores() if show_quality else []}

    def _custom(self, cs) -> Section:
        text = cs.content or ""
        if cs.file:
            p = self.cfg.resolve(cs.file)
            if p and p.is_file():
                text = p.read_text("utf-8")
        sid = cs.id or re.sub(r"[^a-z0-9]+", "-", cs.title.lower()).strip("-")
        return Section(sid, cs.title, "custom.html", context={"body": markdown(text), "text": text})

    def _introduction_text(self) -> str | None:
        """Only when there is substantive text: a configured intro, or a description that is not
        already used as the lede of the document header. Markdown source (the Markdown export uses it as is)."""
        cfg, m = self.cfg, self.onto.metadata
        if cfg.introduction:
            p = cfg.resolve(cfg.introduction)
            return p.read_text("utf-8") if p and p.is_file() else cfg.introduction
        if m.abstract and m.description and m.description.strip() != m.abstract.strip():
            return m.description
        return None

    # ------------------------------------------------------------------ write
    def render(self) -> list[Path]:
        self.out.mkdir(parents=True, exist_ok=True)
        sections = self.sections()
        toc = self.toc(sections)
        pages = []
        for s in sections:
            if s.page not in pages:
                pages.append(s.page)
        if "index.html" not in pages:
            pages.insert(0, "index.html")
        written = []
        data = {
            "search": search_index(self.onto, self.href),
            "graph": (graph_data(self.onto, self.href, individuals=self.cfg.ui.graph_individuals)
                      if self.has_graph() else None),
            "i18n": {k: self.t(k) for k in ("no_results", "copied", "copy_iri", "search_placeholder",
                                            "graph_showing_top", "graph_showing_focus",
                                            "graph_showing_all", "dark", "light", "results_count",
                                            "filter_count")},
            "graphHref": self.graph_href(),
            "ui": {"layout": self.cfg.ui.graph_layout, "notation": self.cfg.ui.graph_notation, "props": self.cfg.ui.graph_property_edges,
                   "topLevels": self.cfg.ui.graph_top_levels},
        }
        data_js = "window.ONTOREVIEW=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
        data_js = data_js.replace("<", "\\u003c")
        inline_assets = None
        if self.inline:
            inline_assets = _inline_assets(data_js, self.cfg)
            for d in self.downloads:
                path = Path(d["path"]) if d.get("path") else self.out / d["file"]
                if path.is_file() and path.stat().st_size < 5_000_000:
                    b64 = base64.b64encode(path.read_bytes()).decode()
                    d["href"] = f"data:{d['media']};base64,{b64}"
        else:
            (self.out / "ontoreview-data.js").write_text(data_js, "utf-8")

        ld = jsonld(self.onto, self.cfg.base_url)
        for page in pages:
            page_sections = [s for s in sections if s.page == page]
            tmpl = self.env.get_template("page.html")
            html_text = tmpl.render(
                page=page,
                sections=sections,
                toc=toc,
                page_sections=page_sections,
                report=self.report,
                downloads=self.downloads,
                jsonld=Markup(ld) if page == "index.html" else None,
                custom_css=self._read_opt(self.cfg.custom_css),
                head_html=Markup(self._read_opt(self.cfg.head_html) or ""),
                page_title=self._page_title(page, page_sections),
                inline=inline_assets,
                has_graph=self.has_graph(),
                cite_section=next((s for s in sections if s.id == "citation"), None),
            cq_page=next((s.page for s in sections if s.id == "competency-questions"), None),
            llm=self.cfg.llm and not self.inline,
            )
            path = self.out / page
            path.write_text(html_text, "utf-8")
            written.append(path)
        return written

    def _page_title(self, page: str, page_sections: list[Section]) -> str:
        title = self.onto.metadata.title or "Ontology documentation"
        if page == "index.html" or not page_sections:
            return title
        return f"{page_sections[0].title} · {title}"

    def _read_opt(self, path: str | None) -> str | None:
        if not path:
            return None
        p = self.cfg.resolve(path)
        if p and p.is_file():
            return p.read_text("utf-8")
        return None


def _inline_assets(data_js: str, cfg: Config) -> dict[str, Markup]:
    static = THEME_DIR / "static"
    theme = cfg.resolve(cfg.theme) if cfg.theme else None

    def read(rel: str) -> str:
        if theme is not None and (theme / "static" / rel).is_file():
            return (theme / "static" / rel).read_text("utf-8")
        return (static / rel).read_text("utf-8")

    def script(text: str) -> Markup:
        return Markup(text.replace("</script", "<\\/script"))

    return {
        "css": Markup(read("ontoreview.css")),
        "data": script(data_js),
        "minisearch": script(read("vendor/minisearch.min.js")),
        "cytoscape": script(read("vendor/cytoscape.min.js")),
        "dagre": script(read("vendor/dagre.min.js")),
        "cydagre": script(read("vendor/cytoscape-dagre.js")),
        "js": script(read("ontoreview.js")),
    }


def copy_assets(out_dir: Path, theme: Path | None = None) -> None:
    dest = out_dir / "assets"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(THEME_DIR / "static", dest)
    if theme is not None and (theme / "static").is_dir():
        shutil.copytree(theme / "static", dest, dirs_exist_ok=True)


def language_links(langs: list[str], current: str, at_root: bool) -> list[LanguageLink]:
    if len(langs) < 2:
        return []
    primary = langs[0]
    links = []
    for code in langs:
        if at_root:
            href = "index.html" if code == primary else f"{code}/index.html"
        else:
            href = "../index.html" if code == primary else (
                "index.html" if code == current else f"../{code}/index.html")
        links.append(LanguageLink(code, LANGUAGE_NAMES.get(code, code), href, code == current))
    return links


def _filesize(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
