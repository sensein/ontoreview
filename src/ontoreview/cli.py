"""Command-line interface: ``ontoreview build | serve | check | diff | export | init``."""

from __future__ import annotations

import functools
import http.server
import logging
import re
import threading
import time
import webbrowser
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import __version__

app = typer.Typer(
    name="ontoreview",
    help="Beautiful documentation for OWL, RDFS, SKOS and LinkML models.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()
err = Console(stderr=True)

SEV_STYLE = {"error": "bold red", "warning": "yellow", "info": "cyan"}


class Layout(str, Enum):
    single = "single"
    multi = "multi"


class CheckFormat(str, Enum):
    console = "console"
    json = "json"
    html = "html"


class FailOn(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"
    never = "never"


class DiffFormat(str, Enum):
    console = "console"
    markdown = "markdown"
    json = "json"


class ExportFormat(str, Enum):
    markdown = "markdown"
    myst = "myst"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=err, show_path=False, show_time=False)],
    )


def _overrides(**kw) -> dict:
    out = {k: v for k, v in kw.items() if v is not None}
    if "languages" in out:
        out["languages"] = [x.strip() for x in out["languages"].split(",") if x.strip()]
    return out


def _eval_overrides(oops: bool | None, robot: str | None) -> dict | None:
    ev = {}
    if oops is not None:
        ev["oops"] = oops
    if robot is not None:
        if robot not in ("auto", "on", "off") and (robot.endswith(".jar") or "/" in robot):
            ev["robot"], ev["robot_path"] = "on", robot
        else:
            ev["robot"] = robot
    return ev or None


def _print_external(report) -> None:
    for ext in report.external:
        console.print(f"\n[bold]{ext.tool}[/] [dim]{ext.url}[/]")
        if ext.error:
            console.print(f"   [red]{_rich_escape(ext.error)}[/]")
            continue
        if not ext.items:
            console.print("   [green]No issues reported.[/]")
        for it in ext.items:
            console.print(f"   [{SEV_STYLE[it.severity]}]{it.severity.upper():8}[/] {it.code} {_rich_escape(it.name)} "
                          f"[dim]({len(it.affected) or ''})[/]")


def _version_cb(value: bool) -> None:
    if value:
        console.print(f"ontoreview {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", callback=_version_cb, is_eager=True,
                                 help="Show version and exit."),
) -> None:
    pass


SourceArg = typer.Argument(None, help="Ontology file or URL (RDF in any syntax, or a LinkML YAML schema).")
ConfigOpt = typer.Option(None, "--config", "-c", help="Path to ontoreview.toml (auto-discovered by default).")


