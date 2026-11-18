"""Command-line interface: ``ontoreview build | serve | check | diff | export | init``."""

from __future__ import annotations

import functools
import http.server
import logging
import sys
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
    help="OntoReview: documentation and quality review for OWL, RDFS, SKOS and LinkML models.\n\n"
         "Most people use the app: [bold]ontoreview ui[/] (or [bold]ontoreview-ui[/]). The other commands are "
         "for automation and CI.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console(emoji=False)
ADVANCED = "Advanced / CI"
err = Console(stderr=True, emoji=False)



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
    html = "html"


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


def _eval_overrides(oops: bool | None, robot: str | None, reasoner: str | None = None,
                    ontocheck: bool | None = None, iri: bool | None = None, offline: bool = False) -> dict | None:
    ev = {}
    if iri is not None:
        ev["iri_checks"] = "on" if iri else "off"
    if offline:
        ev["iri_network"] = False
    if ontocheck is not None:
        ev["ontocheck"] = "on" if ontocheck else "off"
    if reasoner is not None:
        if reasoner.lower() not in ("hermit", "elk", "off"):
            raise typer.BadParameter("use hermit, elk or off", param_hint="--reasoner")
        ev["reasoner"] = reasoner.lower()
    if oops is not None:
        ev["oops"] = "on" if oops else "off"
    if robot is not None:
        if robot not in ("auto", "on", "off"):
            ev["robot"], ev["robot_path"] = "on", robot
        else:
            ev["robot"] = robot
    return ev or None


def _folder_source(source: str | None, config: Path | None) -> Path | None:
    """The input folder when the source (argument, or `source` in the config) is a directory."""
    if source and not source.startswith(("http://", "https://")):
        return Path(source) if Path(source).is_dir() else None
    if source is None:
        from .config import load_config

        try:
            cfg = load_config(config)
        except Exception:  # noqa: BLE001 - let the normal path report config errors
            return None
        if cfg.source and not cfg.source.startswith(("http://", "https://")):
            p = cfg.resolve(cfg.source)
            return p if p and p.is_dir() else None
    return None


def _print_collection(res, verb: str) -> None:
    table = Table(box=None, pad_edge=False, show_header=True, header_style="bold")
    table.add_column("ontology")
    table.add_column("terms", justify="right")
    table.add_column("quality")
    table.add_column("output")
    for e in res.entries:
        if e.error:
            table.add_row(f"[red]✗[/] {_rich_escape(e.source)}", "", "", f"[red]{_rich_escape(e.error)[:80]}[/]")
            continue
        q = e.quality
        qual = f"[red]{q.get('error', 0)}[/] err, [yellow]{q.get('warning', 0)}[/] warn" if q else ""
        ext = "; ".join(f"{x['tool']}: " + ("failed" if x["problem"] else f"{x['summary']['error']} err")
                        for x in e.external)
        table.add_row(f"[green]✓[/] {_rich_escape(e.title)}", str(e.terms), qual + (f"  [dim]{ext}[/]" if ext else ""),
                      f"{e.slug}/")
    console.print(table)
    for sk in res.skipped:
        console.print(f"  [dim]skipped (unsupported format): {_rich_escape(sk)}[/]")
    index = res.output / ("index.html" if verb == "built" else "index.md")
    console.print(f"[green]✓[/] {verb} {len(res.ok)} of {len(res.entries)} ontologies → {index}"
                  f"  [dim]{res.seconds:.2f}s[/]")


def _version_cb(value: bool) -> None:
    if value:
        console.print(f"ontoreview {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", callback=_version_cb, is_eager=True,
                                 help="Show version and exit."),
) -> None:
    if ctx.invoked_subcommand is None:
        console.print(f"[bold]OntoReview[/] {__version__}\n")
        console.print("Start the app:   [bold]ontoreview ui[/]        (or [bold]ontoreview-ui[/])")
        console.print("                 opens http://127.0.0.1:8765 in your browser; "
                      "[dim]--port N, --no-browser[/]")
        console.print('Needs the extra: [bold]pip install "ontoreview\\[ui]"[/]  (Python 3.11+)\n')
        console.print("[dim]Automation and CI commands (build, export, check, …): ontoreview --help[/]")


@app.command("ui")
def ui_cmd(
    port: int | None = typer.Option(None, "--port", "-p", help="Port (default: the first free port from 8765)."),
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind; keep 127.0.0.1 unless you know why."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser window."),
) -> None:
    """Start the OntoReview app in your browser (recommended)."""
    from .ui import main as ui_main

    argv = ["--host", host] + (["--port", str(port)] if port else []) + (["--no-browser"] if no_browser else [])
    ui_main(argv)


