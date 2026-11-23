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
from rich.markup import escape
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
                    ontocheck: bool | None = None, iri: bool | None = None, offline: bool = False,
                    cdi: list[str] | None = None, cdi_domain: list[str] | None = None,
                    cdi_api_key: list[str] | None = None, cdi_ontoaligner: str | None = None,
                    no_cdi: bool = False, hf_token: str | None = None, si: dict | None = None) -> dict | None:
    ev = dict(si or {})
    if hf_token:
        ev["cdi_hf_token"] = hf_token
    if no_cdi:
        ev["cdi"] = "off"
    if cdi_ontoaligner is not None:
        if cdi_ontoaligner not in ("off", "fuzzy", "sbert"):
            raise typer.BadParameter("use fuzzy, sbert or off", param_hint="--cdi-ontoaligner")
        ev["cdi_ontoaligner"] = cdi_ontoaligner
    if cdi_api_key:
        keys = {}
        for item in cdi_api_key:
            repo, sep, key = item.partition("=")
            if not sep:
                repo, key = "bioportal", item
            keys[repo.strip()] = key.strip()
        ev["cdi_api_keys"] = keys
    if cdi:
        if not no_cdi:
            ev["cdi"] = "on"
        ev["cdi_references"] = [c if c.startswith(("ols", "bioportal", "ontoportal", "http://", "https://"))
                                and not Path(c).exists() else str(Path(c).expanduser().resolve()) for c in cdi]
    if cdi_domain:
        ev["cdi_domains"] = list(cdi_domain)
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


def _with_set(ev: dict | None, items: list[str] | None) -> dict | None:
    """Add ``--set KEY=VALUE`` settings (validated like ontoreview.toml) to the evaluation overrides."""
    from .cli_evaluate import parse_set
    extra = parse_set(items)
    return {**(ev or {}), **extra} or None


INTEROP_ONLY = {"robot": "off", "oops": "off", "ontocheck": "off", "iri_checks": "off", "reasoner": "off"}


def _si_overrides(no_si: bool = False, home: str | None = None, theta_s: float | None = None,
                  domains: list[str] | None = None, refs: list[str] | None = None) -> dict:
    """Scientific interoperability options -> ``[evaluation]`` overrides."""
    ev: dict = {}
    if no_si:
        ev["si"] = "off"
    if home:
        ev["si_home_domain"] = home
    if theta_s is not None:
        ev["si_theta_s"] = theta_s
    for item in domains or []:
        oid, sep, codes = item.partition("=")
        if not sep or not oid.strip():
            raise typer.BadParameter("use ONTOLOGY_ID=FIELD, e.g. ols:emi=1.5", param_hint="--si-domain")
        ev.setdefault("si_domain_map", {})[oid.strip()] = [c.strip() for c in codes.split(";") if c.strip()]
    if refs:
        ev["si_references"] = [r if r.startswith(("ols", "bioportal", "ontoportal", "http://", "https://"))
                               and not Path(r).exists() else str(Path(r).expanduser().resolve()) for r in refs]
    return ev


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
                      "[dim]--port N, --no-browser, --keep-running[/]")
        console.print('Needs the extra: [bold]pip install "ontoreview\\[ui]"[/]  (Python 3.11+)\n')
        console.print("[dim]Automation and CI commands (build, export, check, …): ontoreview --help[/]")


