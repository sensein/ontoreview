"""Document a whole folder of ontologies.

Every ontology file found under the folder gets its own sub-site (or Markdown export) in a
sub-folder of the output that mirrors the source layout::

    ontologies/                     docs/
      core.ttl               ->       core/index.html
      bio/anatomy.owl        ->       bio/anatomy/index.html
      bio/cells.ttl          ->       bio/cells/index.html
                                      index.html        (lists every ontology)
                                      collection.json   (machine-readable manifest)

A ``ontoreview.toml`` inside a sub-folder applies to the ontologies in that sub-folder (and
below); otherwise the configuration given for the whole run is used.
"""

from __future__ import annotations

import html
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config, find_config_file
from .linkml import is_linkml_file

log = logging.getLogger(__name__)

RDF_SUFFIXES = {".ttl", ".owl", ".rdf", ".jsonld", ".nt", ".n3", ".trig", ".nq"}
UNSUPPORTED = {".ofn", ".omn"}  # OWL functional / Manchester syntax: rdflib cannot read them
OUTPUT_MARKERS = ("ontoreview-data.js", "collection.json")
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "site-packages"}
# options that only make sense for one ontology; ignored (with a warning) for a folder
PER_ONTOLOGY = ("previous_version", "competency_questions")


@dataclass
class Entry:
    source: str                 # path relative to the input folder
    slug: str                   # output sub-folder, relative to the output folder
    title: str = ""
    description: str = ""
    version: str = ""
    terms: int = 0
    quality: dict[str, int] = field(default_factory=dict)
    external: list[dict] = field(default_factory=list)
    files: int = 0
    error: str | None = None
    issues: list[dict] = field(default_factory=list)


@dataclass
class CollectionResult:
    output: Path
    entries: list[Entry]
    skipped: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def ok(self) -> list[Entry]:
        return [e for e in self.entries if not e.error]

    @property
    def failed(self) -> list[Entry]:
        return [e for e in self.entries if e.error]


# ------------------------------------------------------------------ discovery
def _is_jsonld(p: Path) -> bool:
    try:
        return '"@context"' in p.read_text("utf-8")[:20000]
    except OSError:
        return False