SourceArg = typer.Argument(None, help="Ontology file, URL or folder of ontologies (RDF in any syntax, or LinkML YAML).")
ConfigOpt = typer.Option(None, "--config", "-c", help="Path to ontoreview.toml (auto-discovered by default).")


@app.command(rich_help_panel=ADVANCED)
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
    oops: bool | None = typer.Option(None, "--oops/--no-oops", help="--oops: full OOPS! pitfall catalogue; --no-oops: never upload to oops.linkeddata.es. By default OOPS! runs alongside ROBOT, skipping what ROBOT checks (full when ROBOT cannot run)."),
    robot: str | None = typer.Option(None, "--robot", help="ROBOT report: auto (default: local robot, else Docker; OOPS! fallback), on (also report if unavailable), off, or a path to a robot executable."),
    reasoner: str | None = typer.Option(None, "--reasoner", help="Logical consistency check through ROBOT: hermit (default, OWL 2 DL), elk (fast, OWL 2 EL only) or off."),
    ontocheck: bool | None = typer.Option(None, "--ontocheck/--no-ontocheck", help="OntoCheck metrics: labeling, structural, accessibility and naming (default: on)."),
    iri: bool | None = typer.Option(None, "--iri/--no-iri", help="IRI checks: syntax, header, ontology-IRI resolution, external terms (default: on)."),
    offline: bool = typer.Option(False, "--offline", help="IRI checks use only the bundled and cached SQLite database (no OLS, BioPortal or downloads)."),
    single_file: bool = typer.Option(False, "--single-file", help="Write one self-contained HTML file."),
    open_browser: bool = typer.Option(False, "--open", help="Open the result in a browser."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate the documentation website. SOURCE may be a folder: each ontology in it gets its own
    sub-folder in the output, mirroring the source layout, plus an index page."""
    _setup_logging(verbose)
    from .build import build as do_build
    from .build import build_single_file

    ov = _overrides(layout=layout.value if layout else None, languages=lang, previous_version=previous,
                    base_url=base_url, theme=str(theme.resolve()) if theme else None, reason=reason,
                    load_imports=imports, include_imported=include_imported,
                    include_individuals=individuals, evaluation=_eval_overrides(oops, robot, reasoner, ontocheck, iri, offline),
                    competency_questions=[str(Path(c).resolve()) for c in cq] if cq else None)
    folder = _folder_source(source, config)
    if folder is not None:
        from .collection import build_collection

        try:
            with console.status(f"Building documentation for every ontology in {folder}…"):
                res = build_collection(folder, output or Path("docs"), config=config,
                                       single_file=single_file, **ov)
        except (ValueError, FileNotFoundError) as e:
            err.print(f"[bold red]Error:[/] {e}")
            raise typer.Exit(2) from e
        _print_collection(res, "built")
        if open_browser:
            webbrowser.open((res.output / "index.html").resolve().as_uri())
        if res.failed:
            raise typer.Exit(1)
        return
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
        s = res.report.totals
        console.print(f"  quality (all checks): [red]{s['error']} errors[/], [yellow]{s['warning']} warnings[/], "
                      f"[cyan]{s['info']} suggestions[/]  (ontoreview check for details)")
        b = res.report.summary
        console.print(f"  built-in checks: {b['error']} errors, {b['warning']} warnings, {b['info']} suggestions")
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


@app.command(rich_help_panel=ADVANCED)
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


@app.command(rich_help_panel=ADVANCED)
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


@app.command(rich_help_panel=ADVANCED)
def check(
    source: str | None = SourceArg,
    config: Path | None = ConfigOpt,
    fmt: CheckFormat = typer.Option(CheckFormat.console, "--format", "-f"),
    fail_on: FailOn = typer.Option(FailOn.error, "--fail-on", help="Exit 1 if findings at/above this severity."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write the report to a file."),
    cq: list[str] | None = typer.Option(None, "--cq", help="Competency questions file; repeatable."),
    oops: bool | None = typer.Option(None, "--oops/--no-oops", help="--oops: full OOPS! pitfall catalogue; --no-oops: never upload to oops.linkeddata.es. By default OOPS! runs alongside ROBOT, skipping what ROBOT checks (full when ROBOT cannot run)."),
    robot: str | None = typer.Option(None, "--robot", help="ROBOT report: auto (default: local robot, else Docker; OOPS! fallback), on (also report if unavailable), off, or a path to a robot executable."),
    reasoner: str | None = typer.Option(None, "--reasoner", help="Logical consistency check through ROBOT: hermit (default, OWL 2 DL), elk (fast, OWL 2 EL only) or off."),
    ontocheck: bool | None = typer.Option(None, "--ontocheck/--no-ontocheck", help="OntoCheck metrics: labeling, structural, accessibility and naming (default: on)."),
    iri: bool | None = typer.Option(None, "--iri/--no-iri", help="IRI checks: syntax, header, ontology-IRI resolution, external terms (default: on)."),
    offline: bool = typer.Option(False, "--offline", help="IRI checks use only the bundled and cached SQLite database (no OLS, BioPortal or downloads)."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run quality checks: built-in rules, ROBOT report and a reasoner consistency check (Docker),
    with OOPS! as fallback (great for CI).
    SOURCE may be a folder: every ontology in it is checked; JSON output is keyed by file."""
    _setup_logging(verbose)
    from .build import check as do_check

    folder = _folder_source(source, config)
    if folder is not None:
        _check_folder(folder, config, fmt, fail_on, output, oops, robot, reasoner, ontocheck, iri, offline)
        return

    try:
        ev = _eval_overrides(oops, robot, reasoner, ontocheck, iri, offline)
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
            sys.stdout.write(text + "\n")   # raw JSON: safe to pipe
    elif fmt == CheckFormat.html:
        from .report.html import quality_html

        html = quality_html(onto, report)
        target = output or Path("quality.html")
        target.write_text(html, "utf-8")
        console.print(f"Report written to {target}")
    else:
        from .report.console import print_report

        print_report(console, onto, report)
    if fail_on != FailOn.never and report.failed(fail_on.value):
        raise typer.Exit(1)


def _check_folder(folder: Path, config: Path | None, fmt, fail_on, output: Path | None,
                  oops: bool | None, robot: str | None, reasoner: str | None = None,
                  ontocheck: bool | None = None, iri: bool | None = None, offline: bool = False) -> None:
    import json

    from .build import check as do_check
    from .collection import _config_for, find_ontologies

    files, skipped = find_ontologies(folder, [output] if output else None)
    if not files:
        err.print(f"[bold red]Error:[/] No ontology files found in {folder}")
        raise typer.Exit(2)
    ev = _eval_overrides(oops, robot, reasoner, ontocheck, iri, offline)
    extra = {"evaluation": ev} if ev else {}
    results, failed, broken = {}, False, False
    for f in files:
        rel = f.relative_to(folder.resolve()).as_posix()
        try:
            onto, report = do_check(f, config=_config_for(f, folder, config), **extra)
        except Exception as e:  # noqa: BLE001
            broken = True
            results[rel] = {"error": str(e)}
            if fmt == CheckFormat.console:
                console.print(f"[red]✗ {_rich_escape(rel)}[/]: {_rich_escape(str(e))}")
            continue
        failed = failed or (fail_on != FailOn.never and report.failed(fail_on.value))
        results[rel] = json.loads(report.to_json())
        if fmt == CheckFormat.console:
            s = report.totals
            mark = "[red]✗[/]" if fail_on != FailOn.never and report.failed(fail_on.value) else "[green]✓[/]"
            console.print(f"{mark} [bold]{_rich_escape(rel)}[/]  {s['error']} errors, {s['warning']} warnings, "
                          f"{s['info']} suggestions in {len(onto.terms)} terms (all checks)")
            for x in report.external:
                console.print(f"    {x.tool}: " + (f"[yellow]{_rich_escape(x.error)}[/]" if x.error else
                              f"{x.summary['error']} errors, {x.summary['warning']} warnings, {x.summary['info']} suggestions"))
    for sk in skipped:
        if fmt == CheckFormat.console:
            console.print(f"  [dim]skipped (unsupported format): {_rich_escape(sk.relative_to(folder.resolve()).as_posix())}[/]")
    if fmt != CheckFormat.console:
        text = json.dumps(results, indent=2, ensure_ascii=False)
        if output:
            output.write_text(text, "utf-8")
            console.print(f"Report written to {output}")
        else:
            sys.stdout.write(text + "\n")   # raw JSON: safe to pipe
    if broken:
        raise typer.Exit(2)
    if failed:
        raise typer.Exit(1)


def _rich_escape(s: str) -> str:
    return s.replace("[", "\\[")


@app.command(rich_help_panel=ADVANCED)
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
    elif fmt == DiffFormat.html:
        text = log.to_html(old_label=old, new_label=new)
    else:
        text = None
    if text is not None:
        if output:
            output.write_text(text, "utf-8")
            console.print(f"Written to {output}")
        else:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")   # raw: no wrapping, safe to pipe
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


@app.command("cq-template", rich_help_panel=ADVANCED)
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


@app.command("export", rich_help_panel=ADVANCED)
def export_cmd(
    source: str | None = SourceArg,
    fmt: ExportFormat = typer.Option(ExportFormat.markdown, "--format", "-f",
                                     help="markdown (MkDocs/Docusaurus) or myst (Sphinx)."),
    output: Path = typer.Option(Path("docs-md"), "--output", "-o"),
    config: Path | None = ConfigOpt,
) -> None:
    """Export the documentation as Markdown or MyST for another static-site generator.
    SOURCE may be a folder: each ontology is exported to its own sub-folder, plus an index.md."""
    from .build import load, resolve_config
    from .export import export_markdown
    from .model.extract import extract

    folder = _folder_source(source, config)
    if folder is not None:
        from .collection import export_collection

        try:
            res = export_collection(folder, output, config=config, myst=fmt == ExportFormat.myst)
        except (ValueError, FileNotFoundError) as e:
            err.print(f"[bold red]Error:[/] {e}")
            raise typer.Exit(2) from e
        _print_collection(res, "exported")
        if res.failed:
            raise typer.Exit(1)
        return
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

from .config import CONFIG_TEMPLATE as TOML_TEMPLATE  # noqa: E402  (shared with the app)


@app.command(rich_help_panel=ADVANCED)
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


# ------------------------------------------------------------------ term database (IRI checks)
terms_app = typer.Typer(help="The SQLite term database used by the IRI checks: list, search, add, runs.",
                        no_args_is_help=True)
app.add_typer(terms_app, name="terms", rich_help_panel=ADVANCED)


@terms_app.command("list")
def terms_list() -> None:
    """List stored vocabularies (bundled and cached)."""
    from .quality_checks import iri

    table = Table("vocabulary", "terms", "stored", "source")
    for d in iri.list_documents():
        table.add_row(_rich_escape(d["key"]), f"{d['terms']:,}", d["where"], _rich_escape(d["source_url"]))
    console.print(table)
    console.print(f"[dim]writable database: {iri.default_cache_path()}[/]")


@terms_app.command("search")
def terms_search(query: str = typer.Argument(..., help="Part of an IRI or label."),
                 limit: int = typer.Option(50, "--limit", "-n")) -> None:
    """Find terms by IRI or label."""
    from .quality_checks import iri

    rows = iri.search_terms(query, limit=limit)
    table = Table("label", "iri", "type", "vocabulary")
    for r in rows:
        table.add_row(_rich_escape(", ".join(r["labels"][:1])), _rich_escape(r["iri"]),
                      ", ".join(t.rsplit("#", 1)[-1].rsplit("/", 1)[-1] for t in r["types"][:2]),
                      _rich_escape(r["document"]) + (" [yellow](deprecated)[/]" if r["deprecated"] else ""))
    console.print(table)
    console.print(f"[dim]{len(rows)} term(s)[/]")


@terms_app.command("add")
def terms_add(source: str = typer.Argument(..., help="An ontology URL or a local file.")) -> None:
    """Add an ontology to the writable database (by URL with content negotiation, or a file)."""
    from .quality_checks import iri

    try:
        res = (iri.add_document(url=source) if source.startswith(("http://", "https://"))
               else iri.add_document(path=source))
    except (ValueError, OSError) as e:
        err.print(f"[bold red]Error:[/] {_rich_escape(str(e))}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] {_rich_escape(res['key'])}: {res['terms']:,} terms from {_rich_escape(res['source_url'])}")


@terms_app.command("runs")
def terms_runs(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """Recent IRI-check runs recorded in the database."""
    from .quality_checks import iri

    table = Table("#", "started", "ontology", "external terms", "result")
    for r in iri.recent_runs(limit=limit):
        sm = r.get("summary") or {}
        table.add_row(str(r["id"]), (r["started_at"] or "")[:19].replace("T", " "),
                      _rich_escape(Path(r.get("source") or "").name or (r.get("ontology_iri") or "")),
                      str(sm.get("external_terms", "")),
                      ", ".join(f"{v} {k}" for k, v in sorted((sm.get("statuses") or {}).items())))
    console.print(table)