@app.command("ui")
def ui_cmd(
    port: int | None = typer.Option(None, "--port", "-p", help="Port (default: the first free port from 8765)."),
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind; keep 127.0.0.1 unless you know why."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser window."),
    keep_running: bool = typer.Option(False, "--keep-running", help="Keep running after the last browser tab is "
                                      "closed (otherwise the app stops about 10 s later)."),
) -> None:
    """Start the OntoReview app in your browser (recommended)."""
    from .ui import main as ui_main

    argv = ["--host", host] + (["--port", str(port)] if port else []) + (["--no-browser"] if no_browser else []) \
        + (["--keep-running"] if keep_running else [])
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
    cdi: list[str] | None = typer.Option(None, "--cdi", help="Score cross-domain interoperability against this reference; repeatable: a file or URL (RDF, or SSSOM .tsv), ols, ols:envo,chebi, bioportal, bioportal:NCIT, or another OLS/OntoPortal service as ols@https://…/api."),
    cdi_domain: list[str] | None = typer.Option(None, "--cdi-domain", help="The ontology's own domain; discovered reference ontologies from it are left out. Repeatable."),
    hf_token: str | None = typer.Option(None, "--hf-token", help="Optional Hugging Face token for downloading the CDI language models (higher rate limits). Prefer the HF_TOKEN environment variable to keep it out of shell history."),
    no_cdi: bool = typer.Option(False, "--no-cdi", help="Skip the cross-domain interoperability score (on by default; it queries OLS and runs a language model)."),
    cdi_ontoaligner: str | None = typer.Option(None, "--cdi-ontoaligner", help="Also match file/URL references with OntoAligner: sbert (sentence embeddings, default; model downloaded automatically), fuzzy (string similarity) or off. Needs ontoreview[cdi]."),
    cdi_api_key: list[str] | None = typer.Option(None, "--cdi-api-key", help="Optional API key for BioPortal (KEY or bioportal=KEY), another OntoPortal service (ontoportal=KEY or bioportal@host=KEY). Avoids shared rate limits; OLS needs none. Prefer BIOPORTAL_API_KEY / ONTOPORTAL_API_KEY to keep keys out of shell history."),
    no_si: bool = typer.Option(False, "--no-si", help="Skip the scientific interoperability degree (on by default; it reuses the cross-domain run and its --cdi references)."),
    si_home_domain: str | None = typer.Option(None, "--si-home-domain", help="The ontology's own scientific domain: an OECD field code (1.2) or name. Default: classified from its title and description."),
    si_theta_s: float | None = typer.Option(None, "--si-theta-s", help="θ_s: a domain counts as covered when its CDI reaches this (default 0.3)."),
    si_domain: list[str] | None = typer.Option(None, "--si-domain", help="Your scientific domain for a reference ontology, e.g. ols:emi=1.5 (several: ols:emi=1.5;1.6). Repeatable."),
    si_ref: list[str] | None = typer.Option(None, "--si-ref", help="Reference ontology for scientific interoperability only (same forms as --cdi: file, SSSOM, ols, ols:envo, bioportal:NCIT). Repeatable; default: the --cdi references."),
    set_: list[str] | None = typer.Option(None, "--set", metavar="KEY=VALUE", help="Any [evaluation] setting, e.g. --set cdi_tau=0.6 --set iri_network=false. Repeatable; see `ontoreview evaluate --list-options`."),
    single_file: bool = typer.Option(False, "--single-file", help="Write one self-contained HTML file."),
    standalone: bool | None = typer.Option(None, "--standalone/--no-standalone", help="Also write standalone.html (the whole documentation in one file) in the output folder (default: on)."),
    open_browser: bool = typer.Option(False, "--open", help="Open the result in a browser."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate the documentation website. SOURCE may be a folder: each ontology in it gets its own
    sub-folder in the output, mirroring the source layout, plus an index page."""
    _setup_logging(verbose)
    from .build import build as do_build
    from .build import build_single_file

    ov = _overrides(layout=layout.value if layout else None, languages=lang, previous_version=previous,
                    base_url=base_url, theme=str(theme.resolve()) if theme else None, reason=reason, standalone=standalone,
                    load_imports=imports, include_imported=include_imported,
                    include_individuals=individuals, evaluation=_with_set(_eval_overrides(oops, robot, reasoner, ontocheck, iri, offline, cdi, cdi_domain, cdi_api_key, cdi_ontoaligner, no_cdi, hf_token, _si_overrides(no_si, si_home_domain, si_theta_s, si_domain, si_ref)), set_),
                    competency_questions=[str(Path(c).resolve()) for c in cq] if cq else None)
    folder = _folder_source(source, config)
    if folder is not None:
        from .collection import build_collection

        try:
            with console.status(f"Building documentation for every ontology in {folder}…"):
                res = build_collection(folder, output or Path("docs"), config=config,
                                       single_file=single_file, **ov)
        except (ValueError, FileNotFoundError) as e:
            err.print(f"[bold red]Error:[/] {escape(str(e))}")
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
        err.print(f"[bold red]Error:[/] {escape(str(e))}")
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
    interop_only: bool = typer.Option(False, "--interop-only", help="Only the cross-domain and scientific interoperability checks: no built-in rules, ROBOT, reasoner, IRI checks, OntoCheck or OOPS!."),
    oops: bool | None = typer.Option(None, "--oops/--no-oops", help="--oops: full OOPS! pitfall catalogue; --no-oops: never upload to oops.linkeddata.es. By default OOPS! runs alongside ROBOT, skipping what ROBOT checks (full when ROBOT cannot run)."),
    robot: str | None = typer.Option(None, "--robot", help="ROBOT report: auto (default: local robot, else Docker; OOPS! fallback), on (also report if unavailable), off, or a path to a robot executable."),
    reasoner: str | None = typer.Option(None, "--reasoner", help="Logical consistency check through ROBOT: hermit (default, OWL 2 DL), elk (fast, OWL 2 EL only) or off."),
    ontocheck: bool | None = typer.Option(None, "--ontocheck/--no-ontocheck", help="OntoCheck metrics: labeling, structural, accessibility and naming (default: on)."),
    iri: bool | None = typer.Option(None, "--iri/--no-iri", help="IRI checks: syntax, header, ontology-IRI resolution, external terms (default: on)."),
    offline: bool = typer.Option(False, "--offline", help="IRI checks use only the bundled and cached SQLite database (no OLS, BioPortal or downloads)."),
    cdi: list[str] | None = typer.Option(None, "--cdi", help="Score cross-domain interoperability against this reference; repeatable: a file or URL (RDF, or SSSOM .tsv), ols, ols:envo,chebi, bioportal, bioportal:NCIT, or another OLS/OntoPortal service as ols@https://…/api."),
    cdi_domain: list[str] | None = typer.Option(None, "--cdi-domain", help="The ontology's own domain; discovered reference ontologies from it are left out. Repeatable."),
    hf_token: str | None = typer.Option(None, "--hf-token", help="Optional Hugging Face token for downloading the CDI language models (higher rate limits). Prefer the HF_TOKEN environment variable to keep it out of shell history."),
    no_cdi: bool = typer.Option(False, "--no-cdi", help="Skip the cross-domain interoperability score (on by default; it queries OLS and runs a language model)."),
    cdi_ontoaligner: str | None = typer.Option(None, "--cdi-ontoaligner", help="Also match file/URL references with OntoAligner: sbert (sentence embeddings, default; model downloaded automatically), fuzzy (string similarity) or off. Needs ontoreview[cdi]."),
    cdi_api_key: list[str] | None = typer.Option(None, "--cdi-api-key", help="Optional API key for BioPortal (KEY or bioportal=KEY), another OntoPortal service (ontoportal=KEY or bioportal@host=KEY). Avoids shared rate limits; OLS needs none. Prefer BIOPORTAL_API_KEY / ONTOPORTAL_API_KEY to keep keys out of shell history."),
    no_si: bool = typer.Option(False, "--no-si", help="Skip the scientific interoperability degree (on by default; it reuses the cross-domain run and its --cdi references)."),
    si_home_domain: str | None = typer.Option(None, "--si-home-domain", help="The ontology's own scientific domain: an OECD field code (1.2) or name. Default: classified from its title and description."),
    si_theta_s: float | None = typer.Option(None, "--si-theta-s", help="θ_s: a domain counts as covered when its CDI reaches this (default 0.3)."),
    si_domain: list[str] | None = typer.Option(None, "--si-domain", help="Your scientific domain for a reference ontology, e.g. ols:emi=1.5 (several: ols:emi=1.5;1.6). Repeatable."),
    si_ref: list[str] | None = typer.Option(None, "--si-ref", help="Reference ontology for scientific interoperability only (same forms as --cdi: file, SSSOM, ols, ols:envo, bioportal:NCIT). Repeatable; default: the --cdi references."),
    set_: list[str] | None = typer.Option(None, "--set", metavar="KEY=VALUE", help="Any [evaluation] setting, e.g. --set cdi_tau=0.6 --set iri_network=false. Repeatable; see `ontoreview evaluate --list-options`."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run quality checks: built-in rules, ROBOT report and a reasoner consistency check (Docker),
    with OOPS! as fallback (great for CI).
    SOURCE may be a folder: every ontology in it is checked; JSON output is keyed by file."""
    _setup_logging(verbose)
    from .build import check as do_check

    si_ev = _si_overrides(no_si, si_home_domain, si_theta_s, si_domain, si_ref) | (INTEROP_ONLY if interop_only else {})
    folder = _folder_source(source, config)
    if folder is not None:
        _check_folder(folder, config, fmt, fail_on, output, oops, robot, reasoner, ontocheck, iri, offline, cdi, cdi_domain, cdi_api_key, cdi_ontoaligner, no_cdi, hf_token, si_ev, interop_only)
        return

    try:
        ev = _with_set(_eval_overrides(oops, robot, reasoner, ontocheck, iri, offline, cdi, cdi_domain, cdi_api_key, cdi_ontoaligner, no_cdi, hf_token, si_ev), set_)
        extra = {"evaluation": ev} if ev else {}
        if cq:
            extra["competency_questions"] = [str(Path(c).resolve()) for c in cq]
        import datetime as _dt
        started = _dt.datetime.now(_dt.timezone.utc)
        onto, report = do_check(source, config=config, **extra)
        if interop_only:
            from .ui_core import interop_only as keep_interop
            keep_interop(report)
        if output:      # self-contained: cdi.json, si.json, iri-checks.json, provenance.ttl next to the report
            from .build import check_records
            check_records(output.parent / f"{output.stem}-records", source or Path(config or ".").name,
                          onto, report, started)
    except (ValueError, FileNotFoundError) as e:
        err.print(f"[bold red]Error:[/] {escape(str(e))}")
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
                  ontocheck: bool | None = None, iri: bool | None = None, offline: bool = False,
                  cdi: list[str] | None = None, cdi_domain: list[str] | None = None,
                  cdi_api_key: list[str] | None = None, cdi_ontoaligner: str | None = None,
                  no_cdi: bool = False, hf_token: str | None = None, si: dict | None = None,
                  interop_only: bool = False) -> None:
    import json

    from .build import check as do_check
    from .collection import _config_for, find_ontologies

    files, skipped = find_ontologies(folder, [output] if output else None)
    if not files:
        err.print(f"[bold red]Error:[/] No ontology files found in {folder}")
        raise typer.Exit(2)
    ev = _eval_overrides(oops, robot, reasoner, ontocheck, iri, offline, cdi, cdi_domain, cdi_api_key, cdi_ontoaligner, no_cdi, hf_token, si)
    extra = {"evaluation": ev} if ev else {}
    results, failed, broken = {}, False, False
    for f in files:
        rel = f.relative_to(folder.resolve()).as_posix()
        try:
            import datetime as _dt
            started = _dt.datetime.now(_dt.timezone.utc)
            onto, report = do_check(f, config=_config_for(f, folder, config), **extra)
            if interop_only:
                from .ui_core import interop_only as keep_interop
                keep_interop(report)
            if output:
                from .build import check_records
                check_records(output.parent / f"{output.stem}-records" / Path(rel).with_suffix(""), f, onto,
                              report, started)
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
            err.print(f"[bold red]Error:[/] {escape(str(e))}")
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
    env:
      ONTOREVIEW_WORKFLOW: ontoreview-init   # lets OntoReview's anonymous statistics tell this workflow apart
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
    """List stored ontologies, vocabularies and schemas (bundled and cached)."""
    from .quality_checks import iri

    table = Table("ontology / vocabulary / schema", "terms", "stored", "retrieved", "iri")
    for g in iri.list_groups():
        table.add_row(_rich_escape(g["title"]), f"{g['terms']:,}", g["where"], g["fetched_at"][:10],
                      _rich_escape(g["group"]) + (f" [dim]({len(g['documents'])} documents)[/]" if len(g["documents"]) > 1 else ""))
    console.print(table)
    console.print(f"[dim]writable database: {iri.default_cache_path()}[/]")


