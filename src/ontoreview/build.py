"""High-level build pipeline: load -> extract -> check -> diff -> render -> publish."""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config, load_config
from .cq import CQSet, attach_backlinks, load_many
from .cq import evaluate as evaluate_cqs
from .diff import Changelog, compare
from .loader import LoadedOntology, load_ontology
from .model.entities import Ontology
from .model.extract import extract
from .plugins import PluginManager, load_plugins
from .publish import (
    citation_cff,
    htaccess,
    nginx_conf,
    provenance_graph,
    provenance_record,
    w3id_htaccess,
    write_serializations,
)
from .quality_checks import Finding, Report, Rule, run_checks
from .quality_checks.evaluators import run_evaluations
from .render.site import SiteRenderer, copy_assets, language_links

log = logging.getLogger(__name__)


CQ_RULES = {
    "CQ001": Rule("CQ001", "Competency question not answerable", "warning",
                  "The SPARQL query of a competency question returned no results.", lambda ctx: []),
    "CQ002": Rule("CQ002", "Competency question query error", "error",
                  "The SPARQL query of a competency question could not be executed.", lambda ctx: []),
}


def load_competency_questions(cfg: Config, loaded: LoadedOntology, onto: Ontology,
                              report: Report | None) -> CQSet | None:
    if not cfg.competency_questions:
        return None
    paths = [str(cfg.resolve(p)) for p in cfg.competency_questions]
    cqset = evaluate_cqs(load_many(paths), loaded.full_graph, onto)
    attach_backlinks(cqset, onto)
    if report is not None:
        disabled = set(cfg.checks.disable)
        for q in cqset.questions:
            rid = {"failed": "CQ001", "error": "CQ002"}.get(q.status)
            if rid is None or rid in disabled:
                continue
            rule = CQ_RULES[rid]
            if rule not in report.rules_run:
                report.rules_run.append(rule)
            msg = f"{q.id}: {q.question}" + (f" ({q.error})" if q.error else "")
            report.findings.append(Finding(rid, rule.title, cfg.checks.severity.get(rid, rule.severity), msg))
    return cqset


@dataclass
class BuildResult:
    output: Path
    ontology: Ontology
    report: Report | None
    changelog: Changelog | None
    files: list[Path] = field(default_factory=list)
    seconds: float = 0.0
    competency_questions: CQSet | None = None


def resolve_config(source: str | Path | None = None, config: Config | str | Path | None = None,
                   **overrides: Any) -> Config:
    if isinstance(config, Config):
        cfg = config.model_copy(update={k: v for k, v in overrides.items() if v is not None})
    else:
        cfg = load_config(config, **overrides)
    if source is not None:
        s = str(source)
        if not s.startswith(("http://", "https://")):
            s = str(Path(s).resolve())
        cfg = cfg.model_copy(update={"source": s})
    if not cfg.source:
        raise ValueError("No ontology source given (pass a file/URL or set `source` in ontoreview.toml).")
    return cfg


def _source_path(cfg: Config) -> str:
    s = cfg.source or ""
    if s.startswith(("http://", "https://")):
        return s
    p = cfg.resolve(s)
    return str(p)


def load(cfg: Config) -> LoadedOntology:
    log.info("Parsing ontology %s", _source_path(cfg))
    return load_ontology(
        _source_path(cfg),
        fmt=cfg.format,
        load_imports=cfg.load_imports or cfg.include_imported,
        direct_imports_only=cfg.direct_imports_only,
        import_map={k: str(cfg.resolve(v)) if not v.startswith("http") else v
                    for k, v in cfg.imports.items()},
        catalog=str(cfg.resolve(cfg.catalog)) if cfg.catalog else None,
    )


def build_single_file(source: str | Path | None = None, out_file: str | Path = "ontology.html",
                      config: Config | str | Path | None = None, **overrides: Any) -> BuildResult:
    """Write one self-contained HTML file (CSS, JS, data and serializations inlined)."""
    import tempfile

    t0 = time.perf_counter()
    started = _now()
    cfg = resolve_config(source, config, **overrides)
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    loaded = load(cfg)
    plugins = PluginManager(load_plugins(cfg.plugins))
    onto = extract(loaded, cfg, (cfg.languages or ["en"])[0])
    plugins.decorate_terms(onto)
    log.info("Parsed %d terms; running quality checks", len(onto.terms))
    report = run_checks(onto, loaded.graph, cfg, plugins.rules()) if cfg.sections.quality else None
    if report is not None:
        report.external = run_evaluations(loaded.graph, cfg, loaded.source, onto.namespace)
    cqset = load_competency_questions(cfg, loaded, onto, report)
    prov = provenance_record(onto, _source_path(cfg), __version__, started, report)
    changelog = None
    if cfg.previous_version:
        prev = cfg.previous_version
        try:
            changelog = compare(load_ontology(prev if prev.startswith("http") else str(cfg.resolve(prev))),
                                loaded, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not compute changelog against %s: %s", prev, e)
    log.info("Rendering single HTML file → %s", out_file)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        downloads = write_serializations(loaded.graph, tmpdir, cfg.serialization_basename,
                                         cfg.serializations) if cfg.sections.serializations else []
        renderer = SiteRenderer(cfg.model_copy(update={"layout": "single"}), onto, tmpdir,
                                report=report, changelog=changelog, downloads=downloads,
                                plugin_sections=plugins.sections(onto, cfg), inline=True, cqs=cqset,
                                provenance=prov)
        page = renderer.render()[0]
        shutil.copyfile(page, out_file)
    return BuildResult(out_file, onto, report, changelog, [out_file], time.perf_counter() - t0, cqset)


STANDALONE_FILE = "standalone.html"


def _now():
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc)