def find_ontologies(folder: str | Path, exclude: list[Path] | None = None) -> tuple[list[Path], list[Path]]:
    """Ontology files under ``folder`` (recursive) and files skipped as unsupported.

    ``.json`` counts only when it is JSON-LD and ``.yaml``/``.yml`` only when it is a LinkML
    schema, so competency-question files, manifests and configs are ignored.
    """
    root = Path(folder).resolve()
    excluded = [e.resolve() for e in (exclude or [])]
    # earlier OntoReview output (sites carry ontoreview-data.js, folder builds collection.json) holds
    # copies of the ontologies (ontology.ttl, .owl, …); never document those again
    excluded += [m.parent.resolve() for marker in OUTPUT_MARKERS for m in root.rglob(marker)]
    found, skipped = [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if any(p.is_relative_to(e) for e in excluded):
            continue
        suf = p.suffix.lower()
        if suf in RDF_SUFFIXES or (suf == ".json" and _is_jsonld(p)) or is_linkml_file(p):
            found.append(p)
        elif suf in UNSUPPORTED:
            skipped.append(p)
    return found, skipped


def slugs_for(files: list[Path], root: Path) -> dict[Path, str]:
    """Output sub-folder per file: its relative path without the extension (``bio/anatomy``).
    Two files with the same name and different extensions keep the extension (``core-owl``)."""
    root = root.resolve()
    base = {f: f.relative_to(root).with_suffix("").as_posix() for f in files}
    counts: dict[str, int] = {}
    for s in base.values():
        counts[s] = counts.get(s, 0) + 1
    return {f: (s if counts[s] == 1 else f"{s}-{f.suffix.lower().lstrip('.')}") for f, s in base.items()}


def _config_for(file: Path, root: Path, config: Config | str | Path | None) -> Config | str | Path | None:
    """The nearest ``ontoreview.toml`` between the file's folder and the input folder (exclusive)
    wins over the run-wide configuration."""
    d = file.parent.resolve()
    root = root.resolve()
    while d != root and d.is_relative_to(root):
        found = find_config_file(d)
        if found is not None:
            return found
        d = d.parent
    return config


def _drop_per_ontology(overrides: dict[str, Any]) -> dict[str, Any]:
    out = dict(overrides)
    for k in PER_ONTOLOGY:
        if out.get(k):
            log.warning("`%s` applies to a single ontology and is ignored for a folder; put it in an "
                        "ontoreview.toml next to that ontology instead.", k)
            out.pop(k)
    return out


def _excluded_output(folder: Path, out: Path) -> list[Path]:
    # never treat a previous build inside the source folder as input
    return [out] if out.resolve().is_relative_to(folder.resolve()) else []


# ------------------------------------------------------------------ build
def build_collection(folder: str | Path, out: str | Path = "docs", config: Config | str | Path | None = None,
                     *, single_file: bool = False, **overrides: Any) -> CollectionResult:
    """Build one documentation site per ontology in ``folder`` plus a landing page."""
    from .build import build, build_single_file

    t0 = time.perf_counter()
    folder, out = Path(folder).resolve(), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files, skipped = find_ontologies(folder, _excluded_output(folder, out))
    if not files:
        raise ValueError(f"No ontology files found in {folder}")
    overrides = _drop_per_ontology(overrides)
    slugs = slugs_for(files, folder)
    entries = []
    for i, f in enumerate(files, 1):
        e = Entry(source=f.relative_to(folder).as_posix(), slug=slugs[f])
        log.info("[%d/%d] %s", i, len(files), e.source)
        target = out / e.slug
        try:
            cfg = _config_for(f, folder, config)
            if single_file:
                res = build_single_file(f, target / "index.html", config=cfg, **overrides)
            else:
                res = build(f, out=target, config=cfg, **overrides)
            _fill(e, res)
        except Exception as ex:  # noqa: BLE001 - one broken file must not stop the rest
            log.error("%s: %s", e.source, ex)
            e.error = str(ex) or ex.__class__.__name__
        entries.append(e)
    result = CollectionResult(out, entries, [s.relative_to(folder).as_posix() for s in skipped])
    write_collection_index(result, title=_title(folder, config))
    result.seconds = time.perf_counter() - t0
    return result


def _fill(e: Entry, res) -> None:
    md = res.ontology.metadata
    e.title = md.title or Path(e.source).stem
    e.description = " ".join(str(md.abstract or md.description or "").split())
    e.version = str(md.version_info or "")
    e.terms = len(res.ontology.terms)
    e.files = len(res.files)
    if res.report is not None:
        e.quality = res.report.summary
        e.external = [{"tool": x.tool, "problem": x.error, "summary": x.summary} for x in res.report.external]
        e.issues = report_issues(res.report)


def report_issues(report, limit: int = 500) -> list[dict]:
    """A quality report as table rows: built-in checks grouped by rule, plus ROBOT / OOPS! items.

    Each row: severity (error | warning | info), check, rule, affected (a term or "N elements").
    """
    rows: list[dict] = []
    by_rule: dict[str, list] = {}
    for f in report.findings:
        by_rule.setdefault(f.rule, []).append(f)
    for rid, items in by_rule.items():
        first = items[0]
        subjects = sorted({i.subject_label or i.subject for i in items if i.subject_label or i.subject})
        affected = subjects[0] if len(subjects) == 1 else (f"{len(subjects)} elements" if subjects else "ontology")
        rows.append({"severity": first.severity, "check": "OntoReview", "rule": f"{rid} · {first.title}",
                     "affected": affected, "count": len(items)})
    for ext in report.external:
        if ext.error:
            rows.append({"severity": "warning", "check": ext.tool, "rule": "Could not run",
                         "affected": ext.error, "count": 1})
            continue
        for it in ext.items:
            name = it.name if it.name and it.name != it.code else ""
            rule = f"{it.code} · {name}" if name and it.code[:1].upper() == "P" and it.code[1:].isdigit() else (it.code or name)
            n = len(it.affected)
            affected = it.affected[0] if n == 1 else (f"{n} elements" if n else (it.note[:80] or "ontology"))
            rows.append({"severity": it.severity, "check": ext.tool, "rule": rule, "affected": affected,
                         "count": max(n, 1)})
    rank = {"error": 0, "warning": 1, "info": 2}
    rows.sort(key=lambda r: (rank.get(r["severity"], 3), r["check"], r["rule"]))
    return rows[:limit]


def _title(folder: Path, config) -> str:
    if isinstance(config, Config) and config.metadata.title:
        return config.metadata.title
    return f"{folder.name} ontologies"


# ------------------------------------------------------------------ export
def export_collection(folder: str | Path, out: str | Path = "docs-md", config: Config | str | Path | None = None,
                      *, myst: bool = False) -> CollectionResult:
    """Markdown/MyST export of every ontology in ``folder``, one sub-folder each, plus an index."""
    from .build import load, resolve_config
    from .export import export_markdown
    from .model.extract import extract

    t0 = time.perf_counter()
    folder, out = Path(folder).resolve(), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files, skipped = find_ontologies(folder, _excluded_output(folder, out))
    if not files:
        raise ValueError(f"No ontology files found in {folder}")
    slugs = slugs_for(files, folder)
    entries = []
    for i, f in enumerate(files, 1):
        e = Entry(source=f.relative_to(folder).as_posix(), slug=slugs[f])
        log.info("[%d/%d] %s", i, len(files), e.source)
        try:
            cfg = resolve_config(f, _config_for(f, folder, config))
            onto = extract(load(cfg), cfg)
            written = export_markdown(onto, out / e.slug, myst=myst)
            md = onto.metadata
            e.title = md.title or f.stem
            e.description = " ".join(str(md.abstract or md.description or "").split())
            e.version = str(md.version_info or "")
            e.terms, e.files = len(onto.terms), len(written)
        except Exception as ex:  # noqa: BLE001
            log.error("%s: %s", e.source, ex)
            e.error = str(ex) or ex.__class__.__name__
        entries.append(e)
    result = CollectionResult(out, entries, [s.relative_to(folder).as_posix() for s in skipped])
    (out / "index.md").write_text(_index_md(result, _title(folder, config), myst), "utf-8")
    _write_manifest(result, _title(folder, config))
    result.seconds = time.perf_counter() - t0
    return result


def _index_md(result: CollectionResult, title: str, myst: bool) -> str:
    lines = [f"# {title}", "", f"{len(result.ok)} ontologies.", ""]
    if myst:
        lines += ["```{toctree}", ":maxdepth: 1", ""] + [f"{e.slug}/index" for e in result.ok] + ["```", ""]
    lines += ["| Ontology | Terms | Source |", "| --- | ---: | --- |"]
    for e in result.ok:
        lines.append(f"| [{_md_cell(e.title)}]({e.slug}/index.md) | {e.terms} | `{e.source}` |")
    if result.failed:
        lines += ["", "## Not exported", ""] + [f"- `{e.source}`: {_md_cell(e.error or '')}" for e in result.failed]
    if result.skipped:
        lines += ["", "## Skipped (unsupported format)", ""] + [f"- `{s}`" for s in result.skipped]
    return "\n".join(lines) + "\n"


def _md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


# ------------------------------------------------------------------ landing page
def _write_manifest(result: CollectionResult, title: str) -> None:
    data = {"title": title, "generator": f"OntoReview {__version__}",
            "ontologies": [asdict(e) for e in result.entries], "skipped": result.skipped}
    (result.output / "collection.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


def write_collection_index(result: CollectionResult, title: str) -> Path:
    """``index.html`` listing every ontology, plus ``collection.json``."""
    _write_manifest(result, title)
    esc = html.escape
    rows = []
    for e in result.ok:
        q = e.quality
        quality = (f'<span class="n err">{q.get("error", 0)}</span> errors, '
                   f'<span class="n warn">{q.get("warning", 0)}</span> warnings') if q else "—"
        desc = f'<p class="desc">{esc(e.description[:240])}{"…" if len(e.description) > 240 else ""}</p>' \
            if e.description else ""
        ver = f' <span class="ver">{esc(e.version[:40])}</span>' if e.version else ""
        rows.append(
            f'<tr><th scope="row"><a href="{esc(e.slug)}/index.html">{esc(e.title)}</a>{ver}{desc}</th>'
            f'<td class="num">{e.terms}</td><td>{quality}</td><td><code>{esc(e.source)}</code></td></tr>')
    problems = ""
    if result.failed:
        problems += '<h2 id="failed">Could not be built</h2><ul class="plain-list">' + "".join(
            f"<li><code>{esc(e.source)}</code>: {esc(e.error or '')}</li>" for e in result.failed) + "</ul>"
    if result.skipped:
        problems += ('<h2 id="skipped">Skipped</h2><p>OWL functional and Manchester syntax files are not '
                     'supported; convert them to Turtle or RDF/XML first.</p><ul class="plain-list">'
                     + "".join(f"<li><code>{esc(s)}</code></li>" for s in result.skipped) + "</ul>")
    page = INDEX_TEMPLATE.format(
        title=esc(title), count=len(result.ok), rows="\n".join(rows) or
        '<tr><td colspan="4">No ontology could be built.</td></tr>',
        problems=problems, version=esc(__version__))
    target = result.output / "index.html"
    target.write_text(page, "utf-8")
    return target


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="OntoReview {version}">
<title>{title}</title>
<style>
:root {{ --paper:#fff; --ink:#1a1917; --muted:#5d5950; --rule:#e2ded4; --link:#174a8b; --del:#9a2b20; --mod:#8a5a00; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --paper:#1c1b18; --ink:#ece8de; --muted:#a49e91; --rule:#34312a; --link:#9dbbe6; --del:#ef9a8f; --mod:#e2bd6a; color-scheme: dark; }} }}
@media (prefers-contrast: more) {{ :root {{ --muted: var(--ink); --rule: var(--muted); }} a {{ text-decoration: underline; }} }}
*, *::before, *::after {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:17px/1.6 "Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif; }}
main {{ max-width: 64rem; margin: 0 auto; padding: 3rem 1rem 4rem; }}
h1 {{ font-size: clamp(1.9rem, 4vw, 2.6rem); margin: 0 0 .3rem; }}
h2 {{ font-size: 1.25rem; margin: 2.4rem 0 .6rem; }}
.lede {{ color: var(--muted); margin: 0 0 2rem; }}
a {{ color: var(--link); }}
a:focus-visible {{ outline: 2px solid var(--link); outline-offset: 2px; }}
.skip {{ position:absolute; left:-999px; top:8px; background:var(--ink); color:var(--paper); padding:4px 8px; }}
.skip:focus {{ left: 8px; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width:100%; border-collapse:collapse; font-size:.95rem; }}
caption {{ text-align:left; color:var(--muted); font:.8rem/1.4 system-ui,sans-serif; padding-bottom:.4rem; }}
thead th {{ font:600 .72rem/1.9 system-ui,sans-serif; letter-spacing:.07em; text-transform:uppercase; color:var(--muted); text-align:left; border-bottom:1px solid var(--ink); padding:.35rem .8rem .35rem 0; }}
tbody th, td {{ text-align:left; vertical-align:top; padding:.7rem .8rem .7rem 0; border-bottom:1px solid var(--rule); font-weight:400; }}
tbody th a {{ font-weight:600; font-size:1.05rem; }}
.desc {{ margin:.2rem 0 0; color:var(--muted); font-size:.9rem; max-width:60ch; }}
.ver {{ color:var(--muted); font:.78rem system-ui,sans-serif; margin-left:.4rem; }}
.num {{ font-variant-numeric: tabular-nums; }}
.n {{ font-variant-numeric: tabular-nums; font-weight:600; }}
.err {{ color: var(--del); }} .warn {{ color: var(--mod); }}
code {{ font: .82em ui-monospace, Menlo, Consolas, monospace; overflow-wrap:anywhere; }}
.plain-list {{ padding-left: 1.2rem; }}
footer {{ margin-top:3rem; padding-top:1rem; border-top:1px solid var(--rule); color:var(--muted); font-size:.85rem; }}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<main id="main">
<h1>{title}</h1>
<p class="lede">{count} ontologies, each documented separately.</p>
<div class="table-wrap">
<table>
<caption>Ontologies in this collection</caption>
<thead><tr><th scope="col">Ontology</th><th scope="col">Terms</th><th scope="col">Quality</th><th scope="col">Source file</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
{problems}
<footer>Generated with <a href="https://github.com/CAIRNepal/ontoreview">OntoReview</a> {version}. <a href="collection.json">collection.json</a></footer>
</main>
</body>
</html>
"""