@terms_app.command("search")
def terms_search(query: str = typer.Argument(..., help="Part of an IRI or label."),
                 limit: int = typer.Option(50, "--limit", "-n")) -> None:
    """Find terms by IRI or label."""
    from .quality_checks import iri

    rows = iri.search_terms(query, limit=limit)
    table = Table("label", "iri", "type", "ontology / vocabulary")
    for r in rows:
        table.add_row(_rich_escape(", ".join(r["labels"][:1])), _rich_escape(r["iri"]),
                      ", ".join(t.rsplit("#", 1)[-1].rsplit("/", 1)[-1] for t in r["types"][:2]),
                      _rich_escape(r["vocabulary"]) + (" [yellow](deprecated)[/]" if r["deprecated"] else ""))
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


@terms_app.command("refresh")
def terms_refresh(key: str | None = typer.Argument(None, help="Vocabulary key (see `terms list`)."),
                  stale: bool = typer.Option(False, "--stale", help="Refresh every vocabulary older than --days."),
                  days: float = typer.Option(30, "--days", help="Age limit for --stale.")) -> None:
    """Fetch stored vocabularies again (bundled ones are refreshed into the writable database)."""
    from .quality_checks import iri

    keys = [key] if key else [d["key"] for d in iri.list_documents()
                              if stale and (d.get("age_days") or 0) > days]
    if not keys:
        console.print("Nothing to refresh." if stale else "Give a vocabulary key or --stale.")
        return
    failed = False
    for k in dict.fromkeys(keys):
        try:
            r = iri.refresh_document(k)
            console.print(f"[green]✓[/] {_rich_escape(k)}: {r['terms']:,} terms"
                          + (" (changed)" if r["changed"] else " (unchanged)"))
        except (ValueError, OSError) as e:
            failed = True
            err.print(f"[yellow]✗[/] {_rich_escape(k)}: {_rich_escape(str(e)[:200])}")
    if failed:
        raise typer.Exit(1)


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


