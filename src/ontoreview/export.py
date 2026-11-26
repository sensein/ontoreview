"""Export the documentation model as Markdown (MkDocs/Docusaurus) or MyST (Sphinx)."""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .model.axioms import expr_text
from .model.entities import KIND_SLUGS, Ontology, Term
from .telemetry import api as _api


@_api("export_markdown")
def export_markdown(onto: Ontology, out: Path, myst: bool = False, cqs=None, *, report=None, changelog=None,
                    downloads: list[dict] | None = None, provenance: dict | None = None,
                    config: Config | None = None) -> list[Path]:
    """Write the documentation as Markdown pages (MyST labels and a toctree when ``myst``).

    Pass what a build produced (``report``, ``changelog``, ``downloads``, ``provenance``) to get every section
    of the website; :func:`ontoreview.build.export_docs` runs that pipeline and calls this."""
    from .render.markdown import render_markdown
    from .render.site import SiteRenderer

    cfg = (config or Config()).model_copy(update={"layout": "multi"})
    site = SiteRenderer(cfg, onto, out, report=report, changelog=changelog, downloads=downloads, cqs=cqs,
                        provenance=provenance)
    return render_markdown(site, out, myst=myst)


# ---------------------------------------------------------------------------- Sphinx project (MyST)
SPHINX_REQUIREMENTS = """sphinx>=7
myst-parser>=2
furo
sphinxcontrib-mermaid
"""

SPHINX_CONF = '''"""Sphinx configuration for this MyST export (written by OntoReview {version}).

Build: see README.md. In short: pip install -r requirements.txt && sphinx-build -b html . _build/html
"""

project = {title!r}
author = {author!r}
release = {release!r}
copyright = {copyright!r}

extensions = ["myst_parser"]
try:                                   # the Visualization page draws the class hierarchy with Mermaid
    import sphinxcontrib.mermaid  # noqa: F401
    extensions.append("sphinxcontrib.mermaid")
except ImportError:
    pass

source_suffix = {{".md": "markdown"}}
root_doc = "index"
exclude_patterns = ["_build", "README.md", "requirements.txt", ".venv", "venv", "**/README.md"]
myst_heading_anchors = 3

try:
    import furo  # noqa: F401
    html_theme = "furo"
except ImportError:
    html_theme = "alabaster"
html_title = project
'''

SPHINX_README = """# {title}: Sphinx (MyST) documentation

This folder is a ready-to-build [Sphinx](https://www.sphinx-doc.org) project. The pages are
[MyST Markdown](https://myst-parser.readthedocs.io), written by OntoReview {version}; they carry the same
content as the OntoReview website (overview, visualization, terms, quality report, provenance, …).

| File | What it is |
|---|---|
| `conf.py` | Sphinx configuration (MyST parser, Mermaid diagrams, Furo theme) |
| `requirements.txt` | The Python packages needed to build |
| `index.md` | Front page: metadata, contents, overview, namespaces, downloads, citation, provenance |
{pages}| `ontology.*`, `CITATION.cff`, `provenance.ttl`, `*.json` | Downloads and machine-readable records, linked from the pages |

## Build

Needs Python 3.9 or newer.

```bash
cd {folder}
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
sphinx-build -b html . _build/html
```

Open `_build/html/index.html` in a browser.

## Live preview while editing

```bash
pip install sphinx-autobuild
sphinx-autobuild . _build/html        # serves http://127.0.0.1:8000 and rebuilds on every change
```

## Other outputs

```bash
sphinx-build -b singlehtml . _build/singlehtml   # one HTML page
sphinx-build -b latex . _build/latex             # LaTeX / PDF (needs a TeX installation)
```

## Publish

- **Read the Docs**: add a `.readthedocs.yaml` that installs `requirements.txt` and builds with Sphinx
  (`sphinx.configuration: conf.py`), then import the repository on readthedocs.org.
- **GitHub Pages**: build with the commands above in a workflow and upload `_build/html` with
  `actions/upload-pages-artifact`.

## Customize

- Theme: change `html_theme` in `conf.py` (for example `"sphinx_rtd_theme"` or `"pydata_sphinx_theme"`) and add
  it to `requirements.txt`.
- Your own pages: add `.md` files and list them in the `toctree` at the end of the contents in `index.md`.
- Regenerate after changing the ontology: `ontoreview export ONTOLOGY -f myst -o {folder}`. Generated pages are
  overwritten; `conf.py`, `requirements.txt` and this README are only written when missing, so your edits stay.
"""


def write_sphinx_project(out: Path, onto: Ontology, pages: list[Path] | None = None) -> list[Path]:
    """``conf.py``, ``requirements.txt`` and ``README.md`` for a MyST export. Existing files are kept, so
    a re-export never overwrites the user's own configuration."""
    import datetime as dt

    from . import __version__

    m = onto.metadata
    title = m.title or "Ontology documentation"
    author = ", ".join(a.name for a in m.creators) or "OntoReview"
    page_rows = "".join(f"| `{p.name}` | {_page_title(p)} |\n"
                        for p in (pages or []) if p.name != "index.md" and p.suffix == ".md")
    files = {
        "conf.py": SPHINX_CONF.format(version=__version__, title=title, author=author,
                                      release=m.version_info or "", copyright=f"{dt.date.today().year}, {author}"),
        "requirements.txt": SPHINX_REQUIREMENTS,
        "README.md": SPHINX_README.format(title=title, version=__version__, pages=page_rows, folder=out.name),
    }
    written = []
    for name, text in files.items():
        p = out / name
        if not p.exists():
            p.write_text(text, "utf-8")
            written.append(p)
    return written


def _page_title(p: Path) -> str:
    for line in p.read_text("utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return p.stem


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


EXTRA_PAGES = {"graph.md": ("Visualization", "the class hierarchy as a diagram and as a list"),
               "changelog.md": ("Changelog", "what changed since the previous version"),
               "quality.md": ("Quality report", "the problems each quality check found, merged and per check")}


def llms_txt(onto: Ontology, base_url: str | None, downloads: list[dict], cqs=None,
             pages: list[str] | None = None) -> str:
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
    for name in pages or []:
        if name in EXTRA_PAGES:
            title, what = EXTRA_PAGES[name]
            lines.append(f"- [{title}]({base}{name}): {what}")
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
                    cqs=None, *, report=None, changelog=None, provenance: dict | None = None,
                    config: Config | None = None) -> list[Path]:
    import json

    md = export_markdown(onto, out, myst=False, cqs=cqs, report=report, changelog=changelog, downloads=downloads,
                         provenance=provenance, config=config)
    (out / "llms.txt").write_text(llms_txt(onto, base_url, downloads, cqs, [p.name for p in md]), "utf-8")
    (out / "llms-full.txt").write_text(llms_full_txt(md), "utf-8")
    (out / "ontology.json").write_text(json.dumps(ontology_json(onto, cqs), indent=1, ensure_ascii=False), "utf-8")
    return md + [out / "llms.txt", out / "llms-full.txt", out / "ontology.json"]