def _write_standalone(cfg: Config, onto: Ontology, out_dir: Path, report, changelog, downloads: list[dict],
                      plugins: PluginManager, cqset, prov: dict | None = None) -> Path:
    """The site's primary language as one self-contained page in ``out_dir``, rendered from the
    results this build already has (no second parse or quality run)."""
    import copy
    import tempfile

    dl = copy.deepcopy(downloads)            # the inline renderer rewrites href to data: URIs
    for d in dl:
        d.setdefault("path", str(out_dir / d["file"]))
    with tempfile.TemporaryDirectory() as tmp:
        renderer = SiteRenderer(cfg.model_copy(update={"layout": "single"}), onto, Path(tmp),
                                report=report, changelog=changelog, downloads=dl,
                                plugin_sections=plugins.sections(onto, cfg), inline=True, cqs=cqset,
                                provenance=prov)
        if plugins.template_dirs():
            renderer._plugin_template_dirs = plugins.template_dirs()
            renderer.env = renderer._env()
        target = out_dir / STANDALONE_FILE
        shutil.copyfile(renderer.render()[0], target)
    return target


def build(source: str | Path | None = None, out: str | Path | None = None,
          config: Config | str | Path | None = None, *, live_reload: bool = False,
          **overrides: Any) -> BuildResult:
    """Generate the documentation site.

    >>> import ontoreview
    >>> ontoreview.build("ontology.ttl", out="docs/")          # doctest: +SKIP
    """
    t0 = time.perf_counter()
    started = _now()
    cfg = resolve_config(source, config, **overrides)
    out_dir = Path(out) if out else (cfg.resolve(cfg.output) or Path("docs"))
    out_dir.mkdir(parents=True, exist_ok=True)

    loaded = load(cfg)
    plugins = PluginManager(load_plugins(cfg.plugins))

    languages = cfg.languages or ["en"]
    primary = languages[0]
    onto = extract(loaded, cfg, primary)
    log.info("Parsed %d terms; running quality checks", len(onto.terms))
    report = run_checks(onto, loaded.graph, cfg, plugins.rules()) if cfg.sections.quality else None
    if report is not None:
        report.external = run_evaluations(loaded.graph, cfg, loaded.source, onto.namespace)
    cqset = load_competency_questions(cfg, loaded, onto, report)
    prov = provenance_record(onto, _source_path(cfg), __version__, started, report)

    changelog = None
    if cfg.previous_version:
        prev = cfg.previous_version
        prev_src = prev if prev.startswith(("http://", "https://")) else str(cfg.resolve(prev))
        try:
            changelog = compare(load_ontology(prev_src), loaded, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not compute changelog against %s: %s", prev, e)

    files: list[Path] = []
    log.info("Rendering website → %s", out_dir)
    downloads = write_serializations(loaded.graph, out_dir, cfg.serialization_basename,
                                     cfg.serializations) if cfg.sections.serializations else []
    files += [out_dir / d["file"] for d in downloads]

    theme_dir = cfg.resolve(cfg.theme) if cfg.theme else None
    copy_assets(out_dir, theme_dir)

    llm_files: list[dict] = []
    if cfg.llm:
        from .export import write_llm_files

        written_llm = write_llm_files(onto, out_dir, cfg.base_url, downloads, cqset)
        files += written_llm
        purposes = {
            "llms.txt": "Index for language models (llmstxt.org): summary and links to the Markdown pages",
            "llms-full.txt": "The complete documentation as a single Markdown file",
            "ontology.json": "Every term as JSON: IRI, CURIE, label, definition, hierarchy, domain and range",
        }
        for p in written_llm:
            llm_files.append({"file": p.name, "size": p.stat().st_size,
                              "purpose": purposes.get(p.name, "Markdown version of a documentation page"),
                              "kind": "index" if p.name in purposes else "page"})

    for lang in languages:
        lang_onto = onto if lang == primary else extract(loaded, cfg, lang)
        if lang_onto is not onto and cqset is not None:
            attach_backlinks(cqset, lang_onto)
        plugins.decorate_terms(lang_onto)
        at_root = lang == primary
        target = out_dir if at_root else out_dir / lang
        renderer = SiteRenderer(
            cfg, lang_onto, target,
            report=report, changelog=changelog, downloads=downloads,
            languages=language_links(languages, lang, at_root),
            asset_prefix="assets/" if at_root else "../assets/",
            root_prefix="" if at_root else "../",
            plugin_sections=plugins.sections(lang_onto, cfg),
            live_reload=live_reload,
            cqs=cqset,
            llm_files=llm_files,
            provenance=prov,
        )
        if plugins.template_dirs():
            renderer._plugin_template_dirs = plugins.template_dirs()
            renderer.env = renderer._env()
        files += renderer.render()

    if cfg.standalone:
        files.append(_write_standalone(cfg, onto, out_dir, report, changelog, downloads, plugins, cqset, prov))

    # Publishing extras
    if cfg.conneg and downloads:
        (out_dir / ".htaccess").write_text(htaccess(downloads, cfg.rewrite_base), "utf-8")
        (out_dir / "nginx.conf.example").write_text(nginx_conf(downloads, cfg.rewrite_base), "utf-8")
        if cfg.base_url:
            (out_dir / "w3id.htaccess").write_text(w3id_htaccess(cfg.base_url, downloads), "utf-8")
    if cfg.sections.citation:
        (out_dir / "CITATION.cff").write_text(citation_cff(onto.metadata, cfg.base_url), "utf-8")
    write_records(out_dir, onto, report, prov, Path(cfg.source or "").name, provenance=cfg.sections.provenance)
    if report is not None:
        (out_dir / "quality.json").write_text(report.to_json(), "utf-8")
    if changelog is not None:
        (out_dir / "changelog.json").write_text(changelog.to_json(), "utf-8")
        (out_dir / "CHANGELOG.md").write_text(changelog.to_markdown(), "utf-8")
    (out_dir / ".nojekyll").write_text("", "utf-8")
    (out_dir / ".ontoreview-build").write_text(str(time.time()), "utf-8")

    plugins.postprocess(out_dir, onto, cfg)
    if cqset is not None:
        import json as _json

        (out_dir / "competency-questions.json").write_text(_json.dumps(
            {"summary": cqset.summary, "questions": [
                {k: getattr(q, k) for k in ("id", "question", "sparql", "answer", "status", "error",
                                            "total_rows", "columns", "rows")} for q in cqset.questions]},
            indent=2, ensure_ascii=False), "utf-8")
    return BuildResult(out_dir, onto, report, changelog, files, time.perf_counter() - t0, cqset)


def write_records(out_dir: Path, onto: Ontology, report: Report | None, prov: dict | None, source_name: str,
                  provenance: bool = True) -> list[Path]:
    """The frozen records of a run, next to its docs or report: ``iri-checks.json``, ``cdi.json``,
    ``si.json`` (each with the releases it was checked against) and ``provenance.ttl`` (PROV-O,
    the same times and releases). Used by docs builds and by quality / interoperability runs, so
    any single run is self-contained."""
    from .report.models import TOOLS

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    externals = report.external if report else []

    def rec(tool: str):
        return next((x.provenance for x in externals if x.tool == TOOLS[tool].name and x.provenance), None)

    iri_prov, cdi_rec, si_rec = rec("iri"), rec("cdi"), rec("si")
    for name, record in (("iri-checks.json", iri_prov), ("cdi.json", cdi_rec), ("si.json", si_rec)):
        if record:      # frozen at run time: what each check verified against, and its results
            path = out_dir / name
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), "utf-8")
            written.append(path)
    if provenance:
        pg = provenance_graph(onto, source_name, __version__, prov)
        from rdflib import URIRef

        from .report.iri import add_iri_provenance
        act = URIRef("urn:ontoreview:build")
        if iri_prov:
            add_iri_provenance(pg, iri_prov, act)
        # each reference release once (tag_releases), with the checks that used it
        what = {("cdi",): "the cross-domain interoperability score", ("si",): "the scientific interoperability degree",
                ("cdi", "si"): "the cross-domain interoperability score and the scientific interoperability degree"}
        for rels in ((cdi_rec or {}).get("releases") or [], (si_rec or {}).get("releases") or []):
            for used in what:
                group = [r for r in rels if tuple(r.get("used_in") or ()) == used]
                if group:
                    add_iri_provenance(pg, {"releases": group}, act, purpose=f"Reference release used for {what[used]} "
                                                                             "({terms} correspondence(s), via {source}).")
        path = out_dir / "provenance.ttl"
        pg.serialize(destination=str(path), format="turtle")
        written.append(path)
    return written


def check_records(out_dir: Path, source: str | Path, onto: Ontology, report: Report, started) -> list[Path]:
    """Records and PROV-O for a quality or interoperability run (no docs): see :func:`write_records`."""
    prov = provenance_record(onto, source, __version__, started, report)
    return write_records(out_dir, onto, report, prov, Path(str(source)).name)


def check(source: str | Path | None = None, config: Config | str | Path | None = None,
          **overrides: Any) -> tuple[Ontology, Report]:
    cfg = resolve_config(source, config, **overrides)
    loaded = load(cfg)
    plugins = PluginManager(load_plugins(cfg.plugins))
    onto = extract(loaded, cfg)
    report = run_checks(onto, loaded.graph, cfg, plugins.rules())
    report.external = run_evaluations(loaded.graph, cfg, loaded.source, onto.namespace)
    load_competency_questions(cfg, loaded, onto, report)
    return onto, report