# ---------------------------------------------------------------- fixes
fix_app = typer.Typer(help="Suggested fixes for quality findings, written to a new ontology file (the original is "
                           "never changed).", no_args_is_help=True)
app.add_typer(fix_app, name="fix", rich_help_panel=ADVANCED)


def _fix_session(source: str, config: Path | None):
    from .fixes import FixSession
    try:
        return FixSession(source, config)
    except (ValueError, FileNotFoundError) as e:
        err.print(f"[bold red]Error:[/] {escape(str(e))}")
        raise typer.Exit(2) from e


AI_PANEL = "AI suggestions"


def _ai_config(cfg_ai, priority: str | None, ollama_model: str | None, ollama_url: str | None, hf_model: str | None,
               api_provider: str | None, api_model: str | None, api_base_url: str | None, timeout: float | None):
    """The [ai] settings with the command-line choices applied (the API key only from the environment)."""
    from .config import AIConfig
    ov = {k: v for k, v in {"ollama_model": ollama_model, "ollama_url": ollama_url, "hf_model": hf_model,
                            "api_provider": api_provider, "api_model": api_model, "api_base_url": api_base_url,
                            "timeout": timeout}.items() if v is not None}
    if priority:
        ov["priority"] = [x.strip() for x in priority.split(",") if x.strip()]
    try:
        return AIConfig(**{**cfg_ai.model_dump(), **ov, "enabled": True})
    except Exception as e:  # noqa: BLE001 - pydantic ValidationError
        raise typer.BadParameter(str(e)) from e