@app.command()
def build(
    source: str | None = SourceArg,
    output: Path | None = typer.Option(None, "--output", "-o", help="Output directory [default: docs]."),
    config: Path | None = ConfigOpt,
    layout: Layout | None = typer.Option(None, help="single page or one page per section."),
    lang: str | None = typer.Option(None, "--lang", "-l", help="Comma-separated languages, e.g. en,es,pt."),
    previous: str | None = typer.Option(None, "--previous", "-p", help="Previous version (file/URL) for the changelog."),
    base_url: str | None = typer.Option(None, help="Public URL where the docs will be published."),
    theme: Path | None = typer.Option(None, help="Directory with template/static overrides."),
    reason: bool | None = typer.Option(None, "--reason/--no-reason", help="Show inferred superclasses (needs owlrl)."),
    imports: bool | None = typer.Option(None, "--imports/--no-imports", help="Load owl:imports."),
    include_imported: bool | None = typer.Option(None, help="Also document imported terms."),
    individuals: bool | None = typer.Option(None, "--individuals/--no-individuals"),
    cq: list[str] | None = typer.Option(None, "--cq", help="Competency questions file (.yaml/.json/.csv/.tsv/.xlsx); repeatable."),
    oops: bool | None = typer.Option(None, "--oops/--no-oops", help="Add the OOPS! evaluation (uploads the ontology to oops.linkeddata.es)."),
    robot: str | None = typer.Option(None, "--robot", help="ROBOT report: auto (if installed), on, off, or path to robot.jar."),
    single_file: bool = typer.Option(False, "--single-file", help="Write one self-contained HTML file."),
    open_browser: bool = typer.Option(False, "--open", help="Open the result in a browser."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate the documentation website."""
    _setup_logging(verbose)
    from .build import build as do_build
    from .build import build_single_file

    ov = _overrides(layout=layout.value if layout else None, languages=lang, previous_version=previous,
                    base_url=base_url, theme=str(theme.resolve()) if theme else None, reason=reason,
                    load_imports=imports, include_imported=include_imported,
                    include_individuals=individuals, evaluation=_eval_overrides(oops, robot),
                    competency_questions=[str(Path(c).resolve()) for c in cq] if cq else None)
    try:
        with console.status("Building documentation…"):
            if single_file:
                target = output or Path("ontology.html")
                if target.suffix.lower() != ".html":
                    target = target / "index.html"
                res = build_single_file(source, target, config=config, **ov)
            else:
                res = do_build(source, out=output, config=config, **ov)
    except (ValueError, FileNotFoundError) as e:
        err.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(2) from e
    o = res.ontology
    from .render.i18n import Translator

    tr = Translator("en")
    counts = ", ".join(tr.kind_count(k, n) for k, n in o.stats.items() if k != "triples")
    where = res.output if res.output.suffix == ".html" else res.output / "index.html"
    console.print(f"[green]✓[/] [bold]{o.metadata.title or 'Ontology'}[/] → {where}")
    console.print(f"  {counts}")
    if res.report:
        s = res.report.summary
        console.print(f"  quality: [red]{s['error']} errors[/], [yellow]{s['warning']} warnings[/], "
                      f"[cyan]{s['info']} suggestions[/]  (ontoreview check for details)")
    if res.competency_questions:
        c = res.competency_questions.summary
        console.print(f"  competency questions: {c['passed']} answerable, {c['failed']} not answerable, "
                      f"{c['error']} errors, {c['untested']} without query")
    if res.report and res.report.external:
        for ext in res.report.external:
            if ext.error:
                console.print(f"  [yellow]{ext.tool}: {_rich_escape(ext.error)}[/]")
            else:
                e = ext.summary
                console.print(f"  {ext.tool}: {e['error']} errors, {e['warning']} warnings, {e['info']} suggestions")
    if res.changelog:
        c = res.changelog.summary
        console.print(f"  changelog: +{c['added']} −{c['removed']} ~{c['modified']}")
    missing = o.metadata.missing()
    if missing:
        console.print(f"  [dim]missing metadata: {', '.join(missing)}[/]")
    console.print(f"  [dim]done in {res.seconds:.2f}s[/]")
    if open_browser:
        webbrowser.open(where.resolve().as_uri())


@app.command()
def serve(
    source: str | None = SourceArg,
    config: Path | None = ConfigOpt,
    output: Path | None = typer.Option(None, "--output", "-o"),
    port: int = typer.Option(8000, "--port", "-P"),
    host: str = typer.Option("127.0.0.1", "--host"),
    watch: bool = typer.Option(True, "--watch/--no-watch", help="Rebuild when the ontology changes."),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build, serve locally and live-reload on changes."""
    _setup_logging(verbose)
    from .build import build as do_build
    from .build import resolve_config

    cfg = resolve_config(source, config)
    out = output or cfg.resolve(cfg.output) or Path("docs")

    def rebuild() -> None:
        try:
            res = do_build(None, out=out, config=cfg, live_reload=True)
            console.print(f"[green]✓[/] rebuilt in {res.seconds:.2f}s")
        except Exception as e:  # noqa: BLE001
            err.print(f"[bold red]Build failed:[/] {e}")

    rebuild()
    src = cfg.source or ""
    watched: list[Path] = []
    if watch and not src.startswith("http"):
        sp = cfg.resolve(src)
        exts = {".ttl", ".owl", ".rdf", ".jsonld", ".nt", ".n3", ".yaml", ".yml", ".md", ".toml"}
        extra = [cfg.resolve(x) for x in (cfg.introduction, cfg.custom_css, cfg.head_html,
                                          *[c.file for c in cfg.custom_sections]) if x]
        watched = sorted({p for p in sp.parent.glob("*") if p.is_file() and p.suffix in exts}
                         | {p for p in extra if p and p.is_file()})

        def loop() -> None:
            mtimes = {p: p.stat().st_mtime for p in watched if p.exists()}
            while True:
                time.sleep(0.8)
                changed = False
                for p in watched:
                    try:
                        m = p.stat().st_mtime
                    except FileNotFoundError:
                        continue
                    if mtimes.get(p) != m:
                        mtimes[p] = m
                        changed = True
                if changed:
                    rebuild()

        threading.Thread(target=loop, daemon=True).start()

    handler = functools.partial(_QuietHandler, directory=str(out))
    try:
        httpd = http.server.ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        err.print(f"[bold red]Cannot listen on {host}:{port}:[/] {e.strerror}. Try --port <other>.")
        raise typer.Exit(2) from e
    url = f"http://{host}:{port}/"
    console.print(f"Serving [bold]{out}[/] at [link={url}]{url}[/]"
                  + (f" (watching {len(watched)} files)" if watched else "") + " — Ctrl+C to stop")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("bye")


@app.command()
def studio(
    source: str | None = typer.Argument(None, help="Optional ontology to open on start."),
    port: int = typer.Option(8000, "--port", "-P"),
    host: str = typer.Option("127.0.0.1", "--host"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Local generator UI: open an ontology, preview the document, export a single HTML file."""
    from .studio import serve_studio

    try:
        st, httpd = serve_studio(host, port, preload=source)
    except OSError as e:
        err.print(f"[bold red]Cannot listen on {host}:{port}:[/] {e.strerror}. Try --port <other>.")
        raise typer.Exit(2) from e
    url = f"http://{host}:{port}/"
    console.print(f"ontoreview studio at [link={url}]{url}[/] (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("bye")
    finally:
        st.close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".ttl": "text/turtle", ".jsonld": "application/ld+json", ".owl": "application/rdf+xml",
        ".nt": "application/n-triples",
    }

    def log_message(self, format, *args):  # noqa: A002
        pass


@app.command()
def check(
    source: str | None = SourceArg,
    config: Path | None = ConfigOpt,
    fmt: CheckFormat = typer.Option(CheckFormat.console, "--format", "-f"),
    fail_on: FailOn = typer.Option(FailOn.error, "--fail-on", help="Exit 1 if findings at/above this severity."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write the report to a file."),
    cq: list[str] | None = typer.Option(None, "--cq", help="Competency questions file; repeatable."),
    oops: bool | None = typer.Option(None, "--oops/--no-oops", help="Also run OOPS! (uploads the ontology to oops.linkeddata.es)."),
    robot: str | None = typer.Option(None, "--robot", help="ROBOT report: auto (if installed), on, off, or path to robot.jar."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run quality checks: built-in rules, plus ROBOT and OOPS! when enabled (great for CI)."""
    _setup_logging(verbose)
    from .build import check as do_check

    try:
        ev = _eval_overrides(oops, robot)
        extra = {"evaluation": ev} if ev else {}
        if cq:
            extra["competency_questions"] = [str(Path(c).resolve()) for c in cq]
        onto, report = do_check(source, config=config, **extra)
    except (ValueError, FileNotFoundError) as e:
        err.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(2) from e

    if fmt == CheckFormat.json:
        text = report.to_json()
        if output:
            output.write_text(text, "utf-8")
        else:
            console.print_json(text)
    elif fmt == CheckFormat.html:
        from .render.site import SiteRenderer, codeticks  # noqa: F401

        html = _report_html(onto, report)
        target = output or Path("quality.html")
        target.write_text(html, "utf-8")
        console.print(f"Report written to {target}")
    else:
        if not report.findings:
            console.print("[green]✓ No issues found.[/]")
        for rule, findings in report.by_rule():
            sev = findings[0].severity
            console.print(f"\n[{SEV_STYLE[sev]}]{sev.upper():8}[/] [bold]{rule.id}[/] {rule.title} "
                          f"[dim]({len(findings)})[/]")
            for f in findings[:50]:
                msg = re.sub(r"`([^`]+)`", r"[bold]\1[/]", _rich_escape(f.message))
                console.print(f"   • {msg}")
            if len(findings) > 50:
                console.print(f"   [dim]… and {len(findings) - 50} more[/]")
        _print_external(report)
        s = report.summary
        console.print(f"\n[bold]{s['error']}[/] errors, [bold]{s['warning']}[/] warnings, "
                      f"[bold]{s['info']}[/] suggestions in {len(onto.terms)} terms.")
    if fail_on != FailOn.never and report.failed(fail_on.value):
        raise typer.Exit(1)


def _rich_escape(s: str) -> str:
    return s.replace("[", "\\[")


def _report_html(onto, report) -> str:
    from .config import Config
    from .render.site import Section, SiteRenderer

    cfg = Config()
    r = SiteRenderer(cfg, onto, Path("."), report=report)
    tmpl = r.env.from_string(
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Quality report · {{ meta.title }}</title><style>{{ css|safe }}</style></head>'
        '<body><main class="content" style="margin:auto">{% include "sections/quality.html" %}</main></body></html>'
    )
    from .render.site import THEME_DIR

    css = (THEME_DIR / "static" / "ontoreview.css").read_text("utf-8")
    s = Section("quality", f"Quality report: {onto.metadata.title or ''}", "quality.html",
                context={"report": report})
    return tmpl.render(s=s, css=css, page="index.html", sections=[s])


@app.command()
def diff(
    old: str = typer.Argument(..., help="Previous version (file or URL)."),
    new: str = typer.Argument(..., help="New version (file or URL)."),
    fmt: DiffFormat = typer.Option(DiffFormat.console, "--format", "-f"),
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Show what changed between two versions of an ontology."""
    from .diff import compare_files

    log = compare_files(old, new)
    if fmt == DiffFormat.json:
        text = log.to_json()
    elif fmt == DiffFormat.markdown:
        text = log.to_markdown()
    else:
        text = None
    if text is not None:
        if output:
            output.write_text(text, "utf-8")
            console.print(f"Written to {output}")
        else:
            console.print(text, markup=False, highlight=False)
        return
    t = Table(title=f"{log.old_version or old} → {log.new_version or new}", show_lines=False)
    t.add_column("", width=2)
    t.add_column("Term")
    t.add_column("Kind", style="dim")
    t.add_column("Details", overflow="fold")
    for c in log.added:
        t.add_row("[green]+[/]", c.label, c.kind.replace("_", " "), c.curie or c.iri)
    for c in log.removed:
        t.add_row("[red]−[/]", c.label, c.kind.replace("_", " "), c.curie or c.iri)
    for c in log.metadata_changes + log.modified:
        details = "\n".join([f"[red]− {p}: {_rich_escape(v)}[/]" for p, v in c.removed]
                            + [f"[green]+ {p}: {_rich_escape(v)}[/]" for p, v in c.added])
        t.add_row("[yellow]~[/]", c.label, c.kind.replace("_", " "), details)
    if log.empty:
        console.print("No differences.")
    else:
        console.print(t)


@app.command("cq-template")
def cq_template(
    path: Path = typer.Argument(Path("competency-questions.yaml"),
                                help="Where to write the template: .yaml, .csv, .tsv or .xlsx"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Write a starter competency-questions file (YAML, CSV/TSV or Excel)."""
    from .cq import write_template

    if path.exists() and not force:
        err.print(f"{path} exists (use --force to overwrite).")
        raise typer.Exit(1)
    write_template(path)
    console.print(f"[green]✓[/] wrote {path}. Add it with: ontoreview build --cq {path}  "
                  f"(or competency_questions = [\"{path}\"] in ontoreview.toml)")


@app.command("export")
def export_cmd(
    source: str | None = SourceArg,
    fmt: ExportFormat = typer.Option(ExportFormat.markdown, "--format", "-f",
                                     help="markdown (MkDocs/Docusaurus) or myst (Sphinx)."),
    output: Path = typer.Option(Path("docs-md"), "--output", "-o"),
    config: Path | None = ConfigOpt,
) -> None:
    """Export the documentation as Markdown or MyST for another static-site generator."""
    from .build import load, resolve_config
    from .export import export_markdown
    from .model.extract import extract

    cfg = resolve_config(source, config)
    onto = extract(load(cfg), cfg)
    files = export_markdown(onto, output, myst=fmt == ExportFormat.myst)
    console.print(f"[green]✓[/] wrote {len(files)} files to {output}")


CI_WORKFLOW = """name: Ontology docs

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install ontoreview
      - name: Quality checks
        run: ontoreview check --fail-on error
      - name: Build documentation
        run: ontoreview build
      - uses: actions/upload-pages-artifact@v3
        if: github.ref == 'refs/heads/main'
        with:
          path: {output}
  deploy:
    if: github.ref == 'refs/heads/main'
    needs: docs
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
"""

TOML_TEMPLATE = """# ontoreview configuration: https://github.com/tekrajchhetri/ontoreview
source = "{source}"
output = "docs"
layout = "single"          # "single" or "multi"
languages = ["en"]          # first one is the default; others are built under /<lang>/
# base_url = "https://w3id.org/my-ontology"
# previous_version = "releases/1.0.0.ttl"   # enables the changelog
# introduction = "docs/intro.md"
# custom_css = "docs/custom.css"
# reason = true             # show inferred superclasses (pip install 'ontoreview[reason]')

serializations = ["ttl", "owl", "jsonld", "nt"]

[sections]
graph = true
quality = true
changelog = true

[checks]
disable = []                # e.g. ["OB019"]

# Metadata found in the ontology is used automatically; anything here overrides it.
[metadata]
# title = "My Ontology"
# license = "https://creativecommons.org/licenses/by/4.0/"

# [[custom_sections]]
# title = "Examples"
# file = "docs/examples.md"
# position = "after-terms"
"""


@app.command()
def init(
    source: str | None = typer.Argument(None, help="Ontology file to document."),
    from_widoco: Path | None = typer.Option(None, "--from-widoco", help="Widoco config.properties to migrate."),
    ci: bool = typer.Option(True, "--ci/--no-ci", help="Also write a GitHub Pages workflow."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing files."),
) -> None:
    """Create ontoreview.toml (and a GitHub Actions workflow) in the current directory."""
    target = Path("ontoreview.toml")
    if target.exists() and not force:
        err.print("ontoreview.toml already exists (use --force to overwrite).")
        raise typer.Exit(1)
    if source is None:
        candidates = [p for ext in ("ttl", "owl", "rdf", "jsonld", "yaml", "yml") for p in Path(".").glob(f"*.{ext}")]
        source = str(candidates[0]) if candidates else "ontology.ttl"
    if from_widoco:
        from .widoco import widoco_to_toml

        text = widoco_to_toml(from_widoco, source)
    else:
        text = TOML_TEMPLATE.format(source=source)
    target.write_text(text, "utf-8")
    console.print(f"[green]✓[/] wrote {target}")
    if ci:
        wf = Path(".github/workflows/ontoreview.yml")
        if wf.exists() and not force:
            console.print(f"[dim]{wf} exists, skipped[/]")
        else:
            wf.parent.mkdir(parents=True, exist_ok=True)
            wf.write_text(CI_WORKFLOW.format(output="docs"), "utf-8")
            console.print(f"[green]✓[/] wrote {wf}")
    console.print("Next: [bold]ontoreview serve[/]")


if __name__ == "__main__":  # pragma: no cover
    app()