def _source_info(source: str) -> dict:
    import hashlib
    p = Path(source)
    return {"location": source, "name": p.name,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}


@fix_app.command("list")
def fix_list(source: str = typer.Argument(..., help="Ontology file."), config: Path | None = ConfigOpt,
             json_out: bool = typer.Option(False, "--json", help="Print the result as JSON (schema ontoreview.fixes/1)."),
             output: Path | None = typer.Option(None, "--output", "-o", help="Write the JSON result to this file "
                                                "(then `fix apply --from FILE` applies suggestions from it)."),
             ai: bool = typer.Option(False, "--ai", help="Ask the AI source for suggestions: definitions for terms "
                                     "without one, ranked domains and ranges.", rich_help_panel=AI_PANEL),
             ai_limit: int = typer.Option(20, "--ai-limit", help="At most this many AI suggestions.",
                                          rich_help_panel=AI_PANEL),
             refine: list[str] | None = typer.Option(None, "--refine", help="Also suggest a clearer definition for "
                                                     "this term (IRI or label). Repeatable.", rich_help_panel=AI_PANEL),
             refine_instruction: str | None = typer.Option(None, "--refine-instruction", help="How to refine, e.g. "
                                                           "'shorter' or 'for non-experts'.", rich_help_panel=AI_PANEL),
             ai_description: bool = typer.Option(False, "--ai-description", help="Draft the ontology description "
                                                 "when it is missing.", rich_help_panel=AI_PANEL),
             ai_priority: str | None = typer.Option(None, "--ai-priority", help="Sources to try, in order: "
                                                    "ollama,hf,api.", rich_help_panel=AI_PANEL),
             ai_ollama_model: str | None = typer.Option(None, "--ai-ollama-model", rich_help_panel=AI_PANEL,
                                                        help="Ollama model, e.g. qwen3.5:4b."),
             ai_ollama_url: str | None = typer.Option(None, "--ai-ollama-url", rich_help_panel=AI_PANEL,
                                                      help="Ollama server (default http://localhost:11434)."),
             ai_hf_model: str | None = typer.Option(None, "--ai-hf-model", rich_help_panel=AI_PANEL,
                                                    help="Hugging Face model (downloaded on first use)."),
             ai_api_provider: str | None = typer.Option(None, "--ai-api-provider", rich_help_panel=AI_PANEL,
                                                        help="openai, anthropic, openrouter, gemini, mistral, groq or "
                                                             "custom. The key comes from the provider's environment "
                                                             "variable (OPENAI_API_KEY, ANTHROPIC_API_KEY, …)."),
             ai_api_model: str | None = typer.Option(None, "--ai-api-model", rich_help_panel=AI_PANEL,
                                                     help="Model id at the provider."),
             ai_api_base_url: str | None = typer.Option(None, "--ai-api-base-url", rich_help_panel=AI_PANEL,
                                                        help="OpenAI-compatible base URL (for custom)."),
             ai_timeout: float | None = typer.Option(None, "--ai-timeout", rich_help_panel=AI_PANEL,
                                                     help="Seconds per AI request.")):
    """List suggested fixes, required metadata first; with --ai, AI suggestions too. Nothing is changed."""
    import json as _json
    from datetime import datetime, timezone

    from . import __version__
    s = _fix_session(source, config)
    s.precheck()
    ai_info: dict = {"used": False}
    if ai or refine or ai_description:
        from .fixes.ai import AIError, ai_suggestions, draft_description, pick_source, refine_definition
        cfg_ai = _ai_config(s.cfg.ai, ai_priority, ai_ollama_model, ai_ollama_url, ai_hf_model, ai_api_provider,
                            ai_api_model, ai_api_base_url, ai_timeout)
        try:
            src = pick_source(cfg_ai, s.cfg.evaluation.cdi_hf_token)
            ai_info = {"used": True, **{k: v for k, v in src.describe().items() if "key" not in k}}
            if ai:
                ai_suggestions(s, src, limit=ai_limit)
            for t in refine or []:
                iri = t if t in s.onto.terms else next((k for k, v in s.onto.terms.items() if v.label == t), None)
                if iri is None:
                    err.print(f"[yellow]--refine:[/] no term {escape(t)}")
                    continue
                s.add(refine_definition(s, iri, src, refine_instruction or ""))
            if ai_description:
                d = next((x for x in s.suggestions if x.rule == "OB002" and x.fields), None)
                if d is not None:
                    text, prov = draft_description(s, src)
                    d.fields[0].value, d.made_by = text, prov | {"field": "description"}
        except AIError as e:
            ai_info = {"used": False, "error": str(e)}
            err.print(f"[yellow]AI:[/] {escape(str(e))}")
    result = {"schema": "ontoreview.fixes/1", "tool": {"name": "OntoReview", "version": __version__},
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": _source_info(source),
              "format": "linkml" if s.is_linkml else "rdf", "ai": ai_info,
              "required": [x.id for x in s.required_open()],
              "suggestions": [x.to_dict() | {"writes_to": "yaml" if s.yaml_writable(x) else "owl"} if s.is_linkml
                              else x.to_dict() for x in s.suggestions]}
    if output:
        output.write_text(_json.dumps(result, indent=2, ensure_ascii=False) + "\n", "utf-8")
    if json_out:
        sys.stdout.write(_json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        return
    t = Table(title=f"{len(s.suggestions)} suggested fixes for {Path(source).name}")
    for col in ("id", "kind", "rule", "fix", "term", "flags"):
        t.add_column(col)
    for x in s.suggestions:
        t.add_row(x.id, x.source + (" (required)" if x.required else ""), x.rule, escape(x.title),
                  escape(s.onto.terms[x.subject].label if x.subject in s.onto.terms else (x.subject or "ontology")),
                  ", ".join(x.flags))
    console.print(t)
    if ai_info.get("used"):
        console.print(f"AI: {ai_info.get('provider', ai_info.get('source'))} · {ai_info.get('model')}")
    if output:
        console.print(f"Saved to {output}; apply with: ontoreview fix apply {source} --from {output} --accept ID")
    if s.required_open():
        console.print("[bold]Required before docs:[/] " + ", ".join(x.title.lower() for x in s.required_open())
                      + ". Use: ontoreview fix apply SOURCE --set title=… --set license=… …")


@fix_app.command("apply")
def fix_apply(source: str = typer.Argument(..., help="Ontology file."), config: Path | None = ConfigOpt,
              from_: Path | None = typer.Option(None, "--from", help="Suggestions saved by `fix list -o FILE` "
                                                "(needed to apply AI suggestions: they are not re-generated)."),
              accept: list[str] | None = typer.Option(None, "--accept", help="Suggestion id to apply (option 1); "
                                                                            "ID:N picks option N. Repeatable."),
              accept_safe: bool = typer.Option(False, "--accept-safe", help="Apply every fix flagged safe."),
              set_: list[str] | None = typer.Option(None, "--set", help="Required metadata: title=…, description=…, "
                                                                       "license=URL, creators='Name | ORCID | email; …', version=…"),
              value: list[str] | None = typer.Option(None, "--value", metavar="ID=TEXT", help="The value for a "
                                                     "suggestion that asks for one (e.g. a definition). Repeatable."),
              text: list[str] | None = typer.Option(None, "--text", metavar="ID=TEXT", help="Your edited text for an "
                                                    "AI suggestion (instead of the AI's wording). Repeatable."),
              json_out: bool = typer.Option(False, "--json", help="Print the result as JSON (schema "
                                                                  "ontoreview.fix-result/1)."),
              output: Path | None = typer.Option(None, "--output", "-o", help="Default: the next version, e.g. a-v1.ttl.")):
    """Apply chosen fixes: writes a new file (a-v1.ttl), a patch and a record; the original is unchanged."""
    import json as _json

    from .fixes import FixError
    from .fixes.model import suggestion_from_dict
    s = _fix_session(source, config)
    if from_:
        saved = _json.loads(from_.read_text("utf-8"))
        want = (saved.get("source") or {}).get("sha256")
        have = _source_info(source)["sha256"]
        if want and have and want != have:
            err.print(f"[bold red]Error:[/] {escape(str(from_))} was made for another version of {Path(source).name}; "
                      "run `fix list` again.")
            raise typer.Exit(2)
        known = {x.id for x in s.suggestions}
        for d in saved.get("suggestions", []):
            x = suggestion_from_dict({k: v for k, v in d.items() if k != "writes_to"})
            if x.id not in known:
                s.replace(x) if x.kind == "L" else s.add(x)
    values = dict(v.split("=", 1) for v in (set_ or []) if "=" in v)
    if "creators" in values:
        values["creators"] = values["creators"].replace(";", "\n")
    per_id = dict(v.split("=", 1) for v in (value or []) if "=" in v)
    texts = dict(v.split("=", 1) for v in (text or []) if "=" in v)
    try:
        for x in s.suggestions:          # --set fills required metadata only (not every term's definition)
            names = [f.name for f in x.fields]
            if x.required and names and all(values.get(n) for n in names):
                s.accept(x.id, values=values)
        for sid, val in per_id.items():
            x = s.get(sid)
            if not x.fields:
                raise FixError(f"{sid} does not ask for a value; use --accept.")
            s.accept(sid, values={x.fields[0].name: val})
        for item in accept or []:
            sid, _, opt = item.partition(":")
            s.accept(sid, option=max(int(opt) - 1, 0) if opt else 0, text=texts.get(sid))
        for sid, t_ in texts.items():
            if sid not in s.accepted:
                s.accept(sid, text=t_)
        if accept_safe:
            s.accept_safe()
        r = s.write(output)
    except FixError as e:
        err.print(f"[bold red]Error:[/] {escape(str(e))}")
        raise typer.Exit(2) from e
    if json_out:
        rec = _json.loads(r.record.read_text("utf-8"))
        sys.stdout.write(_json.dumps({
            "schema": "ontoreview.fix-result/1", "source": _source_info(source),
            "output": {"path": str(r.path), "format": r.path.suffix.lstrip("."), "sha256": rec["output"]["sha256"]},
            "patch": str(r.patch), "record": str(r.record), "applied": r.applied, "not_applied": r.not_applied,
            "ai_assisted": sum(1 for a in rec["applied"] if a.get("ai_assisted")), "converted": rec.get("converted"),
            "fixed": r.fixed, "new_findings": r.new_findings, "before": r.before, "after": r.after,
            "still_required": [x.title for x in s.required_open()]}, indent=2, ensure_ascii=False) + "\n")
        return
    console.print(f"[green]✓[/] {r.path}  ({r.applied} fixes; {r.not_applied} not applied)")
    console.print(f"  patch {r.patch.name} · record {r.record.name}")
    console.print(f"  fixed: {len(r.fixed)} findings" + (f"; new: {', '.join(r.new_findings)}" if r.new_findings else ""))
    if s.required_open():
        console.print("[yellow]Still required before docs:[/] " + ", ".join(x.title.lower() for x in s.required_open()))


# every evaluation and every [evaluation] setting as an option, with a JSON result (cli_evaluate.py)
from .cli_evaluate import register as _register_evaluate  # noqa: E402

_register_evaluate(app, ADVANCED)


# ---------------------------------------------------------------- telemetry
telemetry_app = typer.Typer(help="Anonymous usage statistics: what is sent, and switching off the optional details.",
                            no_args_is_help=True)
app.add_typer(telemetry_app, name="telemetry", rich_help_panel=ADVANCED)


@telemetry_app.command("status")
def telemetry_status() -> None:
    """Whether telemetry is on, whether the optional details are sent, and where."""
    from . import telemetry
    for line in telemetry.status_lines():
        console.print(escape(line))


@telemetry_app.command("disable")
def telemetry_disable() -> None:
    """Stop sending the optional details (the mandatory usage statistics are still sent)."""
    from . import telemetry
    telemetry.set_details(False)
    console.print("[green]✓[/] Optional telemetry details are off. Mandatory usage statistics (country, commands "
                  "and checks run, platform) are still sent; see `ontoreview telemetry show`.")


@telemetry_app.command("off")
def telemetry_off() -> None:
    """Turn off all telemetry for this user (the same as DO_NOT_TRACK=1, but saved)."""
    from . import telemetry
    telemetry.set_enabled(False)
    console.print("[green]✓[/] Telemetry is off: nothing is sent from this computer (events not sent yet were "
                  "discarded). Turn it back on with `ontoreview telemetry on`.")


@telemetry_app.command("on")
def telemetry_on() -> None:
    """Turn telemetry back on (the default)."""
    from . import telemetry
    telemetry.set_enabled(True)
    reason = telemetry.disabled_reason()
    console.print("[green]✓[/] Telemetry is on." + (f" [yellow]Still off here: {escape(reason)}.[/]" if reason else ""))


@telemetry_app.command("enable")
def telemetry_enable() -> None:
    """Send the optional details again (the default)."""
    from . import telemetry
    telemetry.set_details(True)
    console.print("[green]✓[/] Optional telemetry details are on.")


@telemetry_app.command("show")
def telemetry_show(last: bool = typer.Option(False, "--last", help="Also print the last events sent from here.")) -> None:
    """Every property that can be sent, whether it is mandatory or optional, and why."""
    import json as _json

    from . import telemetry
    for line in telemetry.status_lines():
        console.print(escape(line))
    details = telemetry.details_enabled()
    t = Table(title="What is sent", show_lines=False)
    for col in ("Property", "Tier", "Event", "Example", "Why"):
        t.add_column(col, overflow="fold")
    for p in telemetry.SPEC:
        tier = "mandatory" if p.tier == "mandatory" else ("optional (on)" if details else "optional (off)")
        t.add_row(escape(p.name), tier, p.events, escape(p.example), escape(p.purpose))
    console.print(t)
    console.print("Never sent: " + "; ".join(telemetry.NEVER_SENT) + ".")
    if last:
        console.print_json(_json.dumps(telemetry.last_events()))


def run() -> None:
    """Console entry point: ``app`` with one anonymous ``run_completed`` event per command (see telemetry.py)."""
    from . import telemetry

    argv = sys.argv[1:]
    command = telemetry.cli_command(argv)
    if command is None or command == "ui" or command.startswith("telemetry") or not telemetry.enabled():
        app()       # help/version, the app (it sends its own session event), telemetry settings, or switched off
        return
    notice = telemetry.first_run_notice()
    if notice:
        err.print(f"[dim]{escape(notice)}[/]")
    with telemetry.run(command, surface="ontoreview", flags=telemetry.cli_flags(argv)):
        app()
