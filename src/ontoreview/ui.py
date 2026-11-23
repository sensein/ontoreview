"""``ontoreview-ui``: a local web UI (NiceGUI) to configure and run builds, exports and checks.

    pip install "ontoreview[ui]"
    ontoreview-ui                     # opens http://127.0.0.1:8765 in your browser

Runs on this machine only (bound to 127.0.0.1 by default); paths are local paths.
Pages: Build, Run history, Settings, About; a sidebar shows whether ROBOT and OOPS! are available.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import sys
import time
import uuid
import webbrowser
from dataclasses import asdict, fields
from datetime import datetime
from html import escape as html_escape
from pathlib import Path

from rdflib import URIRef

from . import __version__, telemetry
from .ui_core import (
    MAX_UPLOAD_BYTES,
    RUN_FOLDER_TASKS,
    TASKS,
    Prefs,
    Settings,
    add_deploy,
    browse,
    change_counts,
    clear_history,
    deploys_for,
    describe_source,
    existing_output,
    load_reviews,
    save_reviews,
    export_output,
    forget_run,
    issues_text,
    load_history,
    oops_status,
    open_in_file_manager,
    record_run,
    robot_status,
    run_config_rows,
    run_name,
    run_task,
    system_info,
    task_kind,
    upload_files,
    upload_source,
    upload_target,
    when_text,
)

ASSETS = Path(__file__).parent / "ui_assets"
REPO = "https://github.com/CAIRNepal/ontoreview"
FORMATS = [  # id, name, description, tag
    ("site", "Website", "Deploy as your ontology's docs site (GitHub Pages, w3id, any web server)", "index.html"),
    ("single", "Single HTML file", "One portable file to share or attach", ".html"),
    ("markdown", "Markdown", "Editable text, good for Git repos, MkDocs or Docusaurus", ".md"),
    ("myst", "MyST / Sphinx", "Pages for a Sphinx docs project you extend and build", "MyST"),
    ("check", "Quality check only", "Run the checks, ROBOT, the reasoner, IRI checks, OntoCheck, cross-domain "
     "interoperability and OOPS! without docs", "report"),
    ("interop", "Interoperability check only", "Cross-domain and scientific interoperability against reference "
     "ontologies you upload, name on OLS/BioPortal, or that are found there; nothing else", "report"),
    ("diff", "Compare versions", "What changed since a previous release of this ontology", "changes.md"),
]
RECOMMENDED = "site"
INCLUDES = {
    "site": "Includes: every term, search, class diagram, quality report (built-in checks, ROBOT, reasoner consistency, IRI checks, OntoCheck metrics, "
            "cross-domain interoperability, OOPS!), "
            "changelog, downloads (TTL, OWL, JSON-LD), citation, llms.txt, and standalone.html (all in one file)",
    "single": "Includes: the same pages and quality report as the website, in one file; no separate downloads",
    "markdown": "Includes: one page per term type; no quality checks or diagram",
    "myst": "Includes: Markdown pages with MyST cross-references; no quality checks or diagram",
    "check": "Includes: built-in checks, ROBOT, reasoner, IRI, OntoCheck and OOPS! results as JSON; no documentation",
    "interop": "Includes: CDI (Align, Gen), SI (covered scientific domains, per-domain scores, domain of each "
               "reference ontology) as JSON; references and options in Settings › Quality checks",
    "diff": "Includes: added, removed and modified terms with the exact statements that changed, as Markdown "
            "and JSON. To put a changelog inside the website instead, set Previous version in Settings › Documentation",
}
OOPS_CHOICES = {"auto": "Alongside ROBOT (default)", "on": "Full catalogue, always", "off": "Off"}
REASONER_CHOICES = {"hermit": "HermiT (OWL 2 DL)", "elk": "ELK (fast, OWL 2 EL)", "off": "Off"}

# ---------------------------------------------------------------------------- drag and drop
# The page uploads dropped files to this endpoint. The token is embedded in the page, so other
# web sites open in the same browser cannot write files through it.
UPLOAD_TOKEN = secrets.token_urlsafe(24)
UPLOAD_URL = "/_ontoreview/upload"
STATIC_URL = "/_ontoreview/static"


def register_upload_route(app) -> None:
    paths = {getattr(r, "path", None) for r in app.router.routes}
    if not any(str(p or "").startswith(STATIC_URL) for p in paths):
        app.add_static_files(STATIC_URL, ASSETS)
    if UPLOAD_URL in paths:
        return
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _upload(request):
        from urllib.parse import unquote

        if not secrets.compare_digest(request.headers.get("x-upload-token", ""), UPLOAD_TOKEN):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        target = upload_target(request.query_params.get("batch", ""),
                               unquote(request.headers.get("x-path", "")))
        if target is None:
            return JSONResponse({"error": "file type or path not accepted"}, status_code=400)
        if int(request.headers.get("content-length") or 0) > MAX_UPLOAD_BYTES:
            return JSONResponse({"error": "file too large"}, status_code=413)
        target.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        with open(target, "wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    fh.close()
                    target.unlink(missing_ok=True)
                    return JSONResponse({"error": "file too large"}, status_code=413)
                fh.write(chunk)
        return JSONResponse({"ok": True, "size": size})

    # a plain Starlette route, ahead of NiceGUI's catch-all routes
    app.router.routes.insert(0, Route(UPLOAD_URL, _upload, methods=["POST"]))


DROP_JS = r"""
<script>
(() => {
  const TOKEN = "%TOKEN%", URL_ = "%URL%";
  const OK = /\.(ttl|owl|rdf|jsonld|json|nt|n3|trig|nq|ofn|omn|ya?ml|csv|tsv|xlsx|toml|md|css|html)$/i;
  // drop zones: elements with class ob-dropzone and data-zone="<name>"; a drop outside any zone goes to the first
  const zones = () => Array.from(document.querySelectorAll(".ob-dropzone"));
  const zoneAt = (el) => (el && el.closest && el.closest(".ob-dropzone")) || zones()[0] || null;
  let hover = null;
  const mark = (z) => { zones().forEach((x) => x.classList.toggle("ob-drag", x === z)); hover = z; };
  const hasFiles = (e) => !!e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
  let depth = 0;
  window.addEventListener("dragenter", (e) => { if (hasFiles(e)) { depth++; mark(zoneAt(e.target)); } });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) mark(null); });
  window.addEventListener("dragover", (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; mark(zoneAt(e.target)); } });
  const fileOf = (entry) => new Promise((res, rej) => entry.file(res, rej));
  const readAll = async (dir) => {
    const reader = dir.createReader(), out = [];
    for (;;) { const batch = await new Promise((res, rej) => reader.readEntries(res, rej)); if (!batch.length) return out; out.push(...batch); }
  };
  async function walk(entry, prefix, out) {
    if (entry.name.startsWith(".")) return;
    if (entry.isFile) { out.push([prefix + entry.name, await fileOf(entry)]); return; }
    for (const child of await readAll(entry)) await walk(child, prefix + entry.name + "/", out);
  }
  window.addEventListener("drop", async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault(); depth = 0;
    const target = zoneAt(e.target); mark(null);
    const zone = target ? target.dataset.zone : null;
    if (!zone) return;
    // collect entries synchronously: the DataTransfer is emptied after the first await
    const entries = Array.from(e.dataTransfer.items || []).map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
    const plain = Array.from(e.dataTransfer.files || []);
    const found = [];
    if (entries.length) { for (const en of entries) await walk(en, "", found); }
    else plain.forEach((f) => found.push([f.name, f]));
    const files = found.filter(([p]) => OK.test(p)), skipped = found.length - files.length;
    if (!files.length) { emitEvent("ob_drop_done", { zone, batch: null, ok: 0, failed: 0, skipped }); return; }
    const batch = Array.from(crypto.getRandomValues(new Uint8Array(8)), (b) => b.toString(16).padStart(2, "0")).join("");
    emitEvent("ob_drop_start", { zone, count: files.length });
    let ok = 0, failed = 0;
    for (const [path, file] of files) {
      try {
        const r = await fetch(URL_ + "?batch=" + batch, { method: "POST", body: file,
          headers: { "X-Upload-Token": TOKEN, "X-Path": encodeURIComponent(path), "Content-Type": "application/octet-stream" } });
        r.ok ? ok++ : failed++;
      } catch (err) { failed++; }
    }
    emitEvent("ob_drop_done", { zone, batch, ok, failed, skipped });
  });
})();
</script>
"""

# ---------------------------------------------------------------------------- look
BRAND = Path(__file__).parent / "ui_assets" / "brand"
TAGLINE = "Docs, review & fixes"


def _unique_ids(svg: str, prefix: str) -> str:
    """Prefix every id (and its url(#…) uses) so several inline SVGs on one page do not clash."""
    for i in set(re.findall(r'id="([^"]+)"', svg)):
        svg = svg.replace(f'id="{i}"', f'id="{prefix}-{i}"').replace(f"url(#{i})", f"url(#{prefix}-{i})")
    return svg


def logo_svg(size: int, small: bool = False) -> str:
    """The OntoReview icon from the brand kit (favicon.svg is the simplified small-size version)."""
    svg = (BRAND / ("favicon.svg" if small else "icon.svg")).read_text("utf-8")
    return _unique_ids(svg, f"or-logo-{'s' if small else 'l'}{size}").replace(
        "<svg ", f'<svg width="{size}" height="{size}" aria-hidden="true" ', 1)


def logo_full(width: int, dark: bool = True) -> str:
    """The horizontal logo with the tagline ("Docs, review & fixes"); ``dark`` = white lettering."""
    svg = (BRAND / ("logo-dark.svg" if dark else "logo-light.svg")).read_text("utf-8")
    return _unique_ids(svg, f"or-full-{'d' if dark else 'l'}{width}").replace(
        "<svg ", f'<svg width="{width}" role="img" aria-label="OntoReview: {TAGLINE.replace("&", "&amp;")}" style="height:auto;display:block" ', 1)

NAV = [  # key, path, label, svg path data
    ("build", "/", "Build", '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/>'),
    ("issues", "/issues", "Quality issues", '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/>'),
    ("history", "/history", "Run history", '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/>'),
    ("compare", "/compare", "Compare", '<path d="M8 3v18M16 3v18"/><path d="m4 8 4-4 4 4M12 16l4 4 4-4"/>'),
    ("interop", "/interoperability", "Interoperability", '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="6" r="3"/>'
     '<circle cx="18" cy="18" r="3"/><path d="m8.6 10.6 6.8-3.2M8.6 13.4l6.8 3.2"/>'),
    ("terms", "/terms", "Term database", '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
     '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
    ("settings", "/settings", "Settings", '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/>'
     '<circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>'),
    ("about", "/about", "About", '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
    ("help", "/help", "Help", '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/>'
     '<path d="M12 17h.01"/>'),
]

# Help page: (anchor, title, screenshot(s) in ui_assets/help/ (a name, a tuple of names, or ""), steps, note, links)
# a link target is an app path ("/history"), "settings:<tab>" (general | docs | checks | look) or an https URL
HELP = [
    ("start", "Getting started", "build.png", [
        "Install the app once: <code>pip install \"ontoreview[ui]\"</code> (Python 3.11 or newer).",
        "Start it with <code>ontoreview ui</code>. Your browser opens the Build page; if port 8765 is busy, the "
        "next free port is used and printed in the terminal.",
        "Pick an ontology with <b>File</b>, a folder with <b>Folder</b>, a web address with <b>URL</b>, or drag "
        "files or folders onto the page.",
        "Keep <b>Website</b> selected (recommended for publishing) and press <b>Build docs</b>.",
    ], "Everything runs on your computer except the OOPS! scan, which sends the ontology to a web service, and the "
       "cross-domain interoperability score, which sends labels and IRIs (never the file) to OLS. Turn either off in "
       "Settings › Quality checks.", [("Open Build", "/")]),
    ("results", "Reading the results", "results.png", [
        "While it runs you see each step: parse, built-in checks, ROBOT, logical consistency, IRI checks, OntoCheck, "
        "cross-domain and scientific interoperability, OOPS!, render.",
        "When it finishes, the tiles show how many terms were documented and how many errors and warnings were found.",
        "<b>Quality metrics</b> is a scorecard: OntoCheck's labeling, structure, accessibility and naming metrics, "
        "and the cross-domain and scientific interoperability scores (CDI, Align, Gen, SI, per reference ontology "
        "and per scientific domain). Hover a metric to see what it measures.",
        "<b>Issues</b> lists every problem: filter by errors or warnings. ROBOT, reasoner, OntoCheck and OOPS! findings are merged with "
        "OntoReview's own checks; <b>Affected</b> names the term, or how many elements share the problem.",
        "<b>Logical consistency</b> errors come from an OWL reasoner (HermiT by default): an inconsistent ontology, "
        "or classes that can never have members. Use Protégé's explanations to find the axioms responsible.",
        "<b>Open docs</b> opens the website in a new tab; <b>Export</b> downloads the run (a docs folder as one "
        ".zip); <b>Show in folder</b> opens it in Finder / Explorer.",
        "<b>New build</b> clears the result so the next run starts from an empty panel. Your settings stay, and the "
        "run stays in Run history.",
        "Each docs or check run goes into its own dated folder (<code>docs-YYYYMMDD-HHMMSS</code>) with everything it "
        "needs: the docs or report, <code>standalone.html</code>, the records of what each check was verified "
        "against (<code>cdi.json</code>, <code>si.json</code>, <code>iri-checks.json</code>) and "
        "<code>provenance.ttl</code>. Turn this off under <b>Save to</b> with <b>Each run in its own folder</b>.",
    ], "", [("Open Build", "/")]),
    ("compare", "Comparing two versions", "compare.png", [
        "Open <b>Compare</b> in the sidebar. Add the <b>Previous version</b> (A) and the <b>Current version</b> (B): "
        "drop a file on each box, or use File / URL.",
        "The comparison runs as soon as both are there; press <b>Compare</b> to run it again after editing a file.",
        "Shortcut for the ontology you're documenting: on Build, select <b>Compare versions</b> and pick the "
        "previous release.",
        "The tiles count added, removed and modified terms; the <b>Changes</b> table lists each one, and for "
        "modified terms the exact statements that were added (+) or removed (−).",
        "<b>Open HTML report</b> opens a standalone page you can share, print or attach to a release; "
        "<b>Download HTML</b> saves a copy. changes.md and changes.json are written next to it.",
        "<b>Tip:</b> compare against the published release by giving its URL (for example your w3id or GitHub "
        "release address) as the previous version, so you review exactly what users will see change.",
        "Use the report for release notes: changes.md is ready to paste into a GitHub release or a CHANGELOG.",
    ], "To include a changelog section in the published website instead, set Previous version in "
       "Settings › Documentation and build the Website.",
     [("Open Compare", "/compare"), ("Settings › Documentation", "settings:docs")]),
    ("compare-details", "How the comparison works", ("compare-table.png", "compare-report.png"), [
        "<b>Matching:</b> terms (classes, properties, individuals, SKOS concepts and annotation properties) are "
        "matched by their IRI. A term whose IRI was renamed shows up as one <b>Removed</b> and one <b>Added</b>; "
        "keep IRIs stable and change labels instead.",
        "<b>Added / Removed:</b> the IRI exists only in the current / only in the previous version. In the pizza "
        "example on the right, <i>Calzone</i> was added and <i>spicy_thing</i> removed.",
        "<b>Modified:</b> any statement <i>about</i> the term changed: labels, definitions, comments, "
        "superclasses, restrictions and equivalent classes (shown in Manchester syntax), domains and ranges, "
        "characteristics, deprecation and so on. Each changed statement is listed with + (now present) or − (gone): "
        "for <i>Food</i>, the old definition is − and the new one +.",
        "A change is listed under the term it describes: if <i>Margherita</i> gets a new superclass, it appears "
        "under Margherita, not under the superclass.",
        "<b>Ontology metadata</b> (title, version, license, imports, authors…) is compared too and counted as "
        "Modified; the versions in the heading come from owl:versionInfo or owl:versionIRI.",
        "<b>Asserted statements only:</b> no reasoner runs, so inferred superclasses don't create changes; "
        "formatting, statement order and prefixes never do either.",
        "<b>Formats:</b> the two versions can use different syntaxes (e.g. Turtle against RDF/XML) and either "
        "can be a URL. LinkML schemas are compared after conversion to OWL.",
        "<b>Outputs:</b> <code>changes.html</code> (a standalone report), <code>changes.md</code> (Added, "
        "Removed and Modified sections) and <code>changes.json</code> (the same data for scripts). In CI, "
        "<code>ontoreview diff OLD NEW --format html|markdown|json -o …</code> produces the same reports.",
    ], "Compare versions works on one ontology at a time; for a folder, compare each module separately.",
     [("Open Compare", "/compare"), ("Report an issue", REPO + "/issues/new/choose")]),
    ("folder", "Documenting a folder of ontologies", "folder.png", [
        "Choose <b>Folder</b> (or drop a folder). Every ontology inside, including sub-folders, is documented.",
        "Each one gets its own sub-folder in the output, mirroring your folder, plus an index page that links them.",
        "One broken file doesn't stop the rest: it is listed with its error in the <b>Ontologies</b> table.",
    ], "Competency questions and the previous version apply to one ontology; for folders, put them in an "
       "ontoreview.toml inside that ontology's sub-folder.", [("Open Build", "/")]),
    ("terms", "Term database and IRI checks", "", [
        "Every build checks IRIs: malformed IRIs, the ontology header and version IRI, whether the ontology IRI "
        "returns RDF, and whether reused classes and properties (e.g. prov:Entity) exist in their vocabulary.",
        "Terms are looked up in a SQLite database first: 10 W3C vocabularies ship with OntoReview, and everything "
        "found online (OLS, BioPortal, direct downloads) is saved, so the next run is fast and works offline.",
        "<b>Term database</b> shows it: <b>Search</b> by IRI or label, <b>Ontologies, vocabularies &amp; schemas</b> lists what is stored by name (click one for its IRI, release, source and checksums), "
        "<b>Add ontology</b> indexes a vocabulary from a URL or a file (or drop files), and <b>Runs</b> lists every "
        "IRI check with each term's result and where it was found.",
        "Terms nobody could confirm are <i>unverified</i>, not wrong. Add their vocabulary on the Term database page "
        "to verify them next time.",
        "Every result records the vocabulary release it was checked against. Stored vocabularies older than 30 days "
        "are fetched again automatically when online; use <b>Refresh</b> on the Term database page to do it now.",
    ], "Only external term IRIs are sent to OLS or BioPortal, never your ontology. Turn network lookups off in "
       "Settings › Quality checks to use the SQLite database only.",
     [("Open Term database", "/terms"), ("IRI settings", "settings:checks")]),
    ("cdi", "Cross-domain interoperability", ("cdi-settings.png", "cdi-results.png"), [
        "<b>What it measures:</b> whether the ontology can serve beyond its own domain. <b>Align</b> is how well its "
        "classes and properties map to ontologies from other domains; <b>Gen</b> is how general and domain-neutral "
        "its class definitions are; <b>CDI</b> combines both and stays low when either is low. CDI ≥ 0.5 counts as "
        "interoperable.",
        "<b>Align:</b> each class or property gets the strength of its best correspondence: shared IRIs, "
        "<code>owl:equivalentClass</code> / <code>rdfs:subClassOf</code> axioms, SSSOM mappings, exact label and "
        "synonym matches, OntoAligner matches, and matches inherited from superclasses (weaker per step). "
        "Subclass-type matches count 0.8, matches below 0.5 don't count.",
        "<b>Gen:</b> a language model rates each class definition from “broad, abstract statement” to “highly "
        "specific, with measurable details”. Classes without a definition count as 0, so missing definitions "
        "lower Gen.",
        "<b>Reference ontologies</b> (Settings › Quality checks, one per line): <code>ols</code> or "
        "<code>bioportal</code> find ontologies with matching terms and keep the top 10; <code>ols:envo,chebi</code> "
        "or <code>bioportal:NCIT</code> use those; files and URLs can be ontologies or SSSOM <code>.tsv</code> "
        "mappings; other services as <code>ols@https://…/api</code> or <code>ontoportal@https://…</code>. Drop "
        "several files on the drop area at once.",
        "<b>Own domain(s)</b> leave out discovered ontologies from your own field, so only cross-domain links count.",
        "<b>Scientific interoperability (SI)</b> counts in how many scientific domains (the 41 OECD fields of science "
        "besides the ontology's own) it is interoperable. It reuses this run: the same reference ontologies (uploaded, "
        "named on OLS/BioPortal, or found there) and correspondences. Each reference ontology gets a domain from "
        "repository metadata, else from the language model reading its title and description, or from your domain "
        "map; then CDI is computed per domain, and a domain counts when it reaches θ_s (0.3). Upper-level ontologies "
        "(BFO, DOLCE, …) are ignored, so SI counts links to scientific fields. Gen caps every domain's CDI, so vague "
        "or missing definitions limit SI too. Set your own domain in Settings if the detected one is wrong.",
        "<b>Term database first:</b> every vocabulary stored on the Term database page (the bundled W3C ones and "
        "everything you or the IRI checks added) is matched first, offline. Details of OLS and BioPortal ontologies "
        "(title, domain, release) are read from the database before asking the service, and saved when fetched. "
        "Reference ontologies you provide are added to the database, so it grows with every run.",
        "<b>What it was checked against:</b> each reference's release is recorded: version IRI or version when the "
        "source gives one, otherwise the release/load date, the file's SHA-256 or a fingerprint of the repository's "
        "answer (shown as “version not reported”). Every run is kept on the Term database page under <b>Runs</b>, "
        "and the docs list the releases and write them to cdi.json and provenance.ttl.",
        "<b>OntoAligner</b> (SBERT by default) adds automatic matches for file and URL references. Its embedding "
        "model and the generality model are downloaded automatically on first use (about 90 MB and 1.6 GB) and "
        "then run on this computer.",
        "<b>Keys (optional):</b> OLS needs none. BioPortal and other OntoPortal services answer only with an API "
        "key, and your own key avoids shared rate limits. A Hugging Face token speeds up model downloads. Keys are "
        "never written to reports, ontoreview.toml, the history or the command line shown in the app.",
        "<b>In the results:</b> the scores, Align per reference ontology, entities with no correspondence and classes "
        "with very specific definitions (both as Info issues: what to map or reword to raise the score). The docs "
        "folder gets <code>cdi.json</code> with every correspondence.",
    ], "Needs pip install \"ontoreview[cdi]\" for the language models and OntoAligner; without it only Align is "
       "scored and the review says why. Turn the score off in Settings › Quality checks or with --no-cdi.",
     [("Cross-domain settings", "settings:checks"), ("Open Build", "/")]),
    ("publish", "Publishing the website", "", [
        "The output folder (by default <code>docs</code> next to your ontology) is a complete static website: "
        "copy it to any web server.",
        "<b>GitHub Pages:</b> commit the folder, then in the repository go to Settings › Pages and serve from the "
        "<code>docs</code> folder, or run <code>ontoreview init</code> to add a workflow that rebuilds the site "
        "on every push.",
        "Set <b>Public URL</b> in Settings › Documentation so links, search engines and llms.txt use the final address.",
        "For permanent identifiers, the output includes ready-made <code>.htaccess</code> files for w3id.org.",
    ], "", [("Settings › Documentation (Public URL)", "settings:docs"), ("GitHub Pages documentation", "https://docs.github.com/en/pages"), ("w3id.org permanent identifiers", "https://w3id.org")]),
    ("config", "Project config (ontoreview.toml)", "config.png", [
        "<b>Why save it?</b> The file keeps the build settings next to your ontology, so the command line, CI and "
        "teammates produce exactly the same documentation.",
        "<b>Settings or ontoreview.toml?</b> Most options (layout, languages, public URL, competency questions, "
        "ROBOT and OOPS!) can be set in both. <b>Settings</b> are your personal defaults for every build in this "
        "app, stored on this computer. <b>ontoreview.toml</b> belongs to one project and travels with it. When "
        "both set an option, ontoreview.toml wins.",
        "<b>Project config › New from template</b> opens a commented config in the editor; <b>Edit ontoreview.toml</b> "
        "opens the existing one.",
        "<b>Check</b> validates the file; <b>Save and use for this build</b> writes it and applies it here.",
        "<b>Save current settings</b> turns what you chose in Settings and on the Build page into an "
        "ontoreview.toml, which is the quickest way to share your setup. <b>Open another config…</b> loads any "
        "ontoreview.toml.",
    ], "In CI, <code>ontoreview build</code> and <code>ontoreview check</code> find ontoreview.toml automatically.", [("Build › Project config", "/"), ("Settings", "settings:general")]),
    ("history", "Run history: re-run, change, export", ("history.png", "history-config.png"), [
        "Every build and check is listed with its status, issues and time. Search by ontology or output path, "
        "filter documentation vs. checks, and hide runs whose output was deleted.",
        "<b>Click a run</b> (or its settings icon) to see the configuration it ran with (task, ontology, output, "
        "layout, languages, every check and its options, including the reference ontologies) and the equivalent "
        "command line.",
        "<b>Run again</b> runs it now with exactly that configuration, into a new folder; the earlier output is kept.",
        "<b>Edit and run</b> loads that configuration into Build: change what you need (another reference "
        "ontology, a different own domain, a check turned off) and press Build docs or Run checks. The modified "
        "run is recorded as a new entry, so both configurations stay side by side.",
        "<b>Export</b> downloads the run's output: a docs or check folder as one .zip (docs, standalone.html, "
        "reports, cdi.json, si.json, provenance.ttl), a single file as it is. The row's download icon does the same.",
        "The other row buttons open the output, show it in its folder, or remove the entry (files are kept). API keys "
        "are never stored in the history, so re-runs use the keys currently set in Settings.",
    ], "", [("Open Run history", "/history")]),
    ("fixes", "Fix first, then document", "fixes-ai.png", [
        "After <b>Build docs</b>, OntoReview checks the ontology and opens the <b>Quality issues</b> page before any "
        "docs are generated (also from <b>Review fixes</b> on a result). The original file is <b>never changed</b>: applied fixes go to a new file "
        "(<code>a-v1.ttl</code>, then <code>a-v2.ttl</code> …), and the docs are built from it.",
        "<b>Required metadata:</b> title, description, license and creators. The docs are not generated without "
        "them; fill them in (an AI draft can suggest the description). Values in ontoreview.toml [metadata] count. "
        "You can leave a review and come back later, even after restarting the app: each <b>Build docs</b> adds "
        "its ontology to the list on the Quality issues page (<i>All reviews</i>), with its status: <i>Waiting</i> "
        "(open issues) or <i>Built</i>. <i>Fix &amp; build</i> opens one; <i>Apply</i> or <i>Skip</i> builds only "
        "that ontology, with the settings it was started with. "
        "The AI button turns amber and pulses while the model works, green when the draft is ready, red if it "
        "failed. "
        "LinkML schemas are checked and fixed too: definitions, titles, domains and ranges go into the YAML copy; "
        "a fix the YAML cannot hold saves the fixed version as OWL (Turtle) generated from the schema. "
        "Open issues stay at the top of the list; accepted or ignored ones move to the end. "
        "<b>Missed reuse</b>: a term you defined that a standard vocabulary already has (found by label or name in "
        "the term database, e.g. your Sensor next to sosa:Sensor) can be linked to it as equivalent, or replaced by "
        "the standard IRI. A shared name is not proof of the same meaning: check its definition first. "
        "The prompts sent to the model are in <code>fixes/ai/prompts.md</code> in the package; set "
        "<code>ONTOREVIEW_PROMPTS</code> to your own copy to change them. "
        "For each creator, the name is looked up in the public ORCID registry (or press the search icon in the ORCID "
        "field): pick the right person to fill in the ORCID, or choose <i>None of these</i>. Nothing is filled in "
        "without your choice.",
        "<b>Suggested fixes</b> are marked by who made them: <b>Rule</b> (exact edits such as trimming spaces, a "
        "label from the term's name, removing a self-reference, resolving a two-class cycle), <b>Your input</b> "
        "(e.g. a version) and <b>AI draft</b> (definitions, refinements; editable). Safe fixes are pre-selected; "
        "open <i>Show change</i> to see the triples.",
        "Each fix is tested on a copy first: if it would cause a new problem, the review says so.",
        "Pick an issue on the left; the centre shows its fixes and the Turtle change, the right side what changes in "
        "the ontology and the docs. <b>Accept fix</b>, or <b>Ignore in future builds</b>.",
        "<b>Apply N fixes &amp; build</b> writes the new file plus a SPARQL patch and a record; <b>Skip and build</b> uses the "
        "original (not possible while required metadata is missing). Fixes you did not apply can be applied later; "
        "that writes another file.",
        "The docs' Provenance section and <code>provenance.ttl</code> list every applied fix: what changed, what made "
        "it (rule, or AI source, model and revision) and when it was accepted. Run history marks fixed versions.",
        "Command line: <code>ontoreview fix list a.ttl</code> and <code>ontoreview fix apply a.ttl --accept-safe "
        "--set license=…</code>.",
        "<b>AI suggestions</b> (on by default): definitions for terms without one, refined definitions, the description, "
        "and ranked domains and ranges with a reason each (only classes of your ontology). They are prepared "
        "automatically and shown for review: edit a definition, pick a suggested class or <b>choose another one "
        "yourself</b>. Nothing is applied until you accept it; what came from AI is marked <b>AI-assisted</b> in the "
        "docs and provenance, your own choices are not.",
        "<b>Where AI runs</b> (Settings › AI &amp; fixes, priority you can reorder): <b>Ollama</b> first if it is "
        "running (its installed models are listed; if the chosen model is missing the closest installed one is used; "
        "<b>Pull a model</b> downloads another), then <b>Hugging Face</b> (an open-source model downloaded once, "
        "with progress on the Quality issues page; default Qwen/Qwen3.5-4B, about 9 GB), then an <b>API key</b> "
        "(OpenAI, Anthropic, OpenRouter, …). Local sources keep the ontology on this computer.",
    ], "Turn the review off in Settings › AI &amp; fixes (required metadata is still asked), or turn AI off there.",
     [("AI & fixes settings", "settings:ai")]),
    ("deploy", "Deploy: GitHub Pages, Docker, any server", "deploy.png", [
        "Every website folder includes a deployment kit: <code>DEPLOY.md</code> (step-by-step), a "
        "<code>Dockerfile</code> and <code>docker-compose.yml</code> (nginx, content negotiation included), "
        "<code>deploy/nginx.conf</code> for nginx without Docker, <code>.htaccess</code> for Apache, "
        "<code>deploy/serve.sh</code> / <code>serve.bat</code> for a local preview, and "
        "<code>.github/workflows/pages.yml</code>, which publishes the folder on GitHub Pages on every push.",
        "<b>Deploy to GitHub Pages from the app:</b> press <b>Deploy</b> on a website result, or the cloud icon / "
        "<b>Deploy</b> of a website run in Run history. Enter the repository (create it on GitHub first; it can be "
        "empty, or let OntoReview create it with a token) and the branch, and press Deploy. The app pushes the "
        "website; GitHub Actions publishes it at "
        "<code>https://&lt;you&gt;.github.io/&lt;repo&gt;/</code> a minute or two later.",
        "Deploying again (a newer build, or the same run after changes) updates the same site and keeps the "
        "repository history; nothing is force-pushed. Each deploy is listed with its link on the run in Run history.",
        "<b>Signing in:</b> add a <b>GitHub token</b> in Settings › General › Publishing, or use your git login "
        "(<code>gh auth login</code>, a credential helper or an SSH address). With a token OntoReview also turns on "
        "Pages and, if allowed, creates the repository.",
        "<b>You control what the token can reach.</b> A fine-grained token with <b>Only select repositories</b> "
        "reaches just the docs repositories you pick (create them on GitHub first); <b>All repositories</b> also "
        "lets OntoReview create new ones. Permissions: Contents, Pages, Workflows (and Administration to create "
        "repositories): read and write. A classic token needs the repo and workflow scopes. <b>Check token</b> in "
        "Settings says whose token it is and what is missing.",
        "<b>Turn on GitHub Pages</b> sets the repository's Pages source to GitHub Actions (with the token, or the "
        "GitHub CLI). Otherwise the result tells you the one setting to change (Settings › Pages › Source: GitHub "
        "Actions). With the token it also lets your branch deploy to the <code>github-pages</code> environment; "
        "if a run fails with “Branch main is not allowed to deploy to github-pages”, add the branch under "
        "Settings › Environments › github-pages › Deployment branches and tags, and re-run it.",
        "<b>Docker:</b> <code>docker compose up -d</code> in the website folder serves it at http://localhost:8080/. "
        "<b>Elsewhere:</b> upload the folder to any static host; see DEPLOY.md.",
    ], "The token is kept on this computer only (like the API keys) and sent to GitHub as a request header; it is "
       "never written to reports, the run history or the repository. A public repository makes the site public.",
     [("Open Run history", "/history"), ("Publishing settings", "settings:general")]),
    ("si", "Scientific interoperability", ("si-settings.png", "si-results.png"), [
        "<b>What it measures:</b> in how many scientific domains, other than the ontology's own, it is interoperable. "
        "Domains are the 41 OECD Fields of Science (Frascati Manual), e.g. 1.2 Computer and information sciences, "
        "1.5 Earth and related environmental sciences, 3.2 Clinical medicine.",
        "<b>How:</b> each reference ontology gets a domain (your domain map, else repository metadata such as OLS "
        "domains, else the language model reading its title and description). For each domain, CDI is computed with "
        "only that domain's reference ontologies; the domain counts as <b>covered</b> when it reaches θ_s (0.3). "
        "<b>SI</b> is the number of covered domains; SI ≥ 1 counts as scientifically interoperable.",
        "<b>Upper-level ontologies</b> (BFO, COB, RO, DOLCE/DUL, GFO, SUMO, gUFO) are ignored, so SI counts links to "
        "scientific fields, not shared foundations. Gen caps every domain: vague or missing class definitions limit "
        "SI however well the ontology is aligned (the review shows this ceiling).",
        "<b>Reference ontologies:</b> by default the cross-domain ones, from the same run (nothing is fetched twice). "
        "Untick <b>Use the cross-domain reference ontologies</b> to give SI its own: type them, browse files, or "
        "<b>Find on OLS or BioPortal</b> by name and click Add (e.g. ols:envo); nothing to upload.",
        "<b>Own scientific domain:</b> detected from the ontology's title and description, or set it; it is never "
        "counted. <b>Domain of a reference ontology:</b> one row per ontology (id and field), a new row appears as "
        "you fill the last; the review lists reference ontologies left without a domain.",
        "<b>Where to see it:</b> the Overview tile and the quality report of the docs (per-domain scores, the domain "
        "of each reference ontology), <code>si.json</code>, and the Interoperability page. Each reference release is "
        "recorded once, with a <b>Used in</b> column (cross-domain, scientific), and in provenance.ttl.",
    ], "SI needs the generality model (pip install 'ontoreview[cdi]'); without it the review says so. Repositories "
       "receive labels and IRIs, never the ontology file.",
     [("Settings › Quality checks", "settings:checks"), ("Open Interoperability", "/interoperability")]),
    ("interop", "Interoperability page", ("interop.png", "interop-results.png"), [
        "Checks only cross-domain (CDI) and scientific (SI) interoperability of one ontology, without building docs; "
        "like Compare, it runs in place and in the background.",
        "Choose the ontology (drop, File or URL). Add reference ontologies: drop or browse files and SSSOM mappings, "
        "<b>Find on OLS or BioPortal</b> by name, or keep <code>ols</code> / <code>bioportal</code> to let OntoReview "
        "discover the ontologies with matching terms (top 10).",
        "Set SI's options (own references, own domain, θ_s, domain of a reference ontology) and press <b>Run checks</b>.",
        "The result shows the CDI and SI tiles and every metric. <b>Open report (JSON)</b>, <b>Export</b> (the run "
        "folder as .zip, with cdi.json, si.json and provenance.ttl), <b>Show in folder</b>, <b>New check</b>. The run "
        "is kept in Run history, where it can be re-run as is or changed.",
        "The same check is <b>Interoperability check only</b> on Build, and <code>ontoreview check my.ttl "
        "--interop-only</code> on the command line.",
    ], "BioPortal search needs your BioPortal API key (Settings › Quality checks); OLS needs none.",
     [("Open Interoperability", "/interoperability")]),
    ("settings", "Settings", "settings.png", [
        "<b>General:</b> default output folder and format, opening docs when a build finishes, and history.",
        "<b>Documentation:</b> layout, languages, public URL, imports, individuals, reasoning, competency "
        "questions and the previous version (for the changelog).",
        "<b>Quality checks:</b> run ROBOT in Docker or with a local <code>robot</code>, the reasoner for the "
        "logical consistency check (HermiT, ELK or off), OntoCheck (on/off, network checks, class search term), "
        "cross-domain interoperability (references, domains, OntoAligner, optional API keys and Hugging Face "
        "token), the OOPS! service, and when a "
        "check run counts as failed.",
        "<b>Appearance:</b> light, dark or match the system, and a compact layout.",
    ], "These are defaults for you on this computer. To fix settings for one project, and share them with the "
       "command line, CI and teammates, use Project config › Save current settings to write an ontoreview.toml; "
       "its values override these.", [("General", "settings:general"), ("Documentation", "settings:docs"), ("Quality checks", "settings:checks"), ("Appearance", "settings:look")]),
    ("trouble", "Troubleshooting", "", [
        "<b>ROBOT · Docker not running:</b> start Docker Desktop, or choose “Local robot command” in Settings › "
        "Quality checks. The first run downloads the ROBOT image, which can take a minute.",
        "<b>OOPS! · unreachable:</b> the web service may be down or you are offline; builds still finish, the "
        "OOPS! section reports the problem. Set OOPS! to Off for private ontologies.",
        "<b>Port already in use:</b> start with <code>ontoreview ui --port 8800</code>, or just run it again "
        "without --port to use the next free port.",
        "<b>Dropped files:</b> browsers don't share real paths, so dropped items are copied to "
        "<code>~/.config/ontoreview/uploads/</code>. Use File / Folder to work on the originals.",
        "<b>Reporting a bug:</b> About › System info › Copy for bug report, then open an issue on GitHub.",
    ], "", [("Settings › Quality checks", "settings:checks"), ("About › System info", "/about"), ("Report an issue", REPO + "/issues/new/choose")]),
    ("telemetry", "Telemetry and privacy", "", [
        "OntoReview sends <b>anonymous usage statistics</b> to PostHog (US cloud). They tell us how many people "
        "actually use OntoReview (PyPI only counts downloads, including mirrors and CI caches), in which countries, "
        "and which commands, app tasks and quality checks they run, and whether those work.",
        "<b>Mandatory (always sent):</b> a random install id made on first run (not linked to you or your computer), "
        "country, how OntoReview is used (the app, a terminal, or headless scripts and CI), the command or task, "
        "which quality checks ran, whether it succeeded (and the error type, never the message), how long it took "
        "(as a range), and the OntoReview, Python and OS versions.",
        "<b>Why some of it is mandatory:</b> OntoReview is free, open-source research software. Funders and "
        "institutions ask how many people use it and where; that keeps the project funded and maintained. Knowing "
        "which checks people run, and which fail on which platforms, tells us what to fix and improve first. If "
        "only people who opt in were counted, these numbers would be far too low to be useful. The mandatory part "
        "is kept to the minimum needed for that, and none of it identifies you. Mandatory means it is part of "
        "every event; you can still turn telemetry off completely.",
        "<b>Optional (on by default, switch off any time):</b> why a check did not run, ROBOT and reasoner setup, "
        "finding counts, ontology format and size (as ranges such as 100-1k classes), documentation options, the AI "
        "provider and model family, CLI option names (never their values) and which pages of the app you open.",
        "<b>Never sent:</b> your ontologies, IRIs, labels, file paths, URLs, competency questions, AI prompts or "
        "answers, API keys or tokens, names, e-mail addresses, ORCID, git remotes. The IP address is used by PostHog "
        "only to look up the country and is then discarded; no city or location is kept.",
        "<b>Where it comes from:</b> the app, the <code>ontoreview</code> command, and the Python API "
        "(<code>import ontoreview</code>: one event per process with the functions called, never in CI or test "
        "suites). Each user on a computer counts once: the id is a one-way hash of the computer's own id and the "
        "user account, which never leave the computer.",
        "<b>CI (GitHub Actions and others):</b> the CI service, whether the workflow is the one "
        "<code>ontoreview init</code> writes, and what triggered it (push, pull request, schedule). A repository "
        "counts once through a one-way hash of its numeric repository id; repository names and URLs are never "
        "sent. CI runs are sampled (1 in 10).",
        "<b>Turn off the optional details:</b> Settings › Telemetry (switch off <i>Share optional details</i>), "
        "<code>ontoreview telemetry disable</code>, or <code>ONTOREVIEW_TELEMETRY_DETAILS=0</code>.",
        "<b>Turn off everything:</b> Settings › Telemetry (switch off <i>Send usage statistics</i>), "
        "<code>ontoreview telemetry off</code>, or <code>DO_NOT_TRACK=1</code> in the environment (handy for CI).",
        "<b>See what is sent:</b> Settings › Telemetry lists every property and the last events sent from your "
        "computer; <code>ontoreview telemetry show --last</code> prints the same.",
    ], "Statistics are sent in the background and never slow down or stop a run; without a network nothing is "
       "sent; events made offline wait on your computer and are sent later.",
     [("Telemetry settings", "settings:telemetry")]),
]


def _icon(paths: str, size: int = 18) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths}</svg>')


CSS = """
@keyframes or-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes or-spin { to { transform: rotate(360deg); } }
.or-ai-working { color: #b54708 !important; border-color: #f79009 !important; background: #fffaeb !important; }
.or-ai-working .q-icon { animation: or-pulse 1s ease-in-out infinite; }
.or-ai-ok { color: #067647 !important; border-color: #17b26a !important; background: #ecfdf3 !important; }
.or-ai-err { color: #b42318 !important; border-color: #f04438 !important; background: #fef3f2 !important; }
@media (prefers-reduced-motion: reduce) { .or-ai-working .q-icon { animation: none; } }
:root { --or-bg:#F4F6F8; --or-card:#fff; --or-line:#E2E7EC; --or-line-2:#F2F4F7; --or-ink:#101828; --or-ink-2:#344054;
  --or-muted:#5B6675; --or-input:#D0D7DE; --or-primary:#2F4FD8; --or-primary-soft:#EEF1FD; --or-side:#0F1724;
  --or-side-2:#1E293B; --or-side-ink:#C9D1DB; --or-side-muted:#8A97A8; --or-ok-bg:#ECFDF3; --or-ok:#067647;
  --or-err-bg:#FEF3F2; --or-err:#B42318; --or-warn-bg:#FFFAEB; --or-warn:#93370D; --or-info-bg:#EFF8FF; --or-info:#175CD3;
  --or-mono: ui-monospace, "SF Mono", Menlo, Consolas, "JetBrains Mono", monospace; }
body.body--dark { --or-bg:#0B111A; --or-card:#121A26; --or-line:#253041; --or-line-2:#1B2533; --or-ink:#E6EAF0;
  --or-ink-2:#C9D1DB; --or-muted:#98A2B3; --or-input:#344054; --or-primary-soft:#1C2752; --or-side:#070B12;
  --or-side-2:#1A2230; --or-ok-bg:#0B2A1C; --or-ok:#6CE9A6; --or-err-bg:#3A1410; --or-err:#FDA29B;
  --or-warn-bg:#3A2A0A; --or-warn:#FEC84B; --or-info-bg:#0B2547; --or-info:#84CAFF; }
body { background: var(--or-bg); color: var(--or-ink); font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
.q-page-container, .nicegui-content { background: var(--or-bg); }
.nicegui-content { padding: 0 !important; }
.or-mono { font-family: var(--or-mono); }
.or-muted { color: var(--or-muted); }
.or-card { background: var(--or-card) !important; border: 1px solid var(--or-line); border-radius: 12px !important; box-shadow: none !important; }
.or-pagehead { background: var(--or-card); border-bottom: 1px solid var(--or-line); padding: 18px 32px; width: 100%; }
.or-pagehead h1 { margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -.4px; line-height: 1.3; }
.or-pagehead p { margin: 4px 0 0; font-size: 13px; color: var(--or-muted); }
.or-body { padding: 24px 32px 32px; width: 100%; }
.or-compact .or-body { padding: 14px 18px 20px; } .or-compact .or-sec { padding: 12px 14px !important; }
.or-sec { padding: 18px 20px; width: 100%; }
.or-h2 { font-size: 15px; font-weight: 700; margin: 0; }
.or-step { width: 22px; height: 22px; border-radius: 50%; background: var(--or-primary-soft); color: var(--or-primary);
  font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; }
.or-hint { font-size: 12.5px; color: var(--or-muted); }
.or-label { font-weight: 600; font-size: 13.5px; }
/* sidebar */
.or-side { background: var(--or-side) !important; color: var(--or-side-ink); }
.or-side .q-drawer__content, .or-side.q-drawer__content { display: flex; flex-direction: column; padding: 22px 14px; }
.or-nav { display: flex; align-items: center; gap: 12px; padding: 11px 12px; border-radius: 8px; color: var(--or-side-ink) !important;
  font-size: 14px; text-decoration: none !important; min-height: 44px; }
.or-nav:hover { background: rgba(255,255,255,.05); }
.or-nav.or-active { background: var(--or-side-2); color: #fff !important; font-weight: 600; }
.or-env { margin-top: auto; width: 100%; padding: 16px 12px 0; border-top: 1px solid var(--or-side-2); font-size: 12px; display: flex; flex-direction: column; gap: 10px; }
.or-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }
.or-dot.ok { background: #32D583; } .or-dot.warn { background: #FDB022; } .or-dot.missing { background: #F97066; } .or-dot.off { background: #667085; }
/* badges */
.or-badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.or-badge.ok { background: var(--or-ok-bg); color: var(--or-ok); } .or-badge.err { background: var(--or-err-bg); color: var(--or-err); }
.or-badge.warn { background: var(--or-warn-bg); color: var(--or-warn); } .or-badge.info { background: var(--or-info-bg); color: var(--or-info); }
.or-badge.off { background: var(--or-line-2); color: var(--or-muted); }
/* option cards (format, ROBOT mode, theme) */
.or-opt { display: flex; align-items: center; gap: 12px; width: 100%; padding: 11px 14px; border: 1px solid var(--or-line);
  border-radius: 10px; background: var(--or-card); cursor: pointer; text-align: left; color: var(--or-ink); font: inherit; }
.or-opt:hover { border-color: var(--or-input); }
.or-opt.or-sel { border: 1.5px solid var(--or-primary); background: var(--or-primary-soft); }
.or-opt:focus-visible, .or-nav:focus-visible { outline: 2px solid var(--or-primary); outline-offset: 2px; }
.or-radio { width: 16px; height: 16px; border-radius: 50%; border: 1.5px solid var(--or-input); flex: none; }
.or-sel .or-radio { border: 5px solid var(--or-primary); }
.or-tag { font-family: var(--or-mono); font-size: 11.5px; color: var(--or-muted); background: var(--or-line-2); padding: 2px 8px; border-radius: 6px; }
/* tiles */
.or-tile { flex: 1 1 130px; border: 1px solid var(--or-line); border-radius: 10px; padding: 12px 14px; }
.or-tile .k { font-size: 12px; color: var(--or-muted); } .or-tile .v { font-size: 24px; font-weight: 700; margin-top: 2px; }
.or-tile.err { background: var(--or-err-bg); border-color: transparent; } .or-tile.err .v, .or-tile.err .k { color: var(--or-err); }
.or-tile.warn { background: var(--or-warn-bg); border-color: transparent; } .or-tile.warn .v, .or-tile.warn .k { color: var(--or-warn); }
.or-tile .v.small { font-size: 14px; padding-top: 8px; }
.or-tile.ok-tile { background: var(--or-ok-bg); border-color: transparent; } .or-tile.ok-tile .v, .or-tile.ok-tile .k { color: var(--or-ok); }
/* segmented filter */
.or-seg { display: inline-flex; background: var(--or-line-2); border-radius: 8px; padding: 3px; gap: 2px; }
.or-seg button { min-height: 32px; padding: 0 12px; border: 0; background: transparent; border-radius: 6px; font-size: 12.5px;
  font-weight: 500; color: var(--or-ink-2); cursor: pointer; }
.or-seg button[aria-selected="true"] { background: var(--or-card); color: var(--or-ink); font-weight: 600; box-shadow: 0 1px 2px rgba(16,24,40,.08); }
.or-seg button:focus-visible { outline: 2px solid var(--or-primary); outline-offset: 1px; }
/* tables */
.or-table { width: 100%; background: transparent !important; color: var(--or-ink) !important; }
.or-table thead tr th { font-size: 11.5px; text-transform: uppercase; letter-spacing: .5px; color: var(--or-muted); font-weight: 600; background: var(--or-line-2); }
.or-clickable-rows tbody tr { cursor: pointer; }
.or-table tbody td { font-size: 13px; border-color: var(--or-line-2) !important; }
.or-cli { font-family: var(--or-mono); font-size: 12px; white-space: pre-wrap; word-break: break-all; background: var(--or-line-2);
  border-radius: 8px; padding: 10px 12px; width: 100%; }
.ob-dropzone { border: 1.5px dashed var(--or-input); border-radius: 10px; padding: 12px; transition: background-color .15s, border-color .15s; }
.ob-dropzone.ob-drag { border-color: var(--or-primary); background: var(--or-primary-soft); }
.or-chip { display: flex; align-items: center; gap: 12px; width: 100%; }
.or-chipicon { width: 36px; height: 36px; border-radius: 8px; background: var(--or-primary-soft); color: var(--or-primary);
  display: flex; align-items: center; justify-content: center; flex: none; }
.or-steps li { display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 13.5px; list-style: none; }
.or-steps .done { color: var(--or-ok); } .or-steps .todo { color: var(--or-muted); }
.or-log { height: 15rem; font-size: 12px; font-family: var(--or-mono); }
.or-hero { background: #0F1724; color: #fff; border-radius: 14px; padding: 32px; }
.or-feature .ic { width: 36px; height: 36px; border-radius: 8px; background: var(--or-primary-soft); color: var(--or-primary);
  display: flex; align-items: center; justify-content: center; }
.or-notice { padding: 10px 12px; background: var(--or-warn-bg); color: var(--or-warn); border-radius: 8px; font-size: 12.5px; }
.or-themeprev { display: block; height: 64px; border-radius: 8px; border: 1px solid var(--or-line); width: 100%; }
@media (prefers-reduced-motion: reduce) { .ob-dropzone { transition: none; } }
/* settings rows: the control column never stretches beyond a comfortable width */
.or-setrow > :not(:first-child) { flex: 0 1 560px !important; max-width: 560px; }
.or-setrow > .q-checkbox { flex: 0 0 auto !important; }
.q-tab-panels, .q-tab-panel { background: transparent !important; }
.or-helplist { margin: 0; padding-left: 1.2rem; display: flex; flex-direction: column; gap: 8px; font-size: 14px; line-height: 1.55; }
.or-helplist code, .or-hint code { font-family: var(--or-mono); font-size: 12.5px; background: var(--or-line-2); padding: 1px 5px; border-radius: 4px; }
.or-shot { border: 1px solid var(--or-line); border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(16,24,40,.08); }
@media (max-width: 700px) { .or-pagehead, .or-body { padding-left: 16px; padding-right: 16px; } }
"""


class _Session:
    """Run state shared by every page and browser tab of this (single-user, local) app.

    A build or comparison keeps running in a worker thread when you switch pages, reload or open a
    new tab; each view polls this state and redraws when what it shows has changed.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.build: dict = {"last": None, "running": False, "steps": [], "active": None, "done": frozenset(),
                            "folder_pos": "", "filter": "all", "log": [], "env": None, "prior": None}
        self.interop: dict = {"s": None, "last": None, "running": False, "started": 0.0}
        # the Quality issues page: one review per ontology (its fix session, the build waiting for it and the
        # user's decisions); several can wait at once, and each builds only its own ontology
        self.reviews: dict[str, dict] = {}
        self.review_key: str | None = None
        self._saved = ""
        known = {f.name for f in fields(Settings)}
        for r in load_reviews():                   # waiting reviews survive a restart (re-checked when opened)
            try:
                job = Settings(**{k: v for k, v in r["job"].items() if k in known})
            except TypeError:
                continue
            self.reviews[r["key"]] = {"key": r["key"], "session": None, "job": job, "mode": r.get("mode", "prebuild"),
                                      "dec": r.get("dec") or {}, "sel": None, "filter": "all", "show_ignored": False,
                                      "added": r.get("added", 0), "status": r.get("status", "open"),
                                      "finished": r.get("finished", ""), "result": r.get("result", ""),
                                      "open": r.get("open", 0), "keep": r.get("keep") or []}
        self.cmp: dict = {"old": "", "new": "", "output": "", "last": None, "running": False, "filter": "all",
                          "done": None}
        self.verbose = False

    @property
    def fixes(self) -> dict:
        """The review shown on the Quality issues page (an empty one when nothing waits)."""
        return self.reviews.get(self.review_key or "") or {"session": None, "job": None, "mode": "", "dec": {},
                                                           "sel": None, "filter": "all", "show_ignored": False}

    def add_review(self, session, job, mode: str = "prebuild") -> dict:
        """A new review for this ontology (replacing an older one of the same file) and show it."""
        key = str(Path(job.source).expanduser().resolve()) if job is not None else str(session.source)
        entry = {"key": key, "session": session, "job": job, "mode": mode, "dec": {}, "sel": None, "filter": "all",
                 "show_ignored": False, "added": time.time(), "status": "open", "finished": "", "result": "",
                 "open": 0, "keep": []}
        self.reviews[key] = entry
        self.review_key = key
        self.persist()
        return entry

    def drop_review(self, key: str) -> None:
        self.reviews.pop(key, None)
        if self.review_key == key:
            self.review_key = None
        self.persist()

    def finish_review(self, key: str, status: str, result: str = "") -> None:
        """Mark a review built (``built`` from the fixed file, ``skipped`` from the original); it stays listed."""
        e = self.reviews.get(key)
        if e is not None:
            e.update(status=status, result=result, session=None, open=0,
                     finished=time.strftime("%Y-%m-%d %H:%M"))
        if self.review_key == key:
            self.review_key = None
        self.persist()

    def persist(self) -> None:
        """Save the reviews (decisions, AI drafts kept, status) when they changed."""
        rows = []
        for e in self.reviews.values():
            sess = e.get("session")
            if sess is not None:          # AI drafts and own choices are not re-created by a new check: keep them
                e["keep"] = [x.to_dict() for x in sess.suggestions
                             if x.kind == "L" or (x.made_by or {}).get("type") == "user"]
                e["open"] = open_issue_count(e)
            rows.append({k: e.get(k) for k in ("key", "mode", "dec", "added", "status", "finished", "result", "open",
                                               "keep")} | {"job": asdict(e["job"]) if e.get("job") else None})
        text = json.dumps(rows, default=str, sort_keys=True)
        if text != self._saved:
            self._saved = text
            save_reviews(rows)

    def progress(self, msg: str) -> None:
        """Advance the Build progress steps from a log message (called from the worker thread)."""
        st = self.build
        if not st["running"]:
            return
        head = msg.split("]", 1)[0]
        if msg.startswith("[") and "/" in head:
            st["folder_pos"] = f"Ontology {head[1:].replace('/', ' of ')} · {msg.split('] ', 1)[-1]}"
            st["done"], st["active"] = frozenset(), None
        keys = [k for k, _ in st["steps"]]
        for prefix, key in STEP_OF:
            if msg.startswith(prefix) and key in keys:
                st["done"] = st["done"] | frozenset(keys[:keys.index(key)])   # replaced, never mutated
                st["active"] = key


SESSION = _Session()


ORCID_HITS: dict[str, list | None] = {}     # creator name → ORCID candidates (None while looking up)
ORCID_DISMISSED: set[str] = set()            # names whose candidates the user dismissed ("None of these")


def open_issue_total() -> int:
    """Open issues of every review waiting on the Quality issues page, for the sidebar badge."""
    return sum(open_issue_count(fs) for fs in SESSION.reviews.values() if fs.get("status", "open") == "open")


def restore_review(e: dict) -> None:
    """Re-check the ontology of a review saved before a restart and replay the user's decisions."""
    from .fixes import FixError as _FixError
    from .fixes import FixSession
    from .fixes.model import suggestion_from_dict
    job = e["job"]
    ov = {k: v for k, v in job.overrides().items() if k in ("evaluation", "load_imports", "include_individuals",
                                                             "reason", "competency_questions")}
    sess = FixSession(job.source, **ov)
    sess.precheck()
    ids = {x.id for x in sess.suggestions}
    for d in e.get("keep") or []:
        try:
            x = suggestion_from_dict(d)
        except (TypeError, KeyError):
            continue
        if x.id not in ids:
            sess.replace(x)
    for sid, d in list((e.get("dec") or {}).items()):
        if d.get("status") != "accepted":
            continue
        try:
            x = sess.get(sid)
            if x.fields:
                sess.accept(sid, values=d.get("values") or {})
            elif x.kind == "L":
                sess.accept(sid, option=d.get("opt", 0), text=d.get("text") or None)
            else:
                sess.accept(sid, option=d.get("opt", 0))
        except _FixError:
            d["status"] = "open"              # the ontology changed since: decide again
    e["session"] = sess


def open_issue_count(fs: dict) -> int:
    """Open issues of one review (not accepted, not ignored)."""
    sess = fs.get("session")
    if sess is None:
        return int(fs.get("open") or 0) if fs.get("status", "open") == "open" else 0
    ignored = ignored_ids()
    return sum(1 for x in sess.suggestions if x.id not in sess.accepted and x.id not in ignored
               and fs["dec"].get(x.id, {}).get("status") != "ignored")


def ignored_ids() -> set[str]:
    try:
        return {x for x in Prefs.load().fix_ignored.split() if x}
    except Exception:  # noqa: BLE001
        return set()
LOG_LIMIT = 2000


class _ProgressHandler(logging.Handler):
    """Writes ontoreview log records (from worker threads) into :data:`SESSION`."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(levelname)-5s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.levelno >= logging.INFO or SESSION.verbose:
                log = SESSION.build["log"]
                log.append(self.format(record))
                if len(log) > LOG_LIMIT:
                    del log[: len(log) - LOG_LIMIT]
            SESSION.progress(msg)
        except Exception:  # noqa: BLE001
            pass


_HANDLER = _ProgressHandler()


def _install_log_handler() -> logging.Logger:
    lg = logging.getLogger("ontoreview")
    if _HANDLER not in lg.handlers:
        lg.addHandler(_HANDLER)
    if lg.level == logging.NOTSET or lg.level > logging.INFO:
        lg.setLevel(logging.INFO)
    return lg


def _plan(s: Settings) -> list[tuple[str, str]]:
    """Steps shown while a task runs: (key, label)."""
    if s.task == "diff":
        return [("parse", "Parse both versions"), ("render", "Compare and write the report")]
    if s.task == "interop":
        what = " and ".join(x for x, on in (("Cross-domain", s.cdi), ("scientific", s.si)) if on).capitalize()
        return [("parse", "Parse ontology"), ("cdi", f"{what} interoperability"), ("render", "Write report")]
    steps = [("parse", "Parse ontology"), ("checks", "Built-in quality checks")]
    if s.task in ("site", "single", "check"):
        if s.robot != "off":
            steps.append(("robot", "ROBOT report" + (" (local)" if s.robot_path else " (Docker)")))
            if s.reasoner != "off":
                steps.append(("reasoner", "Logical consistency (" + {"hermit": "HermiT", "elk": "ELK"}[s.reasoner] + ")"))
        if s.iri_checks:
            steps.append(("iri", "IRI checks" + ("" if s.iri_network else " (offline)")))
        if s.ontocheck:
            steps.append(("ontocheck", "OntoCheck metrics"))
        if s.cdi or s.si:
            steps.append(("cdi", " and ".join(x for x, on in (("Cross-domain", s.cdi), ("scientific", s.si)) if on)
                          .capitalize() + " interoperability"))
        if s.oops != "off":
            steps.append(("oops", "OOPS! pitfall scan"))
    steps.append(("render", {"site": "Render website", "single": "Render single HTML file", "markdown": "Write Markdown",
                             "myst": "Write MyST files", "check": "Write report"}[s.task]))
    return steps


STEP_OF = [("Parsing ontology", "parse"), ("Parsed ", "checks"), ("Running ROBOT", "robot"),
           ("Checking logical consistency", "reasoner"), ("Checking IRIs", "iri"), ("Running OntoCheck", "ontocheck"),
           ("Scoring cross-domain interoperability", "cdi"),
           ("Running OOPS!", "oops"), ("Rendering", "render"), ("Exporting", "render")]
BADGE_KIND = {"ok": "ok", "warn": "warn", "off": "off", "missing": "err"}


# ---------------------------------------------------------------------------- the app
def build_page() -> None:  # noqa: C901 - the shell and its four pages share state
    from nicegui import app, background_tasks, run, ui

    register_upload_route(app)
    prefs = Prefs.load()
    s = Settings.load()
    prefs.apply(s)
    state = SESSION.build          # shared across pages, reloads and tabs: a run outlives its view
    cmp = SESSION.cmp
    lg = _install_log_handler()
    client = ui.context.client

    ui.colors(primary="#2F4FD8", positive="#067647", negative="#B42318", warning="#B54708")
    ui.add_css(CSS)
    ui.add_body_html(DROP_JS.replace("%TOKEN%", UPLOAD_TOKEN).replace("%URL%", UPLOAD_URL))
    ui.page_title("OntoReview")
    dark = ui.dark_mode({"light": False, "dark": True, "system": None}[prefs.theme])
    if prefs.compact:
        ui.query("body").classes("or-compact")

    # ------------------------------------------------------------------ sidebar
    nav_links: dict = {}
    nav_busy: dict = {}
    with ui.left_drawer(value=True, fixed=True).classes("or-side").props("width=232 breakpoint=900") as drawer:
        with ui.row().classes("items-center no-wrap").style("padding: 0 2px 22px"):
            ui.html(logo_full(214), sanitize=False).mark("brand-logo")
        with ui.element("nav").props('aria-label="Main"').classes("column gap-1 w-full"):
            for key, path, label, icon in NAV:
                with ui.link(target=path).classes("or-nav") as link:
                    ui.html(_icon(icon), sanitize=False)
                    ui.label(label)
                    if key in ("build", "compare"):
                        nav_busy[key] = ui.spinner(size="14px").classes("q-ml-auto").tooltip("Running")
                        nav_busy[key].set_visibility(False)
                    if key == "issues":
                        nav_busy["issues"] = ui.badge("0").props("rounded color=primary").classes("q-ml-auto")
                        nav_busy["issues"].set_visibility(False)
                nav_links[key] = link
        with ui.element("div").classes("or-env"):
            ui.label("Environment").style("font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--or-side-muted)")
            env_robot = ui.row().classes("items-center gap-2 no-wrap")
            env_oops = ui.row().classes("items-center gap-2 no-wrap")
            ui.label(f"v{__version__}").style("color:var(--or-side-muted)")

    def show_env(target, st: dict) -> None:
        target.clear()
        with target:
            ui.element("span").classes(f"or-dot {st['state']}")
            ui.label(st["label"]).tooltip(st.get("detail", ""))

    def env_checking() -> None:
        show_env(env_robot, {"state": "off", "label": "ROBOT · checking…"})
        show_env(env_oops, {"state": "off", "label": "OOPS! · checking…"})

    env_checking()

    async def refresh_env() -> None:
        env_checking()
        rs = await run.io_bound(robot_status, prefs)
        show_env(env_robot, rs)
        if os.environ.get("NICEGUI_USER_SIMULATION"):
            os_ = oops_status(prefs, check=False)
        else:
            os_ = await run.io_bound(oops_status, prefs, True)
        show_env(env_oops, os_)
        state["env"] = (rs, os_)

    ui.timer(0.1, refresh_env, once=True)

    def set_active(key: str) -> None:
        telemetry.note_page(key)
        for k, link in nav_links.items():
            if k == key:
                link.classes(add="or-active")
                link.props('aria-current="page"')
            else:
                link.classes(remove="or-active")
                link.props(remove="aria-current")

    def show_busy() -> None:
        for key, st in (("build", state), ("compare", cmp)):
            if key in nav_busy:
                nav_busy[key].set_visibility(bool(st["running"]))
        n = open_issue_total()
        if "issues" in nav_busy:
            nav_busy["issues"].set_text(str(n))
            nav_busy["issues"].set_visibility(n > 0)

    ui.timer(0.5, show_busy)
    ui.timer(2.0, SESSION.persist)              # save review decisions so they survive a restart

    # ------------------------------------------------------------------ shared helpers
    def page_head(title: str, subtitle: str):
        with ui.row().classes("or-pagehead items-center justify-between gap-4") as head:
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.button(icon="menu", on_click=drawer.toggle).props('flat round dense aria-label="Menu"').classes("lt-md")
                with ui.column().classes("gap-0"):
                    ui.html(f"<h1>{title}</h1>", sanitize=False)
                    ui.html(f"<p>{subtitle}</p>", sanitize=False)
        return head

    def notify(msg: str, kind: str = "info") -> None:
        """Toast on this page, even when called from a task whose view has been replaced."""
        if client.is_deleted:
            return
        with client.layout:
            ui.notify(msg, type=kind, position="bottom-right")

    def reveal(path: str) -> None:
        try:
            open_in_file_manager(path)
        except Exception as e:  # noqa: BLE001
            notify(str(e), "warning")

    def export(path: str) -> None:
        """Download a run's output: a folder as <folder>.zip, a single file as it is."""
        try:
            f = export_output(path)
        except OSError as e:
            notify(f"Could not export: {e}", "negative")
            return
        ui.download.file(str(f), f.name)
        notify(f"Exported {f.name}")

    def link_for(path: str) -> str | None:
        """Serve a result through this app so it opens in a browser tab."""
        if not path:
            return None
        p = Path(path)
        root = p.parent
        last = state.get("last")
        if last is not None and not isinstance(last, Exception):
            out = Path(last.output)
            if out.is_dir():
                root = out
        try:
            rel = p.resolve().relative_to(root.resolve())
        except ValueError:
            root, rel = p.parent, Path(p.name)
        mount = f"/out/{uuid.uuid4().hex[:10]}"
        app.add_static_files(mount, root)
        return f"{mount}/{rel.as_posix()}"

    def open_result(path: str | None, anchor: str = "") -> None:
        if path and Path(path).exists():
            ui.navigate.to(link_for(path) + anchor, new_tab=True)
        else:
            notify("That output no longer exists.", "warning")

    def pick(kind: str, on_pick, folders: bool, start: str = "", title: str = "") -> None:
        st = {"path": start or s.source or str(Path.cwd())}
        with ui.dialog() as dlg, ui.card().classes("or-card w-[40rem] max-w-full"):
            ui.label(title or ("Choose a folder" if folders else "Choose a file")).classes("or-h2")
            path_label = ui.label().classes("or-mono or-hint")
            box = ui.column().classes("w-full gap-0 max-h-[50vh] overflow-auto")

            def show(p: str) -> None:
                lst = browse(p, kind)  # type: ignore[arg-type]
                st["path"] = lst.path
                path_label.text = lst.path
                box.clear()
                with box:
                    if lst.parent:
                        ui.button("..", icon="arrow_upward", on_click=lambda: show(lst.parent)) \
                            .props("flat align=left no-caps").classes("w-full")
                    for d in lst.dirs:
                        ui.button(d, icon="folder", on_click=lambda d=d: show(str(Path(lst.path) / d))) \
                            .props("flat align=left no-caps").classes("w-full")
                    if not folders:
                        for f in lst.files:
                            ui.button(f, icon="description",
                                      on_click=lambda f=f: (on_pick(str(Path(lst.path) / f)), dlg.close())) \
                                .props("flat align=left no-caps").classes("w-full")
                    if not lst.dirs and (folders or not lst.files):
                        ui.label("Nothing here.").classes("or-hint q-pa-sm")

            show(st["path"])
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat no-caps")
                if folders:
                    ui.button("Use this folder", icon="check",
                              on_click=lambda: (on_pick(st["path"]), dlg.close())).props("no-caps unelevated")
        dlg.open()

    def badge(kind: str, text: str):
        return ui.html(f'<span class="or-badge {kind}">{text}</span>', sanitize=False)

    def segmented(options, selected: str, on_pick, label: str):
        with ui.element("div").classes("or-seg").props(f'role="tablist" aria-label="{label}"') as seg:
            for key, text in options:
                b = ui.element("button").props(f'type="button" role="tab" aria-selected="{str(selected == key).lower()}"')
                with b:
                    ui.label(text)
                b.on("click", lambda key=key: on_pick(key))
        return seg

    def render_changes(res, store: dict, rerender, on_new=None) -> None:
        """Comparison result: summary tiles and the filterable Changes table (Build and Compare pages)."""
        ch = res.changes
        sm = change_counts(ch)
        with ui.card().classes("or-card w-full").props("flat"):
            with ui.column().classes("or-sec gap-3"):
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    with ui.column().classes("gap-1 min-w-0"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(f"{ch.get('old_version') or 'previous'} → {ch.get('new_version') or 'current'}") \
                                .classes("or-h2")
                            if sm["added"] + sm["removed"] + sm["modified"]:
                                badge("info", "Changes found")
                            else:
                                badge("ok", "No differences")
                        ui.label(f"Compare versions · {res.seconds:.1f} s · {res.index}  (also .md and .json)") \
                            .classes("or-hint or-mono")
                    with ui.row().classes("gap-2"):
                        if on_new is not None:
                            ui.button("New build", icon="add", on_click=on_new).props("flat no-caps").mark("new-build")
                        ui.button("Open HTML report", icon="open_in_new", on_click=lambda: open_result(res.index)) \
                            .props("unelevated no-caps")
                        ui.button("Download HTML", icon="download", on_click=lambda: ui.download.file(res.index)) \
                            .props("outline no-caps").mark("download-html")
                        ui.button("Show in folder", icon="folder_open",
                                  on_click=lambda: reveal(str(res.output))).props("outline no-caps")
                with ui.row().classes("w-full gap-3"):
                    for k, key, cls in (("Added", "added", "ok-tile"), ("Removed", "removed", "err"),
                                        ("Modified", "modified", "warn")):
                        with ui.element("div").classes(f"or-tile {cls}"):
                            ui.label(k).classes("k")
                            ui.label(str(sm[key])).classes("v")
        rows = []
        for kind, items in (("added", ch["added"]), ("removed", ch["removed"]),
                            ("modified", ch["metadata_changes"] + ch["modified"])):
            for c in items:
                details = "\n".join([f"+ {p}: {v}" for p, v in c["added"]] + [f"− {p}: {v}" for p, v in c["removed"]])
                rows.append({"id": len(rows), "change": kind, "term": c["label"], "id_": c.get("curie") or c["iri"],
                             "kind": c["kind"].replace("_", " "), "details": details})
        with ui.card().classes("or-card w-full").props("flat"):
            with ui.column().classes("or-sec gap-3"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Changes").classes("or-h2")
                    counts = {k: sum(1 for r in rows if r["change"] == k) for k in ("added", "removed", "modified")}
                    segmented([("all", f"All {len(rows)}"), ("added", f"Added {counts['added']}"),
                               ("removed", f"Removed {counts['removed']}"), ("modified", f"Modified {counts['modified']}")],
                              store.get("filter", "all"), lambda k: (store.__setitem__("filter", k), rerender()), "Filter changes")
                shown = [r for r in rows if store.get("filter", "all") in ("all", r["change"])]
                if not shown:
                    ui.label("No differences between the two versions." if not rows else "Nothing of this kind.") \
                        .classes("or-hint q-py-md")
                    return
                tbl = ui.table(rows=shown, row_key="id", pagination={"rowsPerPage": 25}, columns=[
                    {"name": "change", "label": "Change", "field": "change", "align": "left"},
                    {"name": "term", "label": "Term", "field": "term", "align": "left"},
                    {"name": "kind", "label": "Kind", "field": "kind", "align": "left"},
                    {"name": "details", "label": "Details", "field": "details", "align": "left"}]) \
                    .classes("or-table").props("flat dense wrap-cells")
                tbl.add_slot("body-cell-change", r'''<q-td :props="props">
                    <span :class="'or-badge ' + ({added:'ok', removed:'err', modified:'warn'}[props.value])">
                    {{ {added:'Added', removed:'Removed', modified:'Modified'}[props.value] }}</span></q-td>''')
                tbl.add_slot("body-cell-term", r'''<q-td :props="props"><div class="text-weight-medium">{{ props.value }}</div>
                    <div class="or-hint or-mono">{{ props.row.id_ }}</div></q-td>''')
                tbl.add_slot("body-cell-details", r'''<q-td :props="props">
                    <div class="or-mono" style="font-size:12px;white-space:pre-wrap">{{ props.value }}</div></q-td>''')

    # ------------------------------------------------------------------ drag and drop dispatch
    # One handler per event for the whole app; each page registers what a drop on its zones does.
    drop_targets: dict = {}

    def _drop(kind: str, e) -> None:
        a = e.args or {}
        handler = drop_targets.get(a.get("zone") or "")
        if handler:
            handler[0 if kind == "start" else 1](a)

    ui.on("ob_drop_start", lambda e: _drop("start", e))
    ui.on("ob_drop_done", lambda e: _drop("done", e))

    def dropped_path(a: dict, info, files_only: bool = False) -> str | None:
        """Resolve a finished drop to a local path, reporting problems in ``info``."""
        if not a.get("batch") or not a.get("ok"):
            msg = ("Nothing usable was dropped: no ontology files found." if not a.get("failed") else
                   f"Copy failed for {a.get('failed')} file(s).")
            info.text = msg
            notify(msg, "warning")
            return None
        target = upload_source(a["batch"])
        if not target:
            notify("The dropped files could not be found.", "negative")
            return None
        if files_only and Path(target).is_dir():
            info.text = "Drop a single ontology file here (a folder can't be compared)."
            notify(info.text, "warning")
            return None
        extra = (f", {a['skipped']} other file(s) ignored" if a.get("skipped") else "") + \
            (f", {a['failed']} failed" if a.get("failed") else "")
        info.text = f"Copied {a['ok']} file(s){extra} into a local workspace."
        return target

    # ------------------------------------------------------------------ shared form parts
    def repo_picker(on_add, hint: str = "") -> None:
        """Find an ontology on OLS or BioPortal by name or id and add it as a reference (ols:envo)."""
        from .quality_checks.cdi.repos import search_ontologies

        with ui.column().classes("w-full gap-1"):
            ui.label("Find on OLS or BioPortal").classes("or-label")
            with ui.row().classes("w-full no-wrap gap-2 items-center"):
                repo = ui.select({"ols": "OLS", "bioportal": "BioPortal"}, value="ols") \
                    .props('outlined dense aria-label="Repository"').classes("w-36")
                q = ui.input(placeholder="Name or id, e.g. envo, environment, NCIT") \
                    .props('outlined dense clearable aria-label="Find an ontology"').classes("grow").mark("repo-query")
                btn = ui.button("Search", icon="search").props("outline no-caps no-wrap") \
                    .classes("shrink-0").mark("repo-search")
            ui.label(hint or "Adds the ontology by its repository id, e.g. ols:envo or bioportal:NCIT, so it "
                             "is fetched from there; nothing to upload.").classes("or-hint")
            box = ui.column().classes("w-full gap-1")

        async def search() -> None:
            box.clear()
            text = (q.value or "").strip()
            if not text:
                return
            key = prefs.cdi_bioportal_key.strip() or os.environ.get("BIOPORTAL_API_KEY", "")
            with box:
                ui.spinner(size="18px")
            try:
                hits = await run.io_bound(search_ontologies, text, repo.value, key)
            except Exception as e:  # noqa: BLE001
                box.clear()
                with box:
                    ui.label(f"Search failed: {e}").classes("or-hint text-negative")
                return
            box.clear()
            with box:
                if not hits:
                    ui.label(f"No ontology on {repo.value.upper() if repo.value == 'ols' else 'BioPortal'} "
                             f"matches “{text}”.").classes("or-hint")
                for h in hits:
                    with ui.row().classes("w-full items-center no-wrap gap-2 q-py-xs") \
                            .style("border-bottom:1px solid var(--or-line-2)"):
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(h.title).classes("text-weight-medium ellipsis w-full")
                            ui.label(h.spec).classes("or-hint or-mono")
                        if h.description:
                            ui.icon("info", size="16px").classes("or-muted").tooltip(h.description)
                        b = ui.button("Add", icon="add").props("flat dense no-caps no-wrap").classes("shrink-0") \
                            .mark(f"repo-add-{h.id}")
                        b.on_click(lambda _, h=h, b=b: (on_add([h.spec]), b.set_text("Added"), b.disable()))

        q.on("keydown.enter", search)
        btn.on_click(search)

    def domain_rows(get, put) -> None:
        """The SI domain map as a form: reference ontology id + OECD fields per row. A new empty row
        appears as soon as the last one is used; the value is kept as text ("ols:emi = 1.5; 1.6")."""
        from .quality_checks.cdi.si import OECD_FOS

        options = {c: f"{c} {n}" for c, n in OECD_FOS.items()}
        rows: list[dict] = []
        for line in (get() or "").splitlines():
            oid, sep, doms = line.partition("=")
            if sep and oid.strip():
                rows.append({"id": oid.strip(),
                             "doms": [d.strip() for d in doms.replace(",", ";").split(";") if d.strip() in options]})
        box = ui.column().classes("w-full gap-2").mark("si-domain-rows")

        def save() -> None:
            put("\n".join(f"{r['id']} = {'; '.join(r['doms'])}" for r in rows if r["id"].strip() and r["doms"]))

        def changed(r: dict) -> None:
            save()
            if rows and rows[-1] is r and r["id"].strip():
                add({"id": "", "doms": []})          # keep one empty row at the end

        def remove(r: dict, el) -> None:
            if r in rows:
                rows.remove(r)
            el.delete()
            save()
            if not rows or rows[-1]["id"].strip():
                add({"id": "", "doms": []})

        def add(r: dict) -> None:
            rows.append(r)
            with box:
                with ui.row().classes("w-full no-wrap gap-2 items-center") as el:
                    ui.input(placeholder="ols:emi, bioportal:NCIT or file:mine.ttl", value=r["id"],
                             on_change=lambda e, r=r: (r.__setitem__("id", e.value or ""), changed(r))) \
                        .props('outlined dense aria-label="Reference ontology id"').classes("or-mono") \
                        .style("flex: 1 1 12rem; min-width: 9rem").mark("si-domain-id")
                    ui.select(options, multiple=True, value=list(r["doms"]),
                              on_change=lambda e, r=r: (r.__setitem__("doms", list(e.value or [])), changed(r))) \
                        .props('outlined dense use-chips aria-label="Scientific domains" label="Domain(s)"') \
                        .style("flex: 1 1 14rem; min-width: 10rem")
                    ui.button(icon="close", on_click=lambda r=r, el=el: remove(r, el)) \
                        .props('flat round dense aria-label="Remove row"')

        for r in list(rows):
            rows.remove(r)
            add(r)
        add({"id": "", "doms": []})

    def deploy_dialog(site: str) -> None:
        """Push a website run to a GitHub repository; its Pages workflow publishes it."""
        from .publish.github import DeployError, deploy_site, pages_url, parse_remote

        with ui.dialog() as d, ui.card().classes("or-card").style("width:min(40rem,94vw);max-height:90vh;overflow-y:auto"):
            with ui.row().classes("w-full items-start justify-between no-wrap"):
                with ui.column().classes("gap-0"):
                    ui.label("Deploy to GitHub Pages").classes("or-h2")
                    ui.label(Path(site).name).classes("or-hint or-mono")
                ui.button(icon="close", on_click=d.close).props('flat round dense aria-label="Close"')
            ui.label("Pushes this website to a GitHub repository. The workflow included in every website "
                     "(.github/workflows/pages.yml) publishes it on GitHub Pages; later deploys to the same "
                     "repository update the site and keep its history.").classes("or-hint")
            ui.label("Repository").classes("or-label")
            remote = ui.input(placeholder="https://github.com/you/ontology-docs", value=prefs.deploy_remote) \
                .props('outlined dense clearable aria-label="GitHub repository"').classes("w-full or-mono") \
                .mark("deploy-remote")
            url_hint = ui.label().classes("or-hint")
            with ui.row().classes("gap-4 items-end"):
                with ui.column().classes("gap-1"):
                    ui.label("Branch").classes("or-label")
                    branch = ui.input(value=prefs.deploy_branch or "main") \
                        .props('outlined dense aria-label="Branch"').classes("w-40 or-mono")
                pages = ui.checkbox("Turn on GitHub Pages", value=prefs.deploy_enable_pages)
            has_token = bool((prefs.deploy_token or "").strip())
            create = ui.checkbox("Create the repository if it does not exist"
                                 + (" (private)" if prefs.deploy_private else ""),
                                 value=prefs.deploy_create and has_token).mark("deploy-create")
            create.set_enabled(has_token)
            with ui.row().classes("items-center gap-1"):
                ui.icon("key" if has_token else "key_off", size="16px").classes("or-muted")
                ui.label("Signs in with the GitHub token from Settings." if has_token else
                         "No GitHub token set: pushes with your git login (gh auth login, credential helper or SSH) "
                         "and the repository must exist. Add a token to create it and turn on Pages for you.") \
                    .classes("or-hint")
                ui.link("Settings", "/settings").classes("or-hint text-primary")
            ui.label("A public repository makes the site public.").classes("or-hint")
            past = deploys_for(site)
            if past:
                ui.label("Earlier deploys of this run").classes("or-label q-mt-sm")
                for x in past[:5]:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("cloud_done", size="16px").classes("or-muted")
                        ui.label(f"{x.get('when', '')[:16].replace('T', ' ')} UTC → ").classes("or-hint")
                        ui.link(x.get("pages_url", ""), x.get("pages_url", ""), new_tab=True).classes("or-hint")
            result_box = ui.column().classes("w-full gap-1")
            with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                ui.button("Cancel", on_click=d.close).props("flat no-caps")
                go = ui.button("Deploy", icon="cloud_upload").props("unelevated no-caps").mark("deploy-go")

            def show_url() -> None:
                try:
                    o, r = parse_remote(remote.value or "")
                    url_hint.text = f"The site will be at {pages_url(o, r)}"
                except DeployError:
                    url_hint.text = "A GitHub address: https://github.com/<you>/<repo> or git@github.com:<you>/<repo>.git"
            remote.on_value_change(lambda _: show_url())
            show_url()

            async def run_deploy() -> None:
                result_box.clear()
                prefs.deploy_remote, prefs.deploy_branch = (remote.value or "").strip(), (branch.value or "main").strip()
                prefs.deploy_enable_pages = bool(pages.value)
                prefs.save()
                go.disable()
                with result_box:
                    with ui.row().classes("items-center gap-2"):
                        ui.spinner(size="18px")
                        ui.label("Pushing to GitHub…").classes("or-hint")
                try:
                    res = await run.io_bound(lambda: deploy_site(
                        site, prefs.deploy_remote, prefs.deploy_branch, None, prefs.deploy_enable_pages,
                        token=prefs.deploy_token or None, create=bool(create.value), private=prefs.deploy_private))
                except Exception as e:  # noqa: BLE001 - DeployError and anything git says
                    result_box.clear()
                    with result_box:
                        ui.label(f"Deploy failed: {e}").classes("or-hint text-negative").style("word-break:break-word")
                    go.enable()
                    return
                add_deploy(site, res.to_dict())
                result_box.clear()
                with result_box:
                    with ui.row().classes("items-center gap-2"):
                        badge("ok", "Deployed" if res.changed else "Up to date")
                        ui.link(res.pages_url, res.pages_url, new_tab=True).classes("text-weight-medium")
                    ui.label(f"Commit {res.commit} on {res.branch} · {res.repo_url}").classes("or-hint or-mono")
                    for n in res.notes:
                        ui.label(n).classes("or-hint").style("word-break:break-word")
                go.enable()
                notify("Deployed to GitHub" if res.changed else "Already up to date", "positive")

            go.on_click(run_deploy)
        d.open()

    def creator_rows(get, put) -> None:
        """Creators as rows (name, ORCID, email), with an "Add creator" button for more. The value is
        kept as text, one "Name | ORCID | email" line per creator."""
        from .fixes.rules import ORCID_RE, parse_creators

        rows = [dict(c) for c in parse_creators(get() or "")]
        with ui.column().classes("w-full gap-1"):
            box = ui.column().classes("w-full gap-2").mark("creator-rows")
            ui.button("Add creator", icon="person_add", on_click=lambda: add({"name": "", "orcid": "", "email": ""})) \
                .props("flat dense no-caps").mark("creator-add")

        def save() -> None:
            put("\n".join(f"{r['name']} | {r['orcid']} | {r['email']}" for r in rows if r["name"].strip()))

        def changed(r: dict, key: str, value: str, warn=None) -> None:
            r[key] = (value or "").strip()
            if warn is not None and key == "orcid":
                warn.set_visibility(bool(r["orcid"]) and not ORCID_RE.search(r["orcid"]))
            save()

        def remove(r: dict, el) -> None:
            if r in rows:
                rows.remove(r)
            el.delete()
            save()
            if not rows:                     # always at least one row to type into
                add({"name": "", "orcid": "", "email": ""})

        async def lookup(r: dict, oi, picks, auto: bool = False) -> None:
            """Candidates from the ORCID registry for the row's name; the user picks one (or none)."""
            from .fixes.orcid import search_orcid
            name = r["name"].strip()
            if len(name) < 3 or (auto and (r["orcid"] or r.get("_looked") == name or name in ORCID_DISMISSED)):
                return
            r["_looked"] = name
            picks.clear()
            with picks:
                ui.spinner(size="sm")
                ui.label(f"Looking up “{name}” in ORCID…").classes("or-hint")
            # results are cached by name: the panel may be re-rendered while the lookup runs, and the new
            # row then shows them instead of losing them
            if name not in ORCID_HITS:
                ORCID_HITS[name] = None
                try:
                    ORCID_HITS[name] = await run.io_bound(search_orcid, name)
                except Exception as e:  # noqa: BLE001 - offline, rate limit, …
                    ORCID_HITS.pop(name, None)
                    if not picks.is_deleted:
                        picks.clear()
                        if not auto:
                            with picks:
                                ui.label(f"ORCID lookup failed ({type(e).__name__}); type the ORCID yourself.") \
                                    .classes("or-hint text-negative")
                    return
            for _ in range(100):                  # another row/render already asked: wait for its answer
                if ORCID_HITS.get(name) is not None or name not in ORCID_HITS:
                    break
                await asyncio.sleep(0.15)
            hits = ORCID_HITS.get(name) or []
            if picks.is_deleted:
                return
            picks.clear()
            with picks:
                if not hits:
                    ui.label(f"No ORCID record found for “{name}”.").classes("or-hint")
                    return
                ui.label("Is one of these the creator? Pick to fill in the ORCID:").classes("or-hint")
                for h in hits:
                    with ui.row().classes("items-center gap-2 no-wrap"):
                        ui.button("Use", on_click=lambda h=h: use(r, oi, picks, h["orcid"])) \
                            .props("dense flat no-caps color=primary").mark(f"orcid-use orcid-{h['orcid']}")
                        ui.label(h["name"]).classes("text-sm")
                        ui.link(h["orcid"], h["url"], new_tab=True).classes("or-mono text-xs")
                        if h["institutions"]:
                            ui.label(" · ".join(h["institutions"])).classes("or-hint")
                ui.button("None of these", on_click=lambda: (ORCID_DISMISSED.add(name), picks.clear())) \
                    .props("dense flat no-caps").classes("or-hint")

        def use(r: dict, oi, picks, orcid: str) -> None:
            oi.value = orcid             # on_value_change saves and validates it
            picks.clear()

        def add(r: dict) -> None:
            rows.append(r)
            with box, ui.column().classes("w-full gap-0") as el:
                with ui.row().classes("w-full no-wrap gap-2 items-center"):
                    ui.label(f"{len(rows)}.").classes("or-hint").style("width:16px")
                    ni = ui.input("Name", value=r["name"], on_change=lambda e, r=r: changed(r, "name", e.value)) \
                        .props("outlined dense").style("flex: 1 1 14rem").mark("creator-name")
                    oi = ui.input("ORCID (optional)", value=r["orcid"], placeholder="0000-0002-1825-0097") \
                        .props("outlined dense").classes("or-mono").style("flex: 1 1 13rem").mark("creator-orcid")
                    ui.input("Email (optional)", value=r["email"], on_change=lambda e, r=r: changed(r, "email", e.value)) \
                        .props("outlined dense type=email").style("flex: 1 1 13rem").mark("creator-email")
                    ui.button(icon="close", on_click=lambda r=r, el=el: remove(r, el)) \
                        .props('flat round dense aria-label="Remove creator"')
                warn = ui.label("An ORCID looks like 0000-0002-1825-0097 (or its https://orcid.org/ link).") \
                    .classes("or-hint text-negative")
                warn.set_visibility(False)
                picks = ui.column().classes("gap-1 q-pl-lg").mark("orcid-picks")
                oi.on_value_change(lambda e, r=r, w=warn: changed(r, "orcid", e.value, w))
                with oi.add_slot("append"):
                    ui.button(icon="search", on_click=lambda r=r, oi=oi, p=picks: lookup(r, oi, p)) \
                        .props('flat round dense size=sm aria-label="Find ORCID by name"').tooltip("Find in ORCID by name") \
                        .mark("orcid-find")
                # when a name is typed and no ORCID given yet, look it up and offer the matches
                ni.on("blur", lambda _, r=r, oi=oi, p=picks: lookup(r, oi, p, auto=True))
                nm = r["name"].strip()
                if nm in ORCID_HITS and not r["orcid"] and nm not in ORCID_DISMISSED:   # re-rendered mid-lookup
                    ui.timer(0.05, lambda r=r, oi=oi, p=picks: lookup(r, oi, p), once=True)

        for r in list(rows):
            rows.remove(r)
            add(r)
        if not rows:
            add({"name": "", "orcid": "", "email": ""})

    def metrics_grid(metrics: list[dict], title: str = "Quality metrics", mark: str = "ontocheck-metrics") -> None:
        dot = {"ok": "ok", "warn": "warn", "error": "err", "info": "off", "skipped": "off"}
        with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-3 w-full"):
            ui.label(title).classes("or-h2").mark(mark)
            with ui.element("div").classes("w-full").style(
                    "display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 28px"):
                for group in dict.fromkeys(m["group"] for m in metrics):
                    with ui.column().classes("gap-2 q-mb-sm min-w-0"):
                        ui.label(group).classes("or-hint text-uppercase").style("letter-spacing:.6px")
                        for m in (m for m in metrics if m["group"] == group):
                            with ui.row().classes("items-start gap-2 no-wrap min-w-0").tooltip(m["about"]):
                                ui.element("span").classes(f"or-dot {dot.get(m['status'], 'off')}") \
                                    .style("margin-top:6px")
                                with ui.column().classes("gap-0 min-w-0"):
                                    ui.label(m["title"]).classes("text-weight-medium")
                                    ui.label(m["value"]).classes("or-hint").style("word-break:break-word")

    # ------------------------------------------------------------------ Build
    def build_view() -> None:  # noqa: C901
        set_active("build")
        ready: list[bool] = []

        def changed(*_) -> None:  # bindings fire while the page is still being built
            if ready:
                refresh()
        head = page_head("New build", "Pick an ontology, choose what to produce, run.")
        with head:
            with ui.row().classes("gap-2"):
                with ui.dropdown_button("Project config", icon="tune", auto_close=True) \
                        .props("outline no-caps").tooltip(
                            "ontoreview.toml stores this setup next to your ontology so the command line, CI "
                            "and teammates build exactly the same docs"):
                    for icon, label, hint, action in (
                            ("edit_note", "Edit ontoreview.toml", "Open the project's config in an editor",
                             lambda: edit_config()),
                            ("note_add", "New from template", "Start a commented config for this ontology",
                             lambda: edit_config(template=True)),
                            ("save", "Save current settings", "Write what's selected here into ontoreview.toml",
                             lambda: save_toml()),
                            ("file_open", "Open another config…", "Load settings from any ontoreview.toml",
                             lambda: pick("toml", load_toml, False, title="Choose an ontoreview.toml"))):
                        with ui.item(on_click=action).mark(f"cfg-{icon}"):
                            with ui.item_section().props("avatar"):
                                ui.icon(icon)
                            with ui.item_section():
                                ui.item_label(label)
                                ui.item_label(hint).props("caption")
                run_btn = ui.button(icon="play_arrow", on_click=lambda: start()).props("unelevated no-caps").mark("run")

        with ui.element("div").classes("or-body"):
            with ui.row().classes("w-full gap-4 items-start no-wrap max-lg:flex-wrap"):
                # ---------------- configuration column
                with ui.column().classes("gap-4 w-full lg:w-[44%] lg:max-w-[560px] flex-none"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            with ui.row().classes("items-center gap-2"):
                                ui.html('<span class="or-step">1</span>', sanitize=False)
                                ui.label("Source").classes("or-h2")
                            with ui.element("div").props('data-zone="source"').classes("ob-dropzone w-full"):
                                source_box = ui.column().classes("w-full gap-2")
                            with ui.row().classes("gap-2"):
                                ui.button("File", icon="description", on_click=lambda: pick(
                                    "ontology", set_source, False, title="Choose an ontology file")) \
                                    .props("outline no-caps dense").classes("px-3")
                                ui.button("Folder", icon="folder", on_click=lambda: pick(
                                    "ontology", set_source, True, title="Choose a folder of ontologies")) \
                                    .props("outline no-caps dense").classes("px-3")
                                ui.button("URL", icon="link", on_click=lambda: ask_url()) \
                                    .props("outline no-caps dense").classes("px-3")
                            drop_info = ui.label("Drop a .ttl, .owl, .rdf, .jsonld file — or a folder to document "
                                                 "many at once.").classes("or-hint").props('aria-live="polite"')
                            source_info = ui.label().classes("or-hint").props('aria-live="polite"')

                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.html('<span class="or-step">2</span>', sanitize=False)
                                ui.label("Output").classes("or-h2")
                            fmt_box = ui.element("div").props('role="radiogroup" aria-label="Output format"') \
                                .classes("column gap-2 w-full")
                            ui.label("Save to").classes("or-label q-mt-sm")
                            with ui.row().classes("w-full no-wrap gap-2 items-center"):
                                output = ui.input(on_change=changed).bind_value(s, "output").mark("output") \
                                    .props('outlined dense clearable aria-label="Save to"').classes("grow or-mono")
                                ui.button("Browse…", on_click=lambda: pick(
                                    "any", lambda p: output.set_value(p), True, s.output or str(s.output_path().parent),
                                    title="Choose the output folder")).props("outline no-caps")
                            output_info = ui.label().classes("or-hint or-mono w-full").style("word-break: break-all") \
                                .props('aria-live="polite"')
                            separate_cb = ui.checkbox("Each run in its own folder (self-contained, never overwritten)",
                                                      on_change=changed).bind_value(s, "separate_runs") \
                                .mark("separate-runs").tooltip(
                                    "Adds the date and time to the folder name, so every run keeps its own docs "
                                    "and Run history can open, export or re-run each one")
                            with ui.column().classes("w-full gap-1 q-mt-sm") as prev_box:
                                ui.label("Previous version").classes("or-label")
                                with ui.row().classes("w-full no-wrap gap-2 items-center"):
                                    prev_in = ui.input(placeholder="releases/1.0.0.ttl or https://…", on_change=changed) \
                                        .bind_value(s, "previous_version").mark("previous") \
                                        .props('outlined dense clearable aria-label="Previous version"').classes("grow or-mono")
                                    ui.button("Browse…", on_click=lambda: pick(
                                        "ontology", lambda p: prev_in.set_value(p), False,
                                        title="Choose the previous version")).props("outline no-caps")
                                ui.label("The older release to compare against: a file or a URL.").classes("or-hint")
                            with ui.row().classes("w-full items-center gap-1") as existing_row:
                                existing_info = ui.label().classes("or-hint")
                                ui.button("Open", on_click=lambda: open_result(state.get("prior"))) \
                                    .props("flat dense no-caps size=sm")
                                ui.button("Show in folder", on_click=lambda: reveal(str(s.output_path()))) \
                                    .props("flat dense no-caps size=sm")
                            with ui.row().classes("w-full items-center no-wrap gap-2 q-mt-sm q-pa-sm") \
                                    .style("background: var(--or-line-2); border-radius: 8px") as checks_row:
                                ui.icon("fact_check", size="18px").classes("text-primary")
                                checks_info = ui.label().classes("or-hint grow").style("color: var(--or-ink-2)")
                                ui.link("Change in Settings", "/settings").classes("or-hint text-primary text-no-wrap")

                # ---------------- results column
                with ui.column().classes("gap-4 grow min-w-0 w-full"):
                    results = ui.column().classes("gap-4 w-full")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.expansion("Build log", value=False).classes("w-full").props(
                                "dense header-class=or-label"):
                            log_view = ui.log(max_lines=1000).classes("w-full or-log")
                            for line in state["log"]:
                                log_view.push(line)
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.expansion("Command line", value=False).classes("w-full").props(
                                "dense header-class=or-label"):
                            with ui.column().classes("w-full gap-2 q-pb-sm"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    ui.label("The same run from a terminal or CI.").classes("or-hint")
                                    ui.button("Copy", icon="content_copy", on_click=lambda: (
                                        ui.clipboard.write(s.cli()), notify("Command copied", "positive"))) \
                                        .props('flat dense no-caps size=sm aria-label="Copy command"')
                                cli = ui.label().classes("or-cli")

        # ---------------- behaviour
        def set_source(p: str) -> None:
            s.source = p
            refresh()

        def ask_url() -> None:
            with ui.dialog() as dlg, ui.card().classes("or-card w-[36rem] max-w-full"):
                ui.label("Ontology URL or path").classes("or-h2")
                inp = ui.input(placeholder="https://… or /path/to/ontology.ttl", value=s.source) \
                    .props("outlined autofocus").classes("w-full or-mono")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dlg.close).props("flat no-caps")
                    ui.button("Use", on_click=lambda: (set_source(inp.value.strip()), dlg.close())).props("unelevated no-caps")
                inp.on("keydown.enter", lambda: (set_source(inp.value.strip()), dlg.close()))
            dlg.open()

        def render_source() -> None:
            source_box.clear()
            with source_box:
                if s.source.strip():
                    p = Path(s.source).expanduser()
                    is_url = s.source.startswith(("http://", "https://"))
                    with ui.element("div").classes("or-chip"):
                        with ui.element("div").classes("or-chipicon"):
                            ui.icon("link" if is_url else "folder" if s.is_folder else "description", size="20px")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(s.source if is_url else (p.name or str(p))).classes("or-label ellipsis w-full")
                            if not is_url:
                                ui.label(str(p.parent) + "/").classes("or-hint or-mono ellipsis w-full")
                        ui.button(icon="close", on_click=lambda: set_source("")) \
                            .props('flat round dense aria-label="Clear source"').mark("source-clear")
                else:
                    src_in = ui.input(placeholder="Type a path or URL and press Enter, or drop files here") \
                        .props('borderless dense aria-label="Ontology path or URL"').classes("w-full or-mono").mark("source")
                    src_in.on("keydown.enter", lambda: set_source((src_in.value or "").strip()))
                    src_in.on("blur", lambda: (src_in.value or "").strip() and set_source(src_in.value.strip()))

        def render_formats() -> None:
            fmt_box.clear()
            with fmt_box:
                for fid, name, desc, tag in FORMATS:
                    sel = s.task == fid
                    with ui.element("button").classes("or-opt" + (" or-sel" if sel else "")).props(
                            f'type="button" role="radio" aria-checked="{str(sel).lower()}"') as b:
                        ui.element("span").classes("or-radio")
                        with ui.column().classes("gap-0 grow"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label(name).classes("or-label")
                                if fid == RECOMMENDED:
                                    ui.html('<span class="or-badge ok" style="padding:1px 8px;font-size:11px">Recommended</span>',
                                            sanitize=False)
                            ui.label(desc).classes("or-hint")
                            if sel:
                                ui.label(INCLUDES[fid]).classes("or-hint q-mt-xs").style("color: var(--or-ink-2)")
                        ui.label(tag).classes("or-tag")
                    b.mark(f"fmt-{fid}")
                    b.on("click", lambda fid=fid: (setattr(s, "task", fid), refresh()))

        def refresh() -> None:
            # another ontology picked: the result shown belongs to the previous one, so clear it
            if (state["last"] is not None and not state["running"] and state.get("shown_for") is not None
                    and s.source != state["shown_for"]):
                new_build()
            render_source()
            render_formats()
            describe_later()
            output.props(f'placeholder="{s.default_output()}"')
            per_run = s.separate_runs and s.task in RUN_FOLDER_TASKS
            op = s.output_path().resolve()
            is_file = op.suffix.lower() in (".html", ".json", ".md")
            out_txt = (op.parent / f"{op.stem if is_file else op.name}-<date>-<time>" / (op.name if is_file else ""))
            output_info.text = (f"Writes to: {out_txt}  (a new folder each run)"
                                if per_run else
                                f"Writes to: {s.output_path().resolve()}" + ("" if s.output.strip() else "  (default)"))
            separate_cb.set_visibility(s.task in RUN_FOLDER_TASKS)
            prior = None if per_run else existing_output(s.output_path())
            state["prior"] = prior["index"] if prior else None
            existing_row.set_visibility(prior is not None)
            if prior:
                what = f"{prior['count']} ontologies" if prior["kind"] == "folder" else "output"
                existing_info.text = f"Previous {what} here from {when_text(prior['when'])}; building again updates it."
            checks_row.set_visibility(s.task in ("site", "single", "check", "interop"))
            prev_box.set_visibility(s.task == "diff")
            robot_txt = ("ROBOT off" if s.robot == "off" else
                         f"ROBOT ({'local' if s.robot_path else 'Docker'})")
            oops_txt = {"off": "OOPS! off", "auto": "OOPS! alongside ROBOT (uploads the ontology)",
                        "on": "OOPS! full catalogue (uploads the ontology)"}[s.oops]
            reasoner_txt = ("" if s.robot == "off" or s.reasoner == "off" else
                            f" · {'HermiT' if s.reasoner == 'hermit' else 'ELK'} consistency")
            cdi_txt = f" · cross-domain interoperability ({len(s.cdi_reference_list())} references)" if s.cdi else ""
            si_n = len(s.si_reference_list()) or len(s.cdi_reference_list())
            si_txt = f" · scientific interoperability ({si_n} references)" if s.si else ""
            if s.task == "interop":
                checks_info.text = ("Interoperability only: " + (cdi_txt + si_txt).lstrip(" ·")
                                    if s.cdi or s.si else "Turn on cross-domain or scientific interoperability.")
            else:
                checks_info.text = f"Quality checks: built-in · {robot_txt}{reasoner_txt} · {oops_txt}{cdi_txt}{si_txt}"
            cli.text = s.cli()
            show_running()
            s.save()

        described = {"for": None}

        def describe_later() -> None:
            """Folder scans can take a while: describe the source in a worker thread."""
            src = s.source.strip()
            if src == described["for"]:
                return
            described["for"] = src
            source_info.text = "Looking…" if src else ""
            if src:
                background_tasks.create(describe(src), name="describe-source")

        async def describe(src: str) -> None:
            text = await run.io_bound(describe_source, src)
            if described["for"] == src and not source_info.is_deleted:
                source_info.text = text

        def show_running() -> None:
            run_btn.text = "Running…" if state["running"] else {"check": "Run checks", "interop": "Run checks",
                                                                 "diff": "Compare"}.get(s.task, "Build docs")
            run_btn.set_enabled(not state["running"])

        def new_build() -> None:
            """Clear the shown result and the log so the next run starts from an empty panel.
            The form keeps its settings; the run stays in Run history."""
            if state["running"]:
                return
            state["last"] = None
            state["log"].clear()
            log_view.clear()
            seen["log"] = 0
            render_results()

        def new_build_button() -> None:
            ui.button("New build", icon="add", on_click=new_build).props("flat no-caps").mark("new-build") \
                .tooltip("Clear this result and start a new build (it stays in Run history)")

        def render_results() -> None:  # noqa: C901
            results.clear()
            with results:
                if state["running"]:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            name = Path(s.source).name or s.source
                            done_n, total = len(state["done"]), len(state["steps"])
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label({"check": f"Checking {name}…", "interop": f"Checking {name}…",
                                          "diff": f"Comparing {name}…"}.get(
                                    s.task, f"Building {name}…")).classes("or-h2")
                                ui.label(state["folder_pos"] or f"Step {min(done_n + 1, total)} of {total}").classes("or-hint")
                            ui.linear_progress(value=done_n / max(total, 1), show_value=False).props("rounded size=6px")
                            with ui.element("ol").classes("or-steps q-pa-none q-ma-none"):
                                for key, label in state["steps"]:
                                    with ui.element("li"):
                                        if key in state["done"]:
                                            ui.icon("check_circle", size="18px").classes("done")
                                            ui.label(label)
                                        elif key == state["active"]:
                                            ui.spinner(size="18px")
                                            ui.label(label).classes("text-weight-medium")
                                        else:
                                            ui.icon("radio_button_unchecked", size="18px").classes("todo")
                                            ui.label(label).classes("todo")
                    return
                res = state["last"]
                if res is None:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2 items-center text-center q-py-xl"):
                            ui.icon("auto_stories", size="40px").classes("or-muted")
                            ui.label("No build yet").classes("or-h2")
                            ui.label("Choose a source, pick a format and press Build docs. Results, quality "
                                     "issues and the log appear here.").classes("or-hint")
                    return
                if isinstance(res, Exception):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label("Build failed").classes("or-h2")
                                    badge("err", "Failed")
                                new_build_button()
                            ui.label(str(res)).classes("or-mono or-hint")
                    return
                if res.task == "diff" and res.changes:
                    render_changes(res, state, render_results, on_new=new_build)
                    return
                t = res.totals
                failed = len(res.rows) - res.ok
                many = len(res.rows) > 1
                with ui.card().classes("or-card w-full").props("flat"):
                    with ui.column().classes("or-sec gap-3"):
                        with ui.row().classes("w-full items-start justify-between gap-3"):
                            with ui.column().classes("gap-1 min-w-0"):
                                with ui.row().classes("items-center gap-2"):
                                    title = f"{len(res.rows)} ontologies" if many else (res.rows[0].title or res.rows[0].name)
                                    ui.label(title).classes("or-h2")
                                    if not res.ok:
                                        badge("err", "Failed")
                                    elif failed:
                                        badge("warn", f"{failed} failed")
                                    else:
                                        badge("ok", "Succeeded")
                                    if many:
                                        ui.label(f"{res.ok} of {len(res.rows)} succeeded").classes("or-hint")
                                ui.label(f"{TASKS[res.task]} · {res.seconds:.1f} s · {res.index or res.output}") \
                                    .classes("or-hint or-mono")
                            with ui.row().classes("gap-2"):
                                new_build_button()
                                if res.index and res.task not in ("check", "interop"):
                                    ui.button("Open docs", icon="open_in_new", on_click=lambda: open_result(res.index)) \
                                        .props("unelevated no-caps")
                                if res.task in ("site", "single", "markdown", "myst") and not many:
                                    ui.button("Review fixes", icon="build", on_click=lambda: start(force_review=True)) \
                                        .props("outline no-caps").mark("review-fixes") \
                                        .tooltip("Fix the issues found, write a fixed copy and rebuild from it")
                                if res.task == "site" and res.ok:
                                    ui.button("Deploy", icon="cloud_upload",
                                              on_click=lambda: deploy_dialog(str(res.output))) \
                                        .props("outline no-caps").mark("deploy-output") \
                                        .tooltip("Publish this website on GitHub Pages")
                                ui.button("Export", icon="download", on_click=lambda: export(str(res.output))) \
                                    .props("outline no-caps").mark("export-output") \
                                    .tooltip("Download the output" + (" as a .zip" if Path(res.output).is_dir() else ""))
                                ui.button("Show in folder", icon="folder_open",
                                          on_click=lambda: reveal(str(res.output))).props("outline no-caps")
                        with ui.row().classes("w-full gap-3"):
                            for k, v, cls in (("Terms documented", t["terms"], ""), ("Errors", t["errors"], "err"),
                                              ("Warnings", t["warnings"], "warn")):
                                with ui.element("div").classes(f"or-tile {cls}"):
                                    ui.label(k).classes("k")
                                    ui.label(f"{v:,}").classes("v")
                            ran = sorted({x.split(":")[0] for r in res.rows for x in r.external.split("; ") if x})
                            with ui.element("div").classes("or-tile"):
                                ui.label("Checks run").classes("k")
                                ui.label(" · ".join(ran) or "Built-in only").classes("v small")
                if many:
                    ontology_table(res)
                elif res.rows and res.rows[0].metrics:
                    metrics_card(res.rows[0].metrics)
                issues_card(res, many)

        def ontology_table(res) -> None:
            with ui.card().classes("or-card w-full").props("flat"):
                with ui.column().classes("or-sec gap-2"):
                    ui.label("Ontologies").classes("or-h2")
                    rows = [{"id": i, "name": r.title or r.name, "source": r.name,
                             "terms": "" if r.problem else r.terms, "errors": "" if r.problem else r.errors,
                             "warnings": "" if r.problem else r.warnings, "problem": r.problem or "", "path": r.output}
                            for i, r in enumerate(res.rows)]
                    tbl = ui.table(rows=rows, row_key="id", columns=[
                        {"name": "name", "label": "Ontology", "field": "name", "align": "left"},
                        {"name": "terms", "label": "Terms", "field": "terms"},
                        {"name": "errors", "label": "Errors", "field": "errors"},
                        {"name": "warnings", "label": "Warnings", "field": "warnings"},
                        {"name": "act", "label": "", "field": "path", "align": "right"}]) \
                        .classes("or-table").props("flat dense wrap-cells")
                    tbl.add_slot("body-cell-name", r'''<q-td :props="props">
                        <div class="text-weight-medium">{{ props.row.name }}</div>
                        <div class="or-hint or-mono">{{ props.row.source }}</div>
                        <div v-if="props.row.problem" class="text-negative" style="font-size:12px">{{ props.row.problem }}</div></q-td>''')
                    tbl.add_slot("body-cell-act", r'''<q-td :props="props" class="text-no-wrap">
                        <q-btn v-if="props.row.path" flat round dense size="sm" icon="open_in_new"
                          :aria-label="'Open ' + props.row.name" @click="() => $parent.$emit('open', props.row.path)" />
                        <q-btn v-if="props.row.path" flat round dense size="sm" icon="folder_open"
                          :aria-label="'Show ' + props.row.name + ' in folder'" @click="() => $parent.$emit('reveal', props.row.path)" />
                        </q-td>''')
                    tbl.on("open", lambda e: open_result(e.args))
                    tbl.on("reveal", lambda e: reveal(e.args))

        def metrics_card(metrics: list[dict]) -> None:
            metrics_grid(metrics)

        def issues_card(res, many: bool) -> None:
            all_issues = res.issues
            counts = {k: sum(1 for i in all_issues if i["severity"] == k) for k in ("error", "warning", "info")}
            with ui.card().classes("or-card w-full").props("flat"):
                with ui.column().classes("or-sec gap-3"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Issues").classes("or-h2")
                        opts = [("all", f"All {len(all_issues)}"), ("error", f"Errors {counts['error']}"),
                                ("warning", f"Warnings {counts['warning']}")]
                        if counts["info"]:
                            opts.append(("info", f"Info {counts['info']}"))
                        segmented(opts, state["filter"],
                                  lambda k: (state.__setitem__("filter", k), render_results()), "Filter issues")
                    notes = sorted({n for r in res.rows for n in r.notes})
                    for n in notes:
                        ui.label(n).classes("or-hint")
                    shown = [i for i in all_issues if state["filter"] in ("all", i["severity"])]
                    if not shown:
                        ui.label("No issues found." if not all_issues else "No issues of this kind.").classes("or-hint q-py-md")
                    else:
                        cols = [{"name": "severity", "label": "Severity", "field": "severity", "align": "left"},
                                {"name": "check", "label": "Check", "field": "check", "align": "left"}]
                        if many:
                            cols.append({"name": "ontology", "label": "Ontology", "field": "ontology", "align": "left"})
                        cols += [{"name": "rule", "label": "Rule", "field": "rule", "align": "left"},
                                 {"name": "affected", "label": "Affected", "field": "affected", "align": "left"}]
                        rows = [{**i, "id": n} for n, i in enumerate(shown)]
                        tbl = ui.table(rows=rows, columns=cols, row_key="id", pagination={"rowsPerPage": 25}) \
                            .classes("or-table").props("flat dense wrap-cells")
                        tbl.add_slot("body-cell-severity", r'''<q-td :props="props">
                            <span :class="'or-badge ' + ({error:'err', warning:'warn', info:'info'}[props.value])">
                            {{ {error:'Error', warning:'Warning', info:'Info'}[props.value] }}</span></q-td>''')
                        tbl.add_slot("body-cell-affected",
                                     r'''<q-td :props="props"><span class="or-mono" style="font-size:12px">{{ props.value }}</span></q-td>''')
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(f"{len(shown)} of {len(all_issues)} shown").classes("or-hint")
                        if res.task == "site" and res.index and not many:
                            ui.button("Open full quality report", on_click=lambda: open_result(res.index, "#quality")) \
                                .props("flat dense no-caps")
                        elif res.task in ("check", "interop"):
                            ui.button("Open report (JSON)", on_click=lambda: open_result(res.index or str(res.output))) \
                                .props("flat dense no-caps")

        def signature() -> tuple:
            return (state["running"], state["active"], state["done"], state["folder_pos"], id(state["last"]))

        seen = {"sig": signature(), "log": len(state["log"])}

        def sync() -> None:
            """Pick up progress made by the worker thread (also after coming back to this page)."""
            if results.is_deleted:
                return
            lines = state["log"]
            if seen["log"] > len(lines):
                seen["log"] = 0
            for line in lines[seen["log"]:]:
                log_view.push(line)
            seen["log"] = len(lines)
            sig = signature()
            if sig == seen["sig"]:
                return
            finished = seen["sig"][0] and not state["running"]
            seen["sig"] = sig
            if finished:
                refresh()            # e.g. "Previous output here …" now exists
            else:
                show_running()
            render_results()

        ui.timer(0.25, sync)

        async def start(force_review: bool = False) -> None:
            if state["running"]:
                notify("A build is already running.", "warning")
                return
            problems = s.validate()
            if problems:
                for p in problems:
                    notify(p, "warning")
                return
            s.save()
            job = Settings(**asdict(s))           # the form may change while the task runs
            new_build()                           # a new run: the previous result and log go (still in history)
            if job.task in ("site", "single", "markdown", "myst") and not job.is_folder \
                    and not job.source.strip().startswith(("http://", "https://")):
                job = await review_fixes(job, force_review)     # fix first, then document
                if job is None:
                    return
            launch(job)

        async def review_fixes(job: Settings, force: bool = False) -> Settings | None:
            """Fix first, then document: check the ontology and, when there is something to review, open the
            Quality issues page with this build waiting there. Returns the job to build right away, or None."""
            from .fixes import FixSession

            run_btn.disable()
            run_btn.text = "Checking…"
            try:
                ov = {k: v for k, v in job.overrides().items() if k in ("evaluation", "load_imports", "include_individuals",
                                                                         "reason", "competency_questions")}
                session = await run.io_bound(lambda: FixSession(job.source, **ov))
                await run.io_bound(session.precheck)
            except Exception as e:  # noqa: BLE001 - the build itself reports parse errors
                logging.getLogger(__name__).debug("fix review skipped: %s", e)
                return job
            finally:
                run_btn.enable()
                refresh()
            required = session.required_open() if session.cfg.require_metadata else []
            ignored = ignored_ids()
            # anything the Quality issues page can show: fixes, values to type, manual issues
            actionable = [x for x in session.suggestions if not x.required and (x.options or x.fields or x.kind == "M")
                          and session.supported(x) and x.id not in ignored]
            if not required and (not (prefs.fix_review or force) or not actionable):
                if force:
                    notify("No fixes to suggest for this ontology.", "positive")
                    return None
                if prefs.fix_review:
                    left = len([x for x in session.suggestions if x.id not in ignored])
                    notify(f"No issues to review in {Path(job.source).name}; building the docs directly." if not left
                           else f"{Path(job.source).name}: {left} issue(s) cannot be fixed here (e.g. terms from "
                                f"imported files, or ignored); building the docs directly.", "info")
                return job
            SESSION.add_review(session, job)
            others = len(SESSION.reviews) - 1
            if others:
                notify(f"{Path(job.source).name} added to Quality issues; {others} other ontolog"
                       f"{'y is' if others == 1 else 'ies are'} still waiting there.", "info")
            ui.navigate.to("/issues")
            return None

        def launch(job: Settings) -> None:
            state["shown_for"] = s.source        # the form's source (a fixed a-v1 file builds for it too)
            state.update(running=True, steps=_plan(job), active="parse", done=frozenset(), folder_pos="",
                         filter="all")
            state["log"].append(f"$ {job.cli()}")
            background_tasks.create(run_build(job), name="ontoreview-build")
            sync()

        async def run_build(job: Settings) -> None:
            """Runs independently of this view: switching pages does not stop or lose it."""
            SESSION.verbose = job.verbose
            lg.setLevel(logging.DEBUG if job.verbose else logging.INFO)
            try:
                res = await run.io_bound(run_task, job)
            except Exception as e:  # noqa: BLE001
                state["last"] = e
                if prefs.keep_history:
                    record_run(job, None, str(e), limit=prefs.history_limit)
                notify(f"Failed: {e}", "negative")
            else:
                state["last"] = res
                if prefs.keep_history:
                    record_run(job, res, limit=prefs.history_limit)
                failed = len(res.rows) - res.ok
                state["log"].append(f"DONE  {res.ok} of {len(res.rows)} succeeded · {res.seconds:.1f}s")
                notify(f"{res.ok} of {len(res.rows)} succeeded" + (f", {failed} failed" if failed else ""),
                       "positive" if not failed else "warning")
                if (prefs.open_when_done and res.index and res.task not in ("check", "interop") and res.ok
                        and not os.environ.get("NICEGUI_USER_SIMULATION")):
                    webbrowser.open(Path(res.index).resolve().as_uri())
            finally:
                lg.setLevel(logging.INFO)
                SESSION.verbose = False
                state["running"] = False
    
        def save_toml() -> None:
            if not s.source.strip():
                notify("Choose an ontology file or a folder of ontologies first.", "warning")
                return
            target = config_path()
            if target.exists():
                with ui.dialog() as d, ui.card().classes("or-card"):
                    ui.label(f"{target} already exists. Replace it?")
                    with ui.row().classes("justify-end w-full"):
                        ui.button("Cancel", on_click=d.close).props("flat no-caps")
                        ui.button("Replace", color="negative", on_click=lambda: (write(target), d.close())).props("no-caps")
                d.open()
            else:
                write(target)

        def write(target: Path) -> None:
            target.write_text(s.to_toml(), "utf-8")
            notify(f"Saved {target}. The command line and CI can now run: ontoreview build", "positive")

        def load_toml(path: str) -> None:
            try:
                loaded = Settings.from_toml(path)
            except Exception as e:  # noqa: BLE001
                notify(f"Could not read {path}: {e}", "negative")
                return
            for k in ("source", "output", "layout", "languages", "base_url", "reason", "load_imports",
                      "include_individuals", "competency_questions", "previous_version", "robot", "oops", "reasoner"):
                setattr(s, k, getattr(loaded, k))
            refresh()
            notify(f"Loaded {path}", "positive")

        def config_path() -> Path:
            base = s.source_path if s.is_folder else (s.source_path.parent if s.source_path else Path.cwd())
            return base / "ontoreview.toml"

        def edit_config(template: bool = False, path: Path | None = None) -> None:
            from .config import CONFIG_TEMPLATE, validate_config_text

            if not s.source.strip() and path is None:
                notify("Choose an ontology file or folder first; the config is saved next to it.", "warning")
                return
            path = path or config_path()
            exists = path.exists()
            if template or not exists:
                src_rel = (s.source_path.name if s.source_path and not s.is_folder else ".") if s.source_path else s.source
                text = CONFIG_TEMPLATE.format(source=src_rel)
            else:
                text = path.read_text("utf-8")
            with ui.dialog().props("maximized=false") as dlg, \
                    ui.card().classes("or-card").style("width: min(900px, 96vw); max-width: 96vw"):
                with ui.row().classes("w-full items-start justify-between no-wrap"):
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label("ontoreview.toml").classes("or-h2")
                        ui.label(str(path) + ("" if exists else "  (new file)")).classes("or-hint or-mono ellipsis")
                    ui.button(icon="close", on_click=dlg.close).props('flat round dense aria-label="Close"')
                ui.label("This file keeps the build settings with your ontology. `ontoreview build`, "
                         "`ontoreview check`, CI and this app all read it; paths are relative to the file. "
                         "Options set here override your Settings (which are personal defaults on this computer).") \
                    .classes("or-hint")
                editor = ui.codemirror(text, language="TOML", theme="basicDark" if dark.value else "basicLight",
                                       line_wrapping=True).classes("w-full").style("height: 52vh; border: 1px solid var(--or-line); border-radius: 8px")
                status = ui.label().classes("or-hint").props('aria-live="polite"')

                def check() -> bool:
                    problems = validate_config_text(editor.value, path.parent)
                    if problems:
                        status.text = "✗ " + "; ".join(problems[:3])
                        status.classes(replace="text-negative or-hint")
                        return False
                    status.text = "✓ Valid configuration"
                    status.classes(replace="text-positive or-hint")
                    return True

                def save(use: bool) -> None:
                    if not check():
                        notify("Fix the problems before saving.", "warning")
                        return
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(editor.value, "utf-8")
                    notify(f"Saved {path}", "positive")
                    if use:
                        load_toml(str(path))
                    dlg.close()

                with ui.row().classes("w-full items-center justify-between"):
                    ui.button("Check", icon="rule", on_click=check).props("flat no-caps")
                    with ui.row().classes("gap-2"):
                        ui.button("Cancel", on_click=dlg.close).props("outline no-caps")
                        ui.button("Save", on_click=lambda: save(False)).props("outline no-caps")
                        ui.button("Save and use for this build", on_click=lambda: save(True)) \
                            .props("unelevated no-caps").mark("config-save-use")
            dlg.open()
            check()

        def on_drop_done(a: dict) -> None:
            target = dropped_path(a, drop_info)
            if target:
                set_source(target)
                notify(f"Ready: {Path(target).name}", "positive")

        drop_targets.clear()
        drop_targets["source"] = (lambda a: setattr(drop_info, "text", f"Copying {a.get('count', 0)} file(s)…"),
                                  on_drop_done)
        ready.append(True)
        refresh()
        render_results()
        if state.pop("autostart", False):      # "Run again" from Run history
            ui.timer(0.2, start, once=True)
        pending = state.pop("pending_job", None)  # from the Quality issues page: build what was reviewed
        if pending is not None:
            ui.timer(0.1, lambda: launch(pending), once=True)

    # ------------------------------------------------------------------ Run history
    def history_view() -> None:
        set_active("history")
        head = page_head("Run history", "Every build and check you've run — reopen, re-run or clean up.")
        with head:
            ui.button("Clear history…", on_click=lambda: confirm_clear()).props("outline no-caps color=negative")
        filt = {"text": "", "kind": "all", "hide": True}
        with ui.element("div").classes("or-body column gap-4"):
            with ui.card().classes("or-card w-full").props("flat"):
                with ui.row().classes("or-sec items-center gap-3"):
                    search = ui.input(placeholder="Search by ontology or output path",
                                      on_change=lambda e: (filt.__setitem__("text", e.value or ""), table.refresh())) \
                        .props('outlined dense clearable aria-label="Search runs"').classes("grow min-w-[16rem]")
                    search.add_slot("prepend", '<q-icon name="search" />')
                    seg_box = ui.element("div")
                    ui.checkbox("Hide runs whose output was deleted", value=True,
                                on_change=lambda e: (filt.__setitem__("hide", e.value), table.refresh()))
            with ui.card().classes("or-card w-full").props("flat"):
                table_box = ui.column().classes("w-full gap-0")

        def render_seg() -> None:
            seg_box.clear()
            with seg_box:
                segmented((("all", "All"), ("docs", "Documentation"), ("check", "Checks"), ("diff", "Comparisons")), filt["kind"],
                          lambda k: (filt.__setitem__("kind", k), render_seg(), table.refresh()), "Task")

        @ui.refreshable
        def table() -> None:
            entries = load_history()
            shown = [e for e in entries
                     if (filt["kind"] == "all" or task_kind(e.task) == filt["kind"]) and e.matches(filt["text"])
                     and (e.exists or not filt["hide"] or e.failed)]
            if not entries:
                with ui.column().classes("or-sec items-center text-center q-py-xl gap-2"):
                    ui.icon("history", size="40px").classes("or-muted")
                    ui.label("No runs yet").classes("or-h2")
                    ui.label("Builds and checks you start appear here.").classes("or-hint")
                return
            rows = [{"id": e.id, "status": "failed" if e.failed else ("ok" if e.exists else "gone"),
                     "name": run_name(e), "out": e.output, "task": TASKS.get(e.task, e.task),
                     "issues": issues_text(e), "when": when_text(e.when), "index": e.index or "",
                     "exists": e.exists, "site": e.task == "site" and not e.failed,
                     "deployed": (e.deploys[0].get("when", "")[:10] if e.deploys else ""),
                     "fixed": e.fixed_note} for e in shown]
            tbl = ui.table(rows=rows, row_key="id", pagination={"rowsPerPage": 20}, columns=[
                {"name": "status", "label": "Status", "field": "status", "align": "left"},
                {"name": "name", "label": "Ontology", "field": "name", "align": "left"},
                {"name": "task", "label": "Task", "field": "task", "align": "left"},
                {"name": "issues", "label": "Issues", "field": "issues", "align": "left"},
                {"name": "when", "label": "When", "field": "when", "align": "left"},
                {"name": "act", "label": "Actions", "field": "id", "align": "right"}]) \
                .classes("or-table").props("flat wrap-cells")
            tbl.add_slot("body-cell-status", r'''<q-td :props="props">
                <span v-if="props.value === 'ok'" class="or-badge ok">Succeeded</span>
                <span v-else-if="props.value === 'failed'" class="or-badge err">Failed</span>
                <span v-else class="or-badge off">Output deleted</span></q-td>''')
            tbl.add_slot("body-cell-name", r'''<q-td :props="props"><div class="text-weight-medium">{{ props.value }}</div>
                <div v-if="props.row.fixed" class="or-hint" style="color: var(--q-positive)">✓ {{ props.row.fixed }}</div>
                <div class="or-hint or-mono">→ {{ props.row.out }}</div></q-td>''')
            tbl.add_slot("body-cell-act", r'''<q-td :props="props" class="text-no-wrap">
                <q-btn flat round dense size="sm" icon="tune"
                  aria-label="View configuration" @click.stop="() => $parent.$emit('details', props.row)"><q-tooltip>View configuration, edit and re-run</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="open_in_new" :disable="!props.row.index || !props.row.exists"
                  aria-label="Open output" @click.stop="() => $parent.$emit('open', props.row)"><q-tooltip>Open output</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="download" :disable="!props.row.exists"
                  aria-label="Export output" @click.stop="() => $parent.$emit('export', props.row)"><q-tooltip>Export output (folders as .zip)</q-tooltip></q-btn>
                <q-btn v-if="props.row.site" flat round dense size="sm" icon="cloud_upload" :disable="!props.row.exists"
                  aria-label="Deploy to GitHub Pages" @click.stop="() => $parent.$emit('deploy', props.row)"><q-tooltip>Deploy to GitHub Pages{{ props.row.deployed ? ' (deployed ' + props.row.deployed + ')' : '' }}</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="folder_open" :disable="!props.row.exists"
                  aria-label="Show in folder" @click.stop="() => $parent.$emit('reveal', props.row)"><q-tooltip>Show in folder</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="delete_outline" color="negative"
                  aria-label="Remove from history" @click.stop="() => $parent.$emit('forget', props.row)"><q-tooltip>Remove from history (files are kept)</q-tooltip></q-btn>
                </q-td>''')
            by_id = {e.id: e for e in shown}
            tbl.on("open", lambda e: open_result(e.args.get("index")))
            tbl.on("reveal", lambda e: reveal(e.args.get("out")))
            tbl.on("details", lambda e: details(by_id[e.args["id"]]))
            tbl.on("export", lambda e: export(by_id[e.args["id"]].output))
            tbl.on("deploy", lambda e: deploy_dialog(by_id[e.args["id"]].output))
            tbl.on("rowClick", lambda e: details(by_id[e.args[1]["id"]]))
            tbl.props("row-click-cursor").classes("or-clickable-rows")
            tbl.on("forget", lambda e: (forget_run(e.args["id"]), table.refresh()))
            with ui.row().classes("w-full justify-between q-px-md q-py-sm"):
                ui.label(f"{len(shown)} of {len(entries)} runs shown").classes("or-hint")

        def rerun(entry, now: bool = False) -> None:
            """Load a run's settings into the form: to edit them (``now`` False) or to run at once."""
            if entry.task == "diff":
                cmp.update(old=entry.settings.get("previous_version", ""), new=entry.settings.get("source", ""),
                           output=entry.settings.get("output", ""), last=None, done=None)
                ui.navigate.to("/compare")
                notify("Both versions loaded; comparing again.")
                return
            known = set(vars(Settings()))
            for k, v in entry.settings.items():
                if k in known:
                    setattr(s, k, v)
            prefs.apply(s)
            s.save()
            if now:
                state["autostart"] = True
            ui.navigate.to("/")
            notify("Running again with the settings of that run." if now else
                   "Settings from that run loaded. Change what you need, then press "
                   + {"check": "Run checks", "interop": "Run checks"}.get(entry.task, "Build docs") + ".")

        def details(entry) -> None:
            known = set(vars(Settings()))
            cli = Settings(**{k: v for k, v in entry.settings.items() if k in known}).cli()
            with ui.dialog() as d, ui.card().classes("or-card").style(
                    "width:min(46rem,94vw);max-width:94vw;max-height:90vh;overflow-y:auto"):
                with ui.row().classes("w-full items-start justify-between no-wrap"):
                    with ui.column().classes("gap-0"):
                        ui.label(run_name(entry)).classes("or-h2")
                        ui.label(f"{TASKS.get(entry.task, entry.task)} · {when_text(entry.when)} · "
                                 + ("failed" if entry.failed else issues_text(entry))).classes("or-hint")
                    ui.button(icon="close", on_click=d.close).props('flat round dense aria-label="Close"')
                if entry.failed:
                    ui.label(entry.failed).classes("or-hint text-negative")
                if entry.fixed_note:
                    ui.label("✓ " + entry.fixed_note).classes("or-hint").style("color: var(--q-positive)")
                ui.label("Configuration").classes("or-hint text-uppercase q-mt-sm").style("letter-spacing:.6px")
                with ui.element("dl").classes("or-config w-full"):
                    for k, v in run_config_rows(entry.settings):
                        with ui.element("div").classes("row no-wrap gap-3 q-py-xs"):
                            with ui.element("dt").classes("or-hint").style("min-width:12rem"):
                                ui.label(k)
                            with ui.element("dd").classes("q-ma-none or-mono").style("word-break:break-all"):
                                ui.label(str(v))
                ui.label("Command line").classes("or-hint text-uppercase q-mt-sm").style("letter-spacing:.6px")
                ui.code(cli, language="bash").classes("w-full")
                ui.label("This run's output: " + entry.output + ("" if entry.exists else " (deleted)")) \
                    .classes("or-hint or-mono").style("word-break:break-all")
                with ui.row().classes("w-full justify-end gap-2 q-mt-sm"):
                    if entry.task == "site" and entry.exists and not entry.failed:
                        ui.button("Deploy", icon="cloud_upload", on_click=lambda: (d.close(), deploy_dialog(entry.output))) \
                            .props("outline no-caps").tooltip("Publish this website on GitHub Pages")
                    ui.button("Export", icon="download", on_click=lambda: export(entry.output)) \
                        .props("outline no-caps").set_enabled(entry.exists)
                    ui.button("Edit and run", icon="edit", on_click=lambda: (d.close(), rerun(entry))) \
                        .props("outline no-caps").tooltip("Load this configuration into the form to change it")
                    ui.button("Run again", icon="replay", on_click=lambda: (d.close(), rerun(entry, now=True))) \
                        .props("unelevated no-caps")
            d.open()

        def confirm_clear() -> None:
            with ui.dialog() as d, ui.card().classes("or-card"):
                ui.label("Clear the run history?").classes("or-h2")
                ui.label("Only the list is cleared; generated files stay where they are.").classes("or-hint")
                with ui.row().classes("justify-end w-full"):
                    ui.button("Cancel", on_click=d.close).props("flat no-caps")
                    ui.button("Clear history", color="negative",
                              on_click=lambda: (clear_history(), table.refresh(), d.close())).props("no-caps")
            d.open()

        render_seg()
        with table_box:
            table()

    # ------------------------------------------------------------------ Settings
    def settings_view() -> None:  # noqa: C901
        set_active("settings")
        work = Prefs(**asdict(prefs))
        page_head("Settings", "Your defaults for every build on this computer. A project's ontoreview.toml "
                              "(Build › Project config) overrides them and is shared with the CLI, CI and teammates.")
        with ui.element("div").classes("w-full").style(
                "background: var(--or-card); border-bottom: 1px solid var(--or-line); padding: 0 24px"):
            with ui.tabs().props("no-caps align=left active-color=primary indicator-color=primary") as tabs:
                t_general = ui.tab("General")
                t_docs = ui.tab("Documentation")
                t_checks = ui.tab("Quality checks")
                t_ai = ui.tab("AI & fixes")
                t_look = ui.tab("Appearance")
                t_tel = ui.tab("Telemetry")
            tabs.on_value_change(lambda e: telemetry.note_settings_tab(str(getattr(e.value, "_props", {}).get("name", e.value)).lower()))

        def row(label: str, hint: str = ""):
            r = ui.row().classes("w-full items-center gap-4 q-py-md no-wrap max-sm:flex-wrap or-setrow") \
                .style("border-bottom: 1px solid var(--or-line-2)")
            with r:
                with ui.column().classes("gap-0").style("flex: 1 1 320px"):
                    ui.label(label).classes("or-label")
                    if hint:
                        ui.label(hint).classes("or-hint")
            return r

        def telemetry_panel() -> None:
            """Settings › Telemetry: the optional-details switch and the table of everything that can be sent."""
            reason = telemetry.disabled_reason()
            locked = telemetry.details_env_locked()
            with ui.card().classes("or-card w-full").props("flat"):
                with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                    ui.label("Usage statistics").classes("or-h2 q-pt-md")
                    ui.html(
                        '<div class="or-hint" style="line-height:1.55">OntoReview sends anonymous usage statistics '
                        "to PostHog (US) so we can see how many people actually use it (not just download it), "
                        "where, and which commands and quality checks work for them. "
                        "<b>Mandatory</b> statistics are part of every event while telemetry is on; <b>optional</b> "
                        "details are on by default and can be turned off on their own. You can also turn telemetry "
                        "off completely. Nothing about your ontologies, files or keys is ever sent. "
                        "<br>These settings cover the app, the <code>ontoreview</code> command and the Python API "
                        "(<code>import ontoreview</code>): they are one setting for this user on this computer, so "
                        "a change here also applies on the command line, and the other way round. "
                        "See Help › Telemetry for why.</div>", sanitize=False)
                    env_off = bool(reason) and not reason.startswith("switched off")

                    def toggle_all(e) -> None:
                        telemetry.set_enabled(bool(e.value))
                        notify("Telemetry " + ("on" if e.value else "off: nothing is sent from this computer"),
                               "positive")
                        ui.navigate.reload()

                    with row("Send usage statistics",
                             "Everything on this page, mandatory and optional. Off: nothing is sent from this "
                             "computer, from the app, the command line or Python (events not sent yet are "
                             "discarded). The command line: ontoreview telemetry off / on."
                             + (f" Off here: {reason}." if env_off else "")):
                        all_sw = ui.switch(value=not reason, on_change=toggle_all) \
                            .props('aria-label="Send usage statistics"').mark("telemetry-all")
                        if env_off:
                            all_sw.disable()
                    with row("Status"):
                        ui.label(f"Off: {reason}" if reason else f"On · sent to {telemetry.HOST}") \
                            .classes("or-mono").style("flex: 1 1 320px")

                    def toggle(e) -> None:
                        telemetry.set_details(bool(e.value))
                        notify("Optional telemetry details " + ("on" if e.value else "off: only the mandatory "
                                                                 "usage statistics are sent"), "positive")
                        tel_table.refresh()

                    with row("Share optional details",
                             "Check status, ontology size buckets, finding counts, documentation options, AI "
                             "provider and the pages you visit. Applies immediately. The command line: "
                             "ontoreview telemetry disable / enable."
                             + (" Switched off by ONTOREVIEW_TELEMETRY_DETAILS=0." if locked else "")):
                        sw = ui.switch(value=telemetry.details_enabled(), on_change=toggle) \
                            .props('aria-label="Share optional telemetry details"').mark("telemetry-details")
                        if locked or reason:
                            sw.disable()
                    with row("For CI and shared machines", "Set DO_NOT_TRACK=1 in the environment to turn "
                                                           "everything off without changing a setting."):
                        ui.label("DO_NOT_TRACK=1").classes("or-mono")

            @ui.refreshable
            def tel_table() -> None:
                on = telemetry.details_enabled()
                rows = [{"id": p.name, "name": p.name,
                         "tier": "Mandatory" if p.tier == "mandatory" else ("Optional · on" if on else "Optional · off"),
                         "events": p.events, "example": p.example, "purpose": p.purpose} for p in telemetry.SPEC]
                tbl = ui.table(rows=rows, row_key="id", pagination={"rowsPerPage": 0}, columns=[
                    {"name": "name", "label": "Property", "field": "name", "align": "left"},
                    {"name": "tier", "label": "Tier", "field": "tier", "align": "left"},
                    {"name": "events", "label": "Sent with", "field": "events", "align": "left"},
                    {"name": "example", "label": "Example values", "field": "example", "align": "left"},
                    {"name": "purpose", "label": "Why we collect it", "field": "purpose", "align": "left"},
                ]).classes("or-table").props("flat dense wrap-cells hide-bottom").mark("telemetry-table")
                tbl.add_slot("body-cell-tier", r'''
                    <q-td :props="props">
                      <span :class="'or-badge ' + (props.value === 'Mandatory' ? 'info' : (props.value.endsWith('on') ? 'ok' : 'off'))">
                        {{ props.value }}</span>
                    </q-td>''')
                tbl.add_slot("body-cell-name", r'''
                    <q-td :props="props"><code>{{ props.value }}</code></q-td>''')

            with ui.card().classes("or-card w-full q-mt-md").props("flat"):
                with ui.column().classes("w-full gap-2").style("padding: 12px 24px 20px"):
                    ui.label("What is sent").classes("or-h2")
                    ui.label("Three kinds of event: one per command, app task or Python process (run_completed), "
                             "one per app session (ui_session) and one per new user (install_first_seen). Numbers "
                             "are rounded into ranges; at most 30 events a day are sent from one computer; CI runs "
                             "(GitHub Actions and others) are sampled, 1 in 10, and the Python API is not tracked "
                             "in CI or test suites.").classes("or-hint")
                    tel_table()
                    ui.html('<div class="or-hint" style="line-height:1.55"><b>Never sent:</b> '
                            + "; ".join(telemetry.NEVER_SENT) + ".</div>", sanitize=False)
            with ui.card().classes("or-card w-full q-mt-md").props("flat"):
                with ui.column().classes("w-full gap-2").style("padding: 12px 24px 20px"):
                    ui.label("Command line").classes("or-h2")
                    ui.label("The same switches without the app (they change the same setting).").classes("or-hint")
                    cmds = [("ontoreview telemetry status", "Whether telemetry and the optional details are on"),
                            ("ontoreview telemetry show [--last]", "This table; --last adds the events sent from here"),
                            ("ontoreview telemetry disable / enable", "Optional details off / on"),
                            ("ontoreview telemetry off / on", "All telemetry off / on (unsent events are discarded)"),
                            ("DO_NOT_TRACK=1", "Environment variable: nothing is sent (CI, shared machines)"),
                            ("ONTOREVIEW_TELEMETRY_DETAILS=0", "Environment variable: no optional details")]
                    ui.html('<table class="or-hint" style="border-collapse:collapse;line-height:1.7">' + "".join(
                        f'<tr><td style="padding-right:18px"><code>{c}</code></td><td>{d}</td></tr>'
                        for c, d in cmds) + "</table>", sanitize=False).mark("telemetry-cli")
            with ui.card().classes("or-card w-full q-mt-md").props("flat"):
                with ui.column().classes("w-full gap-2").style("padding: 12px 24px 20px"):
                    ui.label("Sent from this computer").classes("or-h2")
                    last = telemetry.last_events()
                    ui.label(f"Install id {telemetry.install_id() if not reason else '(none: telemetry is off)'} · "
                             f"the last {len(last)} event(s), exactly as sent.").classes("or-hint or-mono")
                    if last:
                        with ui.expansion("Show the last events").classes("w-full"):
                            ui.code(json.dumps(last, indent=2), language="json").classes("w-full")

        with ui.element("div").classes("or-body").style("padding-top: 16px"):
            start_tab = {"general": t_general, "docs": t_docs, "checks": t_checks, "ai": t_ai, "look": t_look,
                         "telemetry": t_tel} \
                .get(state.pop("settings_tab", "general"), t_general)
            tabs.set_value(start_tab)
            with ui.tab_panels(tabs, value=start_tab, animated=False).classes("w-full").style("background: transparent"):
                with ui.tab_panel(t_general).classes("q-pa-none"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                            with row("Default output folder", 'Used when "Save to" is left empty. Empty: next to the ontology.'):
                                with ui.row().classes("no-wrap gap-2").style("flex: 1 1 320px"):
                                    dout = ui.input(placeholder="next to the ontology").bind_value(work, "default_output") \
                                        .props('outlined dense clearable aria-label="Default output folder"').classes("grow or-mono")
                                    ui.button("Browse…", on_click=lambda: pick("any", lambda p: dout.set_value(p), True,
                                                                               work.default_output, "Default output folder")) \
                                        .props("outline no-caps")
                            with row("Default format", "Pre-selected on the Build screen."):
                                ui.select({f[0]: f[1] for f in FORMATS}).bind_value(work, "default_task") \
                                    .props('outlined dense aria-label="Default format"').style("flex: 1 1 320px")
                            with row("Open docs when a build finishes", "Opens index.html in your browser."):
                                ui.checkbox().bind_value(work, "open_when_done").props('aria-label="Open docs when a build finishes"')
                            with row("Keep run history", "Stored locally on this computer."):
                                ui.checkbox().bind_value(work, "keep_history").props('aria-label="Keep run history"')
                            with row("Remember the last"):
                                with ui.row().classes("items-center gap-2").style("flex: 1 1 320px"):
                                    ui.number(min=1, max=1000, step=10, format="%d").bind_value(
                                        work, "history_limit", forward=lambda v: int(v or 50)) \
                                        .props('outlined dense aria-label="Number of runs to remember"').classes("w-28")
                                    ui.label("runs").classes("or-hint")
                    with ui.card().classes("or-card w-full q-mt-md").props("flat"):
                        with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                            ui.label("Publishing (GitHub Pages)").classes("or-h2 q-pt-md")
                            ui.label("Used by Deploy on website results and in Run history.").classes("or-hint")
                            with row("GitHub token (optional)",
                                     "Lets OntoReview push and turn on Pages without other tools, and create the "
                                     "repository if you allow it. Kept on this computer only; never in reports or "
                                     "the history. Without it, your git login (gh auth login, credential helper, "
                                     "SSH) is used."):
                                with ui.column().classes("gap-1").style("flex: 1 1 320px"):
                                    with ui.row().classes("no-wrap gap-2 w-full"):
                                        ui.input(password=True, password_toggle_button=True) \
                                            .bind_value(work, "deploy_token").mark("deploy-token") \
                                            .props('outlined dense clearable autocomplete="off" aria-label="GitHub token"') \
                                            .classes("grow or-mono")
                                        tok_btn = ui.button("Check token").props("outline no-caps")
                                    tok_info = ui.label().classes("or-hint").style("word-break:break-word")
                                    ui.html(
                                        '<div class="or-hint" style="line-height:1.5"><b>You choose what it can reach.</b> '
                                        '<a class="text-primary" href="https://github.com/settings/personal-access-tokens/new" target="_blank" '
                                        'rel="noopener">Fine-grained token</a> (recommended), Repository access:'
                                        '<ul style="margin:.2em 0 .3em 1.1em;padding:0">'
                                        '<li><b>Only select repositories</b>: just the docs repositories you pick. '
                                        'Create the repository on GitHub first; OntoReview pushes to it.</li>'
                                        '<li><b>All repositories</b>: also lets OntoReview create new repositories '
                                        'for you.</li></ul>'
                                        'Permissions: Contents, Pages, Workflows and Administration: read '
                                        'and write (Administration lets it create repositories and allow your '
                                        'branch to deploy to Pages). '
                                        'Or a <a class="text-primary" href="https://github.com/settings/tokens/new?scopes=repo,workflow&amp;'
                                        'description=OntoReview%20deploy" target="_blank" rel="noopener">classic '
                                        'token</a> with the repo and workflow scopes (all your repositories). Set an '
                                        'expiry date; revoke it on GitHub any time.</div>', sanitize=False)

                                    async def check_token() -> None:
                                        from .publish.github import token_status
                                        if not (work.deploy_token or "").strip():
                                            tok_info.text = "Paste a token first."
                                            return
                                        tok_info.text = "Checking…"
                                        try:
                                            tok_info.text = await run.io_bound(token_status, work.deploy_token)
                                        except Exception as e:  # noqa: BLE001
                                            tok_info.text = str(e)
                                    tok_btn.on_click(check_token)
                            with row("Repository", "Pre-filled in the Deploy dialog."):
                                ui.input(placeholder="https://github.com/you/ontology-docs") \
                                    .bind_value(work, "deploy_remote") \
                                    .props('outlined dense clearable aria-label="Default repository"') \
                                    .classes("or-mono").style("flex: 1 1 320px")
                            with row("Branch", "The workflow publishes from this branch."):
                                ui.input().bind_value(work, "deploy_branch") \
                                    .props('outlined dense aria-label="Branch"').classes("w-40 or-mono")
                            with row("Create the repository if it does not exist", "Needs the token."):
                                ui.checkbox().bind_value(work, "deploy_create").props('aria-label="Create the repository"')
                            with row("New repositories are private", "GitHub Pages on private repositories needs a paid "
                                                                     "GitHub plan; the site itself is public either way."):
                                ui.checkbox().bind_value(work, "deploy_private").props('aria-label="Private repository"')
                with ui.tab_panel(t_docs).classes("q-pa-none"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                            with row("Layout", "One long page, or one page per section."):
                                ui.select({"single": "One page", "multi": "One page per section"}) \
                                    .bind_value(work, "layout").props('outlined dense aria-label="Layout"')
                            with row("Languages", "Comma-separated, e.g. en, es. The first is the default; "
                                                  "each gets its own site."):
                                ui.input().bind_value(work, "languages").props('outlined dense aria-label="Languages"')
                            with row("Public URL (base_url)", "Where the docs will be published; used for "
                                                              "canonical links and llms.txt."):
                                ui.input(placeholder="https://w3id.org/my-ontology").bind_value(work, "base_url") \
                                    .props('outlined dense clearable aria-label="Public URL"').classes("or-mono")
                            with row("Load owl:imports", "Follow imports so imported terms resolve."):
                                ui.checkbox().bind_value(work, "load_imports").props('aria-label="Load owl:imports"')
                            with row("Document individuals", "Include named individuals in the reference."):
                                ui.checkbox().bind_value(work, "include_individuals") \
                                    .props('aria-label="Document individuals"')
                            with row("Inferred superclasses", "Run a reasoner (needs owlrl) and show inferred "
                                                              "superclasses."):
                                ui.checkbox().bind_value(work, "reason").props('aria-label="Inferred superclasses"')
                            with row("Competency questions", "YAML, CSV/TSV or Excel file(s), comma-separated. "
                                                             "Used for single-ontology builds."):
                                with ui.row().classes("no-wrap gap-2"):
                                    cqw = ui.input().bind_value(work, "competency_questions") \
                                        .props('outlined dense clearable aria-label="Competency questions"').classes("grow or-mono")
                                    ui.button("Browse…", on_click=lambda: pick(
                                        "cq", lambda p: cqw.set_value(", ".join(x for x in (work.competency_questions, p) if x)),
                                        False, title="Choose a competency questions file")).props("outline no-caps")
                            with row("Previous version", "An older release to compare against for the changelog. "
                                                         "Used for single-ontology builds."):
                                with ui.row().classes("no-wrap gap-2"):
                                    pvw = ui.input().bind_value(work, "previous_version") \
                                        .props('outlined dense clearable aria-label="Previous version"').classes("grow or-mono")
                                    ui.button("Browse…", on_click=lambda: pick(
                                        "ontology", lambda p: pvw.set_value(p), False, title="Choose the previous version")) \
                                        .props("outline no-caps")
                            with row("Verbose log", "Show debug messages in the build log."):
                                ui.checkbox().bind_value(work, "verbose").props('aria-label="Verbose log"')
                with ui.tab_panel(t_checks).classes("q-pa-none").style(
                        "display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px;align-items:start"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label("ROBOT").classes("or-h2")
                                robot_badge = ui.html("", sanitize=False)
                            ui.label("Run ROBOT with").classes("or-label")
                            mode_box = ui.row().classes("w-full gap-3 no-wrap max-sm:flex-wrap") \
                                .props('role="radiogroup" aria-label="Run ROBOT with"')
                            img_row = ui.column().classes("w-full gap-1")
                            with img_row:
                                ui.label("Docker image").classes("or-label")
                                with ui.row().classes("w-full no-wrap gap-2"):
                                    ui.input().bind_value(work, "robot_image") \
                                        .props('outlined dense aria-label="Docker image"').classes("grow or-mono")
                                    ui.button("Test", on_click=lambda: test_robot()).props("outline no-caps")
                            path_row = ui.column().classes("w-full gap-1")
                            with path_row:
                                ui.label("robot command").classes("or-label")
                                with ui.row().classes("w-full no-wrap gap-2"):
                                    ui.input(placeholder="robot (on PATH)").bind_value(work, "robot_path") \
                                        .props('outlined dense aria-label="robot command"').classes("grow or-mono")
                                    ui.button("Test", on_click=lambda: test_robot()).props("outline no-caps")
                            ui.checkbox("Run ROBOT by default").bind_value(work, "robot_enabled")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("Logical consistency").classes("or-h2")
                            ui.label("An OWL reasoner checks that the ontology is consistent and that every class "
                                     "can have members. It runs through ROBOT (above), on this machine.") \
                                .classes("or-hint")
                            ui.label("Reasoner").classes("or-label")
                            ui.select(REASONER_CHOICES).bind_value(work, "reasoner") \
                                .props('outlined dense aria-label="Reasoner"').classes("w-72").mark("reasoner")
                            ui.label("HermiT is complete for OWL 2 DL but can be slow on very large ontologies; "
                                     "ELK is fast but only understands OWL 2 EL, so it can miss problems.") \
                                .classes("or-hint")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("IRI checks").classes("or-h2")
                            ui.label("IRI syntax, the ontology header and version IRI, whether the ontology IRI "
                                     "resolves, and whether reused classes and properties exist in their vocabulary. "
                                     "Terms are looked up in SQLite first (bundled W3C vocabularies and your cache), "
                                     "then OLS, BioPortal and a direct download.").classes("or-hint")
                            ui.checkbox("Run IRI checks").bind_value(work, "iri_checks").mark("iri-checks")
                            ui.checkbox("Allow network lookups").bind_value(work, "iri_network")
                            ui.label("Off: only the bundled and cached SQLite database is used; unknown terms are "
                                     "reported as unverified. Only external term IRIs are sent, never your ontology.") \
                                .classes("or-hint")
                            ui.checkbox("Ask OLS and BioPortal").bind_value(work, "iri_repositories")
                            ui.label("BioPortal needs the BIOPORTAL_API_KEY environment variable.").classes("or-hint")
                            ui.checkbox("Check that the ontology IRI resolves").bind_value(work, "iri_resolve")
                            ui.link("Open the term database", "/terms").classes("or-hint text-primary")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("OntoCheck").classes("or-h2")
                            ui.label("Quality metrics for labeling, structure, accessibility and naming conventions, "
                                     "shown as a scorecard in the review. Runs on this machine.").classes("or-hint")
                            ui.checkbox("Run OntoCheck").bind_value(work, "ontocheck").mark("ontocheck")
                            ui.checkbox("Check declared SPARQL endpoints and RDF dumps are reachable").bind_value(
                                work, "ontocheck_network")
                            ui.label("Contacts the URLs listed in the ontology (nothing is uploaded). Each can take up "
                                     "to 10 seconds when a server does not answer.").classes("or-hint")
                            ui.label("Class search term").classes("or-label")
                            ui.input(placeholder="e.g. Person (optional)").bind_value(work, "ontocheck_search") \
                                .props('outlined dense clearable aria-label="Class search term"').classes("w-72")
                            ui.label("For the searchClass metric: lists classes whose name contains this text.") \
                                .classes("or-hint")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("Cross-domain interoperability").classes("or-h2")
                            ui.label("Scores how well the ontology aligns with ontologies from other domains "
                                     "(Align) and how general its class definitions are (Gen); CDI combines "
                                     "both.").classes("or-hint")
                            ui.checkbox("Score cross-domain interoperability").bind_value(work, "cdi").mark("cdi")
                            ui.label("Reference ontologies, one per line").classes("or-label")
                            cdi_refs = ui.textarea(placeholder="ols\nols:envo,chebi\nbioportal:NCIT\n"
                                                               "ols@https://service.tib.eu/ts4tib/api\n"
                                                               "https://example.org/other.owl\n/path/to/mappings.sssom.tsv") \
                                .bind_value(work, "cdi_references").mark("cdi-references") \
                                .props('outlined dense autogrow aria-label="Reference ontologies"').classes("w-full or-mono")

                            def add_refs(paths: list[str]) -> None:
                                lines = [x for x in work.cdi_references.splitlines() if x.strip()]
                                cdi_refs.set_value("\n".join(lines + [p for p in paths if p not in lines]))

                            with ui.element("div").props('data-zone="cdi"').classes("ob-dropzone w-full"):
                                with ui.row().classes("w-full items-center no-wrap gap-2"):
                                    ui.icon("upload_file", size="20px").classes("text-primary")
                                    cdi_drop = ui.label("Drop reference ontologies or SSSOM mapping files here "
                                                        "(several at once)").classes("or-hint grow")
                                    ui.button("Browse…", on_click=lambda: pick(
                                        "any", lambda p: add_refs([p]), False,
                                        title="Choose a reference ontology or SSSOM file")).props("outline no-caps")
                            repo_picker(add_refs)
                            ui.label("ols / bioportal: find ontologies with matching terms and keep the top N. "
                                     "ols:envo,chebi or bioportal:NCIT: use those. Other OLS or OntoPortal services: "
                                     "ols@URL or ontoportal@URL. Files and URLs: RDF ontologies or SSSOM .tsv. "
                                     "BioPortal needs BIOPORTAL_API_KEY, other OntoPortal services "
                                     "ONTOPORTAL_API_KEY. Repositories receive labels and IRIs, never the "
                                     "ontology file.").classes("or-hint")
                            with ui.row().classes("gap-6 items-end"):
                                with ui.column().classes("gap-1"):
                                    ui.label("Own domain(s)").classes("or-label")
                                    ui.input(placeholder="e.g. agriculture").bind_value(work, "cdi_domains") \
                                        .props('outlined dense clearable aria-label="Own domains"').classes("w-56")
                                with ui.column().classes("gap-1"):
                                    ui.label("Discovered ontologies kept").classes("or-label")
                                    ui.number(min=0, max=100, step=1, format="%d").bind_value(
                                        work, "cdi_top_n", forward=lambda v: int(v or 0)) \
                                        .props('outlined dense aria-label="Discovered ontologies kept"').classes("w-28")
                            ui.label("Discovered ontologies from your own domain(s) are left out; comma-separated.") \
                                .classes("or-hint")
                            ui.checkbox("Score definition generality with a language model").bind_value(
                                work, "cdi_generality")
                            ui.label("Needs pip install 'ontoreview[cdi]'; the model (about 1.6 GB) is downloaded "
                                     "on first use and runs on this machine. Without it only Align is scored.") \
                                .classes("or-hint")
                            ui.label("Automatic matcher for file and URL references").classes("or-label")
                            ui.select({"sbert": "OntoAligner, sentence embeddings (SBERT)",
                                       "fuzzy": "OntoAligner, fuzzy string matching", "off": "Off"}) \
                                .bind_value(work, "cdi_ontoaligner").mark("cdi-ontoaligner") \
                                .props('outlined dense aria-label="Automatic matcher"').classes("w-80")
                            ui.label("Adds ≡ matches found by OntoAligner (score ≥ 0.8) to the asserted and lexical "
                                     "ones. Needs ontoreview[cdi]; SBERT's embedding model (all-MiniLM-L6-v2, about "
                                     "90 MB) is downloaded automatically on first use. Repositories (OLS, BioPortal) "
                                     "are matched through their search instead.") \
                                .classes("or-hint")
                            with ui.row().classes("gap-6 items-end"):
                                for label, attr in (("BioPortal API key (optional)", "cdi_bioportal_key"),
                                                    ("Other OntoPortal API key (optional)", "cdi_ontoportal_key"),
                                                    ("Hugging Face token (optional)", "hf_token")):
                                    with ui.column().classes("gap-1"):
                                        ui.label(label).classes("or-label")
                                        ui.input(password=True, password_toggle_button=True).bind_value(work, attr) \
                                            .props(f'outlined dense clearable autocomplete="off" aria-label="{label}"') \
                                            .classes("w-64 or-mono").mark(attr)
                            ui.label("Your own key avoids shared rate limits; OntoPortal services (BioPortal, "
                                     "AgroPortal, …) answer only with one, otherwise those references are skipped. "
                                     "OLS needs no key. The Hugging Face token is used to download the language "
                                     "models (higher rate limits, gated models). Left empty: BIOPORTAL_API_KEY / "
                                     "ONTOPORTAL_API_KEY / HF_TOKEN. Keys stay "
                                     "on this machine; they are not written to reports, ontoreview.toml or the "
                                     "command line shown here.").classes("or-hint")

                            def cdi_dropped(a: dict) -> None:
                                files = upload_files(a.get("batch") or "") if a.get("ok") else []
                                if not files:
                                    cdi_drop.text = "Nothing usable was dropped: no ontology or .tsv files found."
                                    notify(cdi_drop.text, "warning")
                                    return
                                add_refs(files)
                                cdi_drop.text = f"Added {len(files)} reference file(s)."

                            drop_targets["cdi"] = (lambda a: setattr(cdi_drop, "text", "Copying…"), cdi_dropped)
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("Scientific interoperability").classes("or-h2")
                            ui.label("Counts the scientific domains (OECD fields of science), other than the "
                                     "ontology's own, in which it is interoperable: for each domain, CDI computed "
                                     "with only that domain's reference ontologies must reach θ_s. Upper-level "
                                     "ontologies (BFO, DOLCE, …) are ignored.").classes("or-hint")
                            ui.checkbox("Score scientific interoperability").bind_value(work, "si").mark("si")
                            si_same = ui.checkbox("Use the cross-domain reference ontologies",
                                                  value=not work.si_references.strip()).mark("si-same-refs")
                            ui.label("Reuses that run, so nothing is fetched twice. Needs the generality model.") \
                                .classes("or-hint")
                            with ui.column().classes("w-full gap-2") as si_refs_box:
                                ui.label("Reference ontologies for scientific interoperability, one per line") \
                                    .classes("or-label")
                                si_refs = ui.textarea(placeholder="ols:envo,chebi\nbioportal:NCIT\n/path/to/ref.owl") \
                                    .bind_value(work, "si_references").mark("si-references") \
                                    .props('outlined dense autogrow aria-label="SI reference ontologies"') \
                                    .classes("w-full or-mono")

                                def add_si_refs(paths: list[str]) -> None:
                                    lines = [x for x in work.si_references.splitlines() if x.strip()]
                                    si_refs.set_value("\n".join(lines + [p for p in paths if p not in lines]))

                                with ui.row().classes("gap-2"):
                                    ui.button("Browse…", icon="upload_file", on_click=lambda: pick(
                                        "any", lambda p: add_si_refs([p]), False,
                                        title="Choose a reference ontology or SSSOM file")).props("outline no-caps")
                                repo_picker(add_si_refs)

                            def si_same_changed(e) -> None:
                                si_refs_box.set_visibility(not e.value)
                                if e.value:
                                    si_refs.set_value("")
                            si_same.on_value_change(si_same_changed)
                            si_refs_box.set_visibility(not si_same.value)
                            from .quality_checks.cdi.si import OECD_FOS
                            with ui.row().classes("gap-6 items-end"):
                                with ui.column().classes("gap-1"):
                                    ui.label("Own scientific domain").classes("or-label")
                                    ui.select({"": "Detect from title and description",
                                               **{c: f"{c} {n}" for c, n in OECD_FOS.items()}}) \
                                        .bind_value(work, "si_home_domain").mark("si-home-domain") \
                                        .props('outlined dense aria-label="Own scientific domain"').classes("w-96")
                                with ui.column().classes("gap-1"):
                                    ui.label("θ_s").classes("or-label")
                                    ui.number(min=0, max=1, step=0.05, format="%.2f").bind_value(
                                        work, "si_theta_s", forward=lambda v: float(0.3 if v is None else v)) \
                                        .props('outlined dense aria-label="Threshold theta s"').classes("w-28")
                            ui.label("Your own domain is never counted. θ_s: a domain counts as covered when its "
                                     "CDI reaches this (default 0.3).").classes("or-hint")
                            ui.label("Domain of a reference ontology (optional)").classes("or-label")
                            domain_rows(lambda: work.si_domain_map, lambda v: setattr(work, "si_domain_map", v))
                            ui.label("Reference ontologies get a domain from repository metadata, else from a "
                                     "classifier reading their title and description. A line here overrides both; "
                                     "the review lists ontologies left without one.").classes("or-hint")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            with ui.row().classes("w-full items-center justify-between"):
                                ui.label("OOPS!").classes("or-h2")
                                with ui.row().classes("items-center gap-2"):
                                    oops_badge = ui.html("", sanitize=False)
                                    ui.button("Check", on_click=lambda: test_oops()).props("flat dense no-caps")
                            ui.label("Service URL").classes("or-label")
                            ui.input().bind_value(work, "oops_endpoint") \
                                .props('outlined dense aria-label="OOPS! service URL"').classes("w-full or-mono")
                            ui.label("The public OOPS! REST service. Change it only if you run your own OOPS! server.") \
                                .classes("or-hint")
                            with ui.row().classes("gap-6 items-end"):
                                with ui.column().classes("gap-1"):
                                    ui.label("Timeout").classes("or-label")
                                    with ui.row().classes("items-center gap-2"):
                                        ui.number(min=5, max=600, step=5, format="%d").bind_value(
                                            work, "oops_timeout", forward=lambda v: int(v or 90)) \
                                            .props('outlined dense aria-label="Timeout in seconds"').classes("w-28")
                                        ui.label("seconds").classes("or-hint")
                                with ui.column().classes("gap-1"):
                                    ui.label("Use OOPS!").classes("or-label")
                                    ui.select(OOPS_CHOICES).bind_value(work, "oops") \
                                        .props('outlined dense aria-label="Use OOPS!"').classes("w-56")
                            ui.label("OOPS! uploads your ontology to an external web service. Turn it off for "
                                     "unpublished or private ontologies.").classes("or-notice")
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2"):
                            ui.label("Quality check only").classes("or-h2")
                            ui.label("When a check run counts as failed (the CLI exits with 1; useful in CI).") \
                                .classes("or-hint")
                            ui.select({"error": "Any error", "warning": "Any warning or error",
                                       "info": "Any finding", "never": "Never"}).bind_value(work, "fail_on") \
                                .props('outlined dense aria-label="Fail on"').classes("w-64")
                with ui.tab_panel(t_ai).classes("q-pa-none"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                            ui.label("Fixes").classes("or-h2 q-pt-md")
                            with row("Review fixes before generating docs",
                                     "After Build docs, show the suggested fixes first: apply some and build from "
                                     "a fixed copy (a-v1.ttl), or skip. The original file is never changed. "
                                     "Required metadata (title, description, license, creators) is always asked."):
                                ui.checkbox().bind_value(work, "fix_review").props('aria-label="Review fixes"')
                    with ui.card().classes("or-card w-full q-mt-md").props("flat"):
                        with ui.column().classes("w-full gap-0").style("padding: 4px 24px"):
                            ui.label("AI drafts").classes("or-h2 q-pt-md")
                            ui.label("Draft definitions for terms without one, refine existing definitions and "
                                     "suggest a description. Every draft is shown with the model that wrote it and "
                                     "applied only when you accept it.").classes("or-hint")
                            with row("Use AI drafts", "Off by default."):
                                ui.checkbox().bind_value(work, "ai_enabled").props('aria-label="Use AI drafts"') \
                                    .mark("ai-enabled")
                            with row("Priority", "The first available source is used; reorder or remove sources. "
                                                 "Local sources keep the ontology on this computer."):
                                prio_box = ui.column().classes("gap-1").style("flex: 1 1 320px")
                            ui.label("Hugging Face (local)").classes("or-label q-mt-md")
                            with row("Model", "Any Hugging Face model; downloaded on first use and run here. Default: "
                                              "Qwen/Qwen3.5-4B (open source, Apache-2.0); Qwen/Qwen3.5-2B for small "
                                              "machines. Needs pip install 'ontoreview[cdi]'."):
                                ui.input().bind_value(work, "ai_hf_model").props('outlined dense aria-label="HF model"') \
                                    .classes("or-mono").style("flex: 1 1 320px")
                            with row("Hugging Face token (optional)", "For gated models and higher download limits. "
                                                                      "Also used by the interoperability models."):
                                ui.input(password=True, password_toggle_button=True).bind_value(work, "hf_token") \
                                    .props('outlined dense clearable autocomplete="off" aria-label="Hugging Face token"') \
                                    .classes("or-mono").style("flex: 1 1 320px")
                            ui.label("Ollama (local)").classes("or-label q-mt-md")
                            with row("Model", "The models installed in your Ollama. If the chosen one is missing, the "
                                              "closest installed model is used (and named in each draft)."):
                                with ui.row().classes("no-wrap gap-2 items-center").style("flex: 1 1 320px"):
                                    ollama_sel = ui.select({work.ai_ollama_model: work.ai_ollama_model},
                                                           value=work.ai_ollama_model, with_input=True,
                                                           new_value_mode="add-unique") \
                                        .bind_value(work, "ai_ollama_model") \
                                        .props('outlined dense aria-label="Ollama model"').classes("grow or-mono") \
                                        .mark("ollama-model")
                                    ui.button(icon="refresh", on_click=lambda: list_ollama()) \
                                        .props('flat round dense aria-label="Refresh installed models"') \
                                        .tooltip("Refresh the installed models")
                            ollama_info = ui.label().classes("or-hint q-pl-sm")
                            with row("Pull a model", "Download another model into Ollama, e.g. qwen3.5:4b, gemma3:4b "
                                                     "or llama3.2:3b (see ollama.com/library)."):
                                with ui.column().classes("gap-1").style("flex: 1 1 320px"):
                                    with ui.row().classes("no-wrap gap-2 w-full"):
                                        pull_in = ui.input(placeholder="qwen3.5:4b") \
                                            .props('outlined dense clearable aria-label="Model to pull"') \
                                            .classes("grow or-mono").mark("ollama-pull-name")
                                        pull_btn = ui.button("Pull", icon="download", on_click=lambda: pull_ollama()) \
                                            .props("outline no-caps").mark("ollama-pull")
                                    pull_prog = ui.linear_progress(value=0, show_value=False).props("rounded size=6px")
                                    pull_msg = ui.label().classes("or-hint")
                                    pull_prog.set_visibility(False)
                            with row("Server", "Where Ollama runs."):
                                ui.input().bind_value(work, "ai_ollama_url") \
                                    .props('outlined dense aria-label="Ollama server"').classes("or-mono").style("flex: 1 1 320px")
                            ui.label("API (with a key)").classes("or-label q-mt-md")
                            with row("Provider", "OpenAI-compatible providers, or Anthropic. Custom: any "
                                                 "OpenAI-compatible URL (LM Studio, vLLM, a company gateway)."):
                                ui.select({"openai": "OpenAI", "anthropic": "Anthropic", "openrouter": "OpenRouter",
                                           "gemini": "Google Gemini", "mistral": "Mistral", "groq": "Groq",
                                           "custom": "Custom (OpenAI-compatible URL)"}) \
                                    .bind_value(work, "ai_api_provider").props('outlined dense aria-label="Provider"') \
                                    .style("flex: 1 1 320px")
                            with row("Model", "The provider's model id, e.g. gpt-4o-mini or claude-sonnet-4-5."):
                                ui.input().bind_value(work, "ai_api_model") \
                                    .props('outlined dense aria-label="API model"').classes("or-mono").style("flex: 1 1 320px")
                            with row("Base URL (custom only)", "Leave empty for the provider's own address."):
                                ui.input(placeholder="http://localhost:1234/v1").bind_value(work, "ai_api_base_url") \
                                    .props('outlined dense clearable aria-label="API base URL"').classes("or-mono") \
                                    .style("flex: 1 1 320px")
                            with row("API key", "Kept on this computer only; never in reports, the history or "
                                                "ontoreview.toml. Empty: the provider's environment variable "
                                                "(OPENAI_API_KEY, ANTHROPIC_API_KEY, …). Text you send leaves this "
                                                "computer."):
                                ui.input(password=True, password_toggle_button=True).bind_value(work, "ai_api_key") \
                                    .props('outlined dense clearable autocomplete="off" aria-label="API key"') \
                                    .classes("or-mono").style("flex: 1 1 320px")
                            with ui.row().classes("items-center gap-3 q-py-md"):
                                ai_check = ui.button("Check sources", icon="fact_check").props("outline no-caps") \
                                    .mark("ai-check")
                                ai_info = ui.label().classes("or-hint").style("word-break:break-word")

                    names = {"hf": "Hugging Face (local)", "ollama": "Ollama (local)", "api": "API (with a key)"}

                    def render_prio() -> None:
                        prio_box.clear()
                        order = [x for x in work.ai_priority.split(",") if x in names]
                        with prio_box:
                            for i, key in enumerate(order):
                                with ui.row().classes("items-center gap-1 no-wrap"):
                                    ui.label(f"{i + 1}.").classes("or-hint").style("width:18px")
                                    ui.label(names[key]).classes("or-label").style("min-width:170px")
                                    ui.button(icon="arrow_upward", on_click=lambda i=i: move(i, -1)) \
                                        .props(f'flat round dense size=sm aria-label="Move {names[key]} up"') \
                                        .set_enabled(i > 0)
                                    ui.button(icon="arrow_downward", on_click=lambda i=i: move(i, 1)) \
                                        .props(f'flat round dense size=sm aria-label="Move {names[key]} down"') \
                                        .set_enabled(i < len(order) - 1)
                                    ui.button(icon="close", on_click=lambda k=key: drop(k)) \
                                        .props(f'flat round dense size=sm aria-label="Do not use {names[key]}"') \
                                        .set_enabled(len(order) > 1)
                            for key in [k for k in names if k not in order]:
                                ui.button(f"Add {names[key]}", icon="add", on_click=lambda k=key: (
                                    setattr(work, "ai_priority", ",".join(order + [k])), render_prio())) \
                                    .props("flat dense no-caps size=sm")

                    def move(i: int, d: int) -> None:
                        order = [x for x in work.ai_priority.split(",") if x in names]
                        order[i], order[i + d] = order[i + d], order[i]
                        work.ai_priority = ",".join(order)
                        render_prio()

                    def drop(key: str) -> None:
                        work.ai_priority = ",".join(x for x in work.ai_priority.split(",") if x in names and x != key)
                        render_prio()

                    async def check_ai() -> None:
                        from .fixes.ai.sources import make_source
                        cfg = work.ai_config()
                        ai_info.text = "Checking…"
                        parts, used = [], None
                        for key in cfg.priority:
                            ok, why = await run.io_bound(lambda k=key: make_source(k, cfg, work.hf_token).available())
                            parts.append(f"{names[key]}: {'ready' if ok else why}")
                            if ok and used is None:
                                used = names[key]
                        ai_info.text = (f"Would use {used}. " if used else "No source is ready. ") + " · ".join(parts) \
                            + ("" if work.ai_enabled else " (AI drafts are off.)")
                    ai_check.on_click(check_ai)
                    render_prio()

                    async def list_ollama() -> None:
                        from .fixes.ai.sources import OllamaSource
                        models = await run.io_bound(OllamaSource(work.ai_ollama_model, work.ai_ollama_url).models)
                        if not models:
                            ollama_info.set_text(f"Ollama is not running at {work.ai_ollama_url} (or has no models).")
                            return
                        opts = {m["name"]: f"{m['name']}  ·  {m['parameters'] or ''} {m['size'] / 1e9:.1f} GB".strip()
                                for m in models}
                        if work.ai_ollama_model and work.ai_ollama_model not in opts:
                            opts[work.ai_ollama_model] = f"{work.ai_ollama_model}  ·  not installed"
                        ollama_sel.set_options(opts, value=work.ai_ollama_model)
                        ollama_info.set_text(f"{len(models)} model(s) installed in Ollama.")

                    async def pull_ollama() -> None:
                        from .fixes.ai.sources import AIError, OllamaSource
                        name = (pull_in.value or "").strip()
                        if not name:
                            notify("Type a model name, e.g. qwen3.5:4b.", "warning")
                            return
                        pull_btn.disable()
                        pull_prog.set_visibility(True)
                        state_ = {"status": "starting", "done": 0, "total": 0}

                        def progress(status, done, total) -> None:
                            state_.update(status=status, done=done or state_["done"], total=total or state_["total"])

                        def tick() -> None:
                            t_, d_ = state_["total"], state_["done"]
                            pull_prog.set_value(min(d_ / t_, 1.0) if t_ else 0)
                            pull_msg.set_text(f"{state_['status']}" + (f": {d_ / 1e9:.2f} of {t_ / 1e9:.2f} GB" if t_ else ""))
                        timer = ui.timer(0.5, tick)
                        try:
                            await run.io_bound(OllamaSource("", work.ai_ollama_url).pull, name, progress)
                            work.ai_ollama_model = name
                            notify(f"{name} is ready in Ollama.", "positive")
                            await list_ollama()
                        except AIError as e:
                            notify(str(e), "warning")
                        finally:
                            timer.cancel()
                            tick()
                            pull_btn.enable()
                    ui.timer(0.1, list_ollama, once=True)
                with ui.tab_panel(t_look).classes("q-pa-none").style("max-width: 900px"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("Theme").classes("or-h2")
                            theme_box = ui.element("div").props('role="radiogroup" aria-label="Theme"') \
                                .classes("w-full gap-0").style("display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px")
                            ui.checkbox("Compact layout").bind_value(work, "compact")
                with ui.tab_panel(t_tel).classes("q-pa-none"):
                    telemetry_panel()
            with ui.row().classes("w-full items-center justify-between q-mt-md"):
                ui.button("Reset to defaults", on_click=lambda: reset()).props("flat no-caps")
                with ui.row().classes("gap-2"):
                    ui.button("Cancel", on_click=lambda: ui.navigate.to("/")).props("outline no-caps")
                    ui.button("Save changes", on_click=lambda: save()).props("unelevated no-caps").mark("save-settings")

        def render_mode() -> None:
            mode_box.clear()
            with mode_box:
                for key, name, desc in (("docker", "Docker", "No Java install needed"),
                                        ("local", "Local robot command", "Uses `robot` on your PATH")):
                    sel = work.robot_mode == key
                    with ui.element("button").classes("or-opt" + (" or-sel" if sel else "")).props(
                            f'type="button" role="radio" aria-checked="{str(sel).lower()}"') as b:
                        ui.element("span").classes("or-radio")
                        with ui.column().classes("gap-0"):
                            ui.label(name).classes("or-label")
                            ui.label(desc).classes("or-hint")
                    b.on("click", lambda key=key: (setattr(work, "robot_mode", key), render_mode()))
            img_row.set_visibility(work.robot_mode == "docker")
            path_row.set_visibility(work.robot_mode == "local")

        def render_theme() -> None:
            theme_box.clear()
            prev_bg = {"light": "linear-gradient(90deg,#0F1724 25%,#F4F6F8 25%)",
                       "dark": "linear-gradient(90deg,#0B111A 25%,#1A2230 25%)",
                       "system": "linear-gradient(90deg,#0F1724 25%,#F4F6F8 25%,#F4F6F8 62%,#1A2230 62%)"}
            with theme_box:
                for key, name in (("light", "Light"), ("dark", "Dark"), ("system", "Match system")):
                    sel = work.theme == key
                    with ui.element("button").classes("or-opt column items-stretch" + (" or-sel" if sel else "")).props(
                            f'type="button" role="radio" aria-checked="{str(sel).lower()}"') as b:
                        ui.element("span").classes("or-themeprev").style(f"background:{prev_bg[key]}")
                        with ui.row().classes("w-full justify-between q-mt-sm"):
                            ui.label(name).classes("or-label")
                            if sel:
                                ui.label("✓ Selected").classes("text-primary text-weight-medium")
                    b.on("click", lambda key=key: (setattr(work, "theme", key), render_theme()))

        def show_badge(target, st: dict) -> None:
            target.content = f'<span class="or-badge {BADGE_KIND[st["state"]]}">{st["label"].split("· ")[-1].capitalize()}</span>'

        async def test_robot() -> None:
            robot_badge.content = '<span class="or-badge off">Checking…</span>'
            st = await run.io_bound(robot_status, work)
            show_badge(robot_badge, st)
            notify(f"{st['label']}: {st.get('detail', '')}", "positive" if st["state"] == "ok" else "warning")

        async def test_oops() -> None:
            oops_badge.content = '<span class="or-badge off">Checking…</span>'
            show_badge(oops_badge, await run.io_bound(oops_status, work, True))

        def reset() -> None:
            for k, v in asdict(Prefs()).items():
                setattr(work, k, v)
            render_mode()
            render_theme()
            notify("Defaults restored. Save changes to keep them.")

        def save() -> None:
            for k, v in asdict(work).items():
                setattr(prefs, k, v)
            prefs.save()
            prefs.apply(s, new=not s.source.strip())
            s.save()
            dark.set_value({"light": False, "dark": True, "system": None}[prefs.theme])
            if prefs.compact:
                ui.query("body").classes(add="or-compact")
            else:
                ui.query("body").classes(remove="or-compact")
            notify("Settings saved", "positive")
            ui.timer(0.05, refresh_env, once=True)

        if state.get("env"):
            show_badge(robot_badge, state["env"][0])
            show_badge(oops_badge, state["env"][1])
        render_mode()
        render_theme()

    # ------------------------------------------------------------------ About
    def about_view() -> None:
        set_active("about")
        page_head("About", "What this tool does, what it runs on, and where to get help.")
        with ui.element("div").classes("or-body column gap-4"):
            with ui.row().classes("or-hero items-center gap-6 w-full"):
                with ui.column().classes("gap-3").style("flex: 1 1 320px"):
                    ui.html(logo_full(340), sanitize=False)
                    ui.label("Turn ontology files into self-contained documentation, review their quality (built-in "
                             "rules, ROBOT, reasoner, IRI checks, OntoCheck, OOPS!), score cross-domain and scientific "
                             "interoperability, and publish the result — from one window or the command line.").style(
                        "font-size:15px;line-height:1.55;color:#C9D1DB;max-width:560px")
                    with ui.row().classes("gap-2 q-mt-sm"):
                        for chip in (f"Version {__version__}", "MIT License", "CAIR-Nepal"):
                            ui.label(chip).style("background:#1E293B;padding:4px 10px;border-radius:20px;font-size:12px")
                with ui.column().classes("gap-2"):
                    ui.button("View on GitHub", on_click=lambda: ui.navigate.to(REPO, new_tab=True)) \
                        .props("unelevated no-caps color=white text-color=dark")
                    ui.button("Report an issue", on_click=lambda: ui.navigate.to(REPO + "/issues/new/choose", new_tab=True)) \
                        .props("outline no-caps color=white")
            with ui.element("div").classes("w-full").style(
                    "display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px"):
                for icon, title, text in (
                        ("language", "Documentation", "Website, single HTML file, Markdown or a MyST / Sphinx project — "
                                                      "for one ontology or a whole folder."),
                        ("task_alt", "Quality review", "Built-in checks, ROBOT reports, reasoner consistency and OOPS! pitfall scans, merged "
                                                       "into one list of errors and warnings."),
                        ("code", "Reproducible", "Every run here maps to an ontoreview command and can be saved as "
                                                 "ontoreview.toml for CI."),
                        ("computer", "Runs locally", "Files stay on your machine. Only the OOPS! scan contacts an "
                                                     "external service, and you can turn it off.")):
                    with ui.card().classes("or-card or-feature").props("flat"):
                        with ui.column().classes("or-sec gap-1").style("padding: 16px 18px"):
                            with ui.element("div").classes("ic"):
                                ui.icon(icon, size="20px")
                            ui.label(title).classes("or-h2")
                            ui.label(text).classes("or-hint").style("font-size:13px;line-height:1.55")
            with ui.row().classes("w-full gap-4 items-stretch"):
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 380px"):
                    with ui.column().classes("or-sec gap-3"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("System info").classes("or-h2")
                            copy_btn = ui.button("Copy for bug report", icon="content_copy").props("outline no-caps dense")
                        info_box = ui.element("div").classes("w-full").style(
                            "display:grid;grid-template-columns:140px 1fr;row-gap:10px;font-size:13px")
                        with info_box:
                            ui.label("Detecting…").classes("or-hint")
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 300px"):
                    with ui.column().classes("or-sec gap-2"):
                        ui.label("Built on").classes("or-h2")
                        for name, what in (("ROBOT", "OBO tool for ontology reports"), ("OOPS!", "OntOlogy Pitfall Scanner"),
                                           ("OntoCheck", "Ontology quality metrics, SDLE Research Center, CWRU (CC BY 4.0)"),
                                           ("HermiT / ELK", "OWL reasoners, run through ROBOT"),
                                           ("NiceGUI", "Python UI framework"), ("rdflib", "RDF parsing and serialization")):
                            ui.html(f'<div style="font-size:13px"><b>{name}</b> <span class="or-muted">— {what}</span></div>',
                                    sanitize=False)
                        ui.label("Please cite ROBOT, OntoCheck and OOPS! when publishing their results.").classes("or-hint q-mt-sm")
            with ui.element("footer").classes("w-full row items-center justify-between gap-4 q-mt-md q-pt-md").style(
                    "border-top: 1px solid var(--or-line)"):
                with ui.column().classes("gap-0"):
                    ui.label("Developed by CAIR-Nepal").classes("or-label")
                    ui.link("cair-nepal.org", "https://cair-nepal.org", new_tab=True).classes("or-hint")
                ui.label(f"MIT License · OntoReview {__version__}").classes("or-hint")

        async def fill() -> None:
            info = await run.io_bound(system_info)
            info_box.clear()
            with info_box:
                for k, v in info.items():
                    ui.label(k).classes("or-muted")
                    ui.label(v).classes("or-mono").style("font-size:12.5px;word-break:break-all")
            text = "\n".join(f"{k}: {v}" for k, v in info.items())
            copy_btn.on_click(lambda: (ui.clipboard.write(text), notify("System info copied", "positive")))

        ui.timer(0.05, fill, once=True)

    # ------------------------------------------------------------------ Compare

    def compare_view() -> None:  # noqa: C901
        set_active("compare")
        head = page_head("Compare", "Compare two versions of an ontology. Drop or choose both files; the "
                                    "comparison runs as soon as both are there.")
        with head:
            cmp_btn = ui.button("Compare", icon="compare_arrows", on_click=lambda: run_compare()) \
                .props("unelevated no-caps").mark("compare-run")
        infos: dict = {}
        boxes: dict = {}
        with ui.element("div").classes("or-body column gap-4"):
            with ui.row().classes("w-full gap-4 no-wrap max-md:flex-wrap items-stretch"):
                for side, title, hint in (("old", "Previous version", "The older release, e.g. 1.0"),
                                          ("new", "Current version", "The version you want to check")):
                    with ui.card().classes("or-card").props("flat").style("flex: 1 1 0; min-width: 0"):
                        with ui.column().classes("or-sec gap-3"):
                            with ui.row().classes("items-center gap-2"):
                                ui.html(f'<span class="or-step">{"A" if side == "old" else "B"}</span>', sanitize=False)
                                ui.label(title).classes("or-h2")
                            with ui.element("div").props(f'data-zone="{side}"').classes("ob-dropzone w-full"):
                                boxes[side] = ui.column().classes("w-full gap-2")
                            with ui.row().classes("gap-2"):
                                ui.button("File", icon="description", on_click=lambda side=side, title=title: pick(
                                    "ontology", lambda p, side=side: set_side(side, p), False,
                                    cmp[side] or s.source, title=f"Choose the {title.lower()}")) \
                                    .props("outline no-caps dense").classes("px-3")
                                ui.button("URL", icon="link", on_click=lambda side=side, title=title: ask(side, title)) \
                                    .props("outline no-caps dense").classes("px-3")
                            infos[side] = ui.label(f"{hint}. Drop a file here, or choose one.").classes("or-hint") \
                                .props('aria-live="polite"')
            with ui.card().classes("or-card w-full").props("flat"):
                with ui.column().classes("or-sec gap-2"):
                    ui.label("Save report to").classes("or-label")
                    with ui.row().classes("w-full no-wrap gap-2 items-center"):
                        out_in = ui.input(on_change=lambda: show_out()).bind_value(cmp, "output").mark("compare-output") \
                            .props('outlined dense clearable aria-label="Save report to"').classes("grow or-mono")
                        ui.button("Browse…", on_click=lambda: pick("any", lambda p: out_in.set_value(p), True,
                                                                   cmp["output"], "Where to save the report")) \
                            .props("outline no-caps")
                    out_info = ui.label().classes("or-hint or-mono").style("word-break: break-all")
            results = ui.column().classes("w-full gap-4")

        def settings_for() -> Settings:
            return Settings(source=cmp["new"], previous_version=cmp["old"], task="diff", output=cmp["output"],
                            default_root=prefs.default_output)

        def show_out() -> None:
            st = settings_for()
            target = st.output_path()
            stem = target.with_suffix("")
            out_info.text = (f"Writes {stem}.html, .md and .json" + ("" if cmp["output"].strip() else "  (default)")
                             if cmp["new"] else "Choose the current version first.")

        def render_side(side: str) -> None:
            boxes[side].clear()
            with boxes[side]:
                val = cmp[side]
                if val:
                    is_url = val.startswith(("http://", "https://"))
                    with ui.element("div").classes("or-chip"):
                        with ui.element("div").classes("or-chipicon"):
                            ui.icon("link" if is_url else "description", size="20px")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(val if is_url else Path(val).name).classes("or-label ellipsis w-full")
                            if not is_url:
                                ui.label(str(Path(val).parent) + "/").classes("or-hint or-mono ellipsis w-full")
                        ui.button(icon="close", on_click=lambda side=side: set_side(side, "")) \
                            .props(f'flat round dense aria-label="Clear {side} version"')
                else:
                    inp = ui.input(placeholder="Type a path or URL and press Enter, or drop a file here") \
                        .props(f'borderless dense aria-label="{side} version path or URL"') \
                        .classes("w-full or-mono").mark(f"compare-{side}")
                    inp.on("keydown.enter", lambda inp=inp, side=side: set_side(side, (inp.value or "").strip()))
                    inp.on("blur", lambda inp=inp, side=side: (inp.value or "").strip()
                           and set_side(side, inp.value.strip()))

        def set_side(side: str, value: str) -> None:
            if value and not value.startswith(("http://", "https://")):
                pth = Path(value).expanduser()
                if pth.is_dir():
                    notify("Choose a single ontology file, not a folder.", "warning")
                    return
                if not pth.exists():
                    notify(f"Not found: {value}", "warning")
                    return
            cmp[side] = value
            render_side(side)
            show_out()
            if cmp["old"] and cmp["new"] and (cmp["old"], cmp["new"]) != cmp["done"]:
                ui.timer(0.05, run_compare, once=True)   # both chosen: compare right away

        def ask(side: str, title: str) -> None:
            with ui.dialog() as dlg, ui.card().classes("or-card w-[36rem] max-w-full"):
                ui.label(f"{title}: URL or path").classes("or-h2")
                inp = ui.input(placeholder="https://… or /path/to/ontology.ttl", value=cmp[side]) \
                    .props("outlined autofocus").classes("w-full or-mono")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dlg.close).props("flat no-caps")
                    ui.button("Use", on_click=lambda: (set_side(side, inp.value.strip()), dlg.close())).props("unelevated no-caps")
            dlg.open()

        def render() -> None:
            results.clear()
            cmp_btn.set_enabled(not cmp["running"])
            cmp_btn.text = "Comparing…" if cmp["running"] else "Compare"
            with results:
                if cmp["running"]:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.row().classes("or-sec items-center gap-3"):
                            ui.spinner(size="22px")
                            ui.label(f"Comparing {Path(cmp['old']).name} → {Path(cmp['new']).name}…").classes("or-h2")
                    return
                res = cmp["last"]
                if res is None:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2 items-center text-center q-py-xl"):
                            ui.icon("compare_arrows", size="40px").classes("or-muted")
                            ui.label("Nothing compared yet").classes("or-h2")
                            ui.label("Add the previous and the current version above. Terms are matched by IRI; "
                                     "you'll see what was added, removed and modified, and get an HTML report.") \
                                .classes("or-hint")
                    return
                if isinstance(res, Exception):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.label("Comparison failed").classes("or-h2")
                                badge("err", "Failed")
                            ui.label(str(res)).classes("or-mono or-hint")
                    return
                render_changes(res, cmp, render)

        async def run_compare() -> None:
            if cmp["running"]:
                return
            st = settings_for()
            problems = [p for p in st.validate() if "previous version" not in p.lower()] if cmp["old"] else []
            if not cmp["new"] or not cmp["old"]:
                notify("Add both versions first.", "warning")
                return
            if problems:
                for p_ in problems:
                    notify(p_, "warning")
                return
            cmp.update(running=True, filter="all", done=(cmp["old"], cmp["new"]))
            background_tasks.create(compare_job(st), name="ontoreview-compare")
            cmp_sync()

        async def compare_job(st: Settings) -> None:
            """Runs independently of this view: switching pages does not stop or lose it."""
            try:
                res = await run.io_bound(run_task, st)
            except Exception as e:  # noqa: BLE001
                cmp["last"] = e
                if prefs.keep_history:
                    record_run(st, None, str(e), limit=prefs.history_limit)
                notify(f"Comparison failed: {e}", "negative")
            else:
                cmp["last"] = res
                if prefs.keep_history:
                    record_run(st, res, limit=prefs.history_limit)
                n = sum(change_counts(res.changes).values())
                notify(f"{n} change{'s' if n != 1 else ''} found" if n else "No differences", "positive")
            finally:
                cmp["running"] = False
    
        cmp_seen = {"sig": (cmp["running"], id(cmp["last"]))}

        def cmp_sync() -> None:
            sig = (cmp["running"], id(cmp["last"]))
            if results.is_deleted or sig == cmp_seen["sig"]:
                return
            cmp_seen["sig"] = sig
            render()

        ui.timer(0.3, cmp_sync)

        drop_targets.clear()
        for side in ("old", "new"):
            def done(a: dict, side=side) -> None:
                target = dropped_path(a, infos[side], files_only=True)
                if target:
                    set_side(side, target)
            drop_targets[side] = (lambda a, side=side: setattr(infos[side], "text", "Copying…"), done)
            render_side(side)
        show_out()
        render()

    # ------------------------------------------------------------------ Quality issues
    def review_list() -> None:
        """Every ontology checked for Build docs, like Run history: waiting ones to fix and build, built ones."""
        def open_(k: str) -> None:
            SESSION.review_key = k
            ui.navigate.reload()

        def remove(k: str) -> None:
            SESSION.drop_review(k)
            ui.navigate.reload()

        def clear_done() -> None:
            for k in [k for k, e in SESSION.reviews.items() if e.get("status", "open") != "open"]:
                SESSION.drop_review(k)
            ui.navigate.reload()
        rows = sorted(SESSION.reviews.values(), key=lambda e: (e.get("status", "open") != "open", -e["added"]))
        with ui.element("div").classes("or-body"), ui.card().classes("or-card w-full").props("flat"):
            with ui.column().classes("or-sec gap-2 w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    n_wait = sum(1 for e in rows if e.get("status", "open") == "open")
                    ui.label(f"Ontologies checked ({len(rows)}) · {n_wait} waiting for review").classes("or-h2")
                    if len(rows) > n_wait:
                        ui.button("Clear finished", on_click=clear_done).props("flat dense no-caps")
                ui.label("Each Build docs checks the ontology first and waits here. Fix now or come back later; "
                         "docs are generated when you apply or skip.").classes("or-hint")
                for e in rows:
                    st = e.get("status", "open")
                    job = e["job"]
                    with ui.row().classes("w-full items-center no-wrap gap-3 q-py-sm").style(
                            "border-top:1px solid var(--or-line)").mark(f"review-row-{Path(e['key']).name}"):
                        ui.icon({"open": "pending_actions", "built": "check_circle", "skipped": "task_alt"}[st]
                                if st in ("open", "built", "skipped") else "help",
                                color={"open": "warning", "built": "positive"}.get(st, "grey")).style("font-size:22px")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(Path(e["key"]).name).classes("text-weight-medium")
                            ui.label(f"{TASKS.get(job.task, job.task)} → {job.output or 'default output'} · checked "
                                     f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(e['added']))}") \
                                .classes("or-hint ellipsis")
                        if st == "open":
                            n = open_issue_count(e)
                            acc = sum(1 for d in (e.get("dec") or {}).values() if d.get("status") == "accepted")
                            ui.badge(f"Waiting · {n} open" + (f", {acc} accepted" if acc else ""),
                                     color="orange-2", text_color="orange-10").props("rounded")
                            ui.button("Fix & build", icon="build", on_click=lambda k=e["key"]: open_(k)) \
                                .props("unelevated dense no-caps").mark("review-open")
                        else:
                            what = (f"Built from {Path(e['result']).name}" if st == "built" and e.get("result")
                                    else "Built from the original")
                            ui.badge(f"{what} · {e.get('finished', '')}", color="green-1",
                                     text_color="green-9").props("rounded")
                        ui.button(icon="delete_outline", on_click=lambda k=e["key"]: remove(k)) \
                            .props('flat round dense aria-label="Remove from the list"') \
                            .tooltip("Remove from this list (files and docs are kept)")

    def issues_view() -> None:  # noqa: C901
        """Review suggested fixes before the docs are built (or after, to rebuild): issues on the left,
        the selected issue and its fixes in the centre, impact and context on the right."""
        from .fixes import FixError
        from .fixes.model import term as n3term
        from .fixes.rules import missing_values

        set_active("issues")
        fs = SESSION.fixes
        if fs.get("status", "open") != "open":
            SESSION.review_key, fs = None, SESSION.fixes
        session = fs.get("session")
        head = page_head("Quality issues", "Fix first, then document: each fix shows what changes in the ontology "
                                           "and in the docs. The original file is never changed.")
        if fs.get("key") and session is None:          # saved before a restart: check it again, then show it
            with ui.element("div").classes("or-body"):
                with ui.row().classes("items-center gap-3 q-pa-md"):
                    ui.spinner(size="24px")
                    ui.label(f"Checking {Path(fs['key']).name} again and restoring your choices…") \
                        .classes("text-weight-medium")

            async def _restore(e=fs) -> None:
                try:
                    await run.io_bound(restore_review, e)
                except Exception as ex:  # noqa: BLE001 - file moved or unreadable
                    notify(f"Could not re-check {Path(e['key']).name}: {ex}", "warning")
                    SESSION.review_key = None
                ui.navigate.reload()
            ui.timer(0.1, _restore, once=True)
            return
        if session is None and SESSION.reviews:
            review_list()
            return
        if session is None:
            with ui.element("div").classes("or-body"):
                with ui.card().classes("or-card w-full").props("flat"):
                    with ui.column().classes("or-sec gap-2 items-center text-center q-py-xl"):
                        ui.icon("task_alt", size="40px").classes("or-muted")
                        ui.label("No issues to review").classes("or-h2")
                        ui.label("Press Build docs on the Build page: the ontology is checked first and its "
                                 "issues appear here before any docs are generated.").classes("or-hint")
                        ui.button("Go to Build", on_click=lambda: ui.navigate.to("/")).props("outline no-caps")
            return
        job: Settings | None = fs.get("job")
        ignored = ignored_ids()
        sev_of = {(f.rule, f.subject): f.severity for f in session.report.findings}
        sev_of_rules = {f.rule for f in session.report.findings}

        def sev(x) -> str:
            if x.required:
                return "required"
            if x.severity and (x.rule, x.subject) not in sev_of:
                return x.severity
            return sev_of.get((x.rule, x.subject)) or next(
                (f.severity for f in session.report.findings if f.rule == x.rule), "info")

        def check_of(x) -> str:
            if x.required:
                return "Required metadata"
            if ":" in x.rule:                                  # a finding of another check, e.g. OntoCheck:checkLabel
                return " · ".join(x.rule.split(":", 1))
            if x.rule.startswith("FX"):
                return f"Text check · {x.rule}"
            if x.rule in sev_of_rules:
                return f"Built-in rules · {x.rule}"
            return x.reported_by[0] if x.reported_by else f"Built-in rules · {x.rule}"

        def label_of(iri) -> str:
            t = session.onto.terms.get(iri or "")
            if t:
                return t.curie or t.label
            return "ontology" if iri in (None, session.onto.metadata.iri) else str(iri).rsplit("/", 1)[-1]

        def dec(x) -> dict:
            if x.id not in fs["dec"]:
                text = str(n3term(x.options[0].add[0][2])) if x.kind == "L" and x.options and x.options[0].add else ""
                fs["dec"][x.id] = {"opt": 0, "values": {f.name: f.value for f in x.fields}, "text": text,
                                   "status": "accepted" if x.id in session.accepted else "open"}
            return fs["dec"][x.id]

        def visible() -> list:
            items = [x for x in session.suggestions if session.supported(x) and (x.options or x.fields or x.kind == "M")]
            if not fs["show_ignored"]:
                items = [x for x in items if x.id not in ignored and dec(x)["status"] != "ignored"]
            f_ = fs["filter"]
            if f_ != "all":
                want = {"errors": ("error", "required"), "warnings": ("warning",), "suggestions": ("info",)}[f_]
                items = [x for x in items if sev(x) in want]
            order = {"required": 0, "error": 1, "warning": 2, "info": 3}
            # open issues first (by severity); handled ones (accepted, ignored) sink to the end of the list
            return sorted(items, key=lambda x: (dec(x)["status"] != "open", order.get(sev(x), 4)))

        with head:
            header_box = ui.row().classes("gap-2 items-center")
        with ui.element("div").classes("or-body"):
            with ui.row().classes("w-full items-center gap-2 q-mb-sm"):
                def to_list() -> None:
                    SESSION.review_key = None
                    ui.navigate.reload()
                ui.button(f"All reviews ({len(SESSION.reviews)})", icon="arrow_back", on_click=to_list) \
                    .props("flat dense no-caps").mark("reviews-all")
                waiting = sum(1 for e in SESSION.reviews.values() if e.get("status", "open") == "open")
                if waiting > 1:
                    ui.label(f"{waiting - 1} other ontolog{'y' if waiting == 2 else 'ies'} waiting for review") \
                        .classes("or-hint")
            ext_bar = ui.row().classes("w-full items-center gap-3 q-pa-sm q-mb-sm no-wrap").style(
                "background:var(--or-line-2);border-radius:8px")
            with ext_bar:
                ui.spinner(size="18px")
                ext_msg = ui.label("Running ROBOT, the reasoner, IRI checks, OntoCheck and OOPS!: their issues are "
                                   "added here when ready. You can start reviewing.").classes("text-weight-medium")
            ext_bar.set_visibility(False)
            ai_bar = ui.row().classes("w-full items-center gap-3 q-pa-sm q-mb-sm no-wrap").style(
                "background:var(--or-line-2);border-radius:8px")
            ai_bar.set_visibility(False)
            with ai_bar:
                ui.spinner(size="18px")
                with ui.column().classes("gap-0 grow"):
                    ai_msg = ui.label().classes("text-weight-medium")
                    ai_prog = ui.linear_progress(value=0, show_value=False).props("rounded size=6px")
            sub_ = f"From the check of {session.source.name}" + (f" · {TASKS.get(job.task, job.task)} output" if job else "")
            ui.label(sub_ + (" · the docs are built after you apply or skip." if fs["mode"] == "prebuild" else "."))\
                .classes("or-hint q-mb-sm")
            with ui.row().classes("w-full gap-4 items-start no-wrap max-lg:flex-wrap"):
                left = ui.card().classes("or-card").props("flat").style("flex: 0 0 300px; min-width: 260px")
                centre = ui.column().classes("gap-4").style("flex: 1 1 520px; min-width: 0")
                right = ui.column().classes("gap-4").style("flex: 0 0 300px; min-width: 260px")

        def render_left() -> None:
            left.clear()
            items = visible()
            all_items = [x for x in session.suggestions if session.supported(x) and (x.options or x.fields or x.kind == "M")]
            handled = sum(1 for x in all_items if dec(x)["status"] in ("accepted", "ignored") or x.id in ignored)
            with left, ui.column().classes("w-full gap-0"):
                with ui.row().classes("w-full items-center justify-between q-pa-md q-pb-sm"):
                    ui.label("Found in this check").classes("or-label")
                    ui.label(f"{len(all_items) - handled} open · {handled} handled").classes("or-hint")
                counts = {k: sum(1 for x in all_items if sev(x) in v) for k, v in
                          {"errors": ("error", "required"), "warnings": ("warning",), "suggestions": ("info",)}.items()}
                with ui.row().classes("gap-1 q-px-md q-pb-sm"):
                    for key, lab in (("all", f"All {len(all_items)}"), ("errors", f"Errors {counts['errors']}"),
                                     ("warnings", f"Warnings {counts['warnings']}"),
                                     ("suggestions", f"Suggestions {counts['suggestions']}")):
                        ui.button(lab, on_click=lambda k=key: (fs.__setitem__("filter", k), render_all())) \
                            .props("dense no-caps " + ("unelevated" if fs["filter"] == key else "outline")) \
                            .classes("q-px-sm")
                for x in items:
                    d = dec(x)
                    sel = fs["sel"] == x.id
                    with ui.element("div").classes("w-full cursor-pointer q-px-md q-py-sm").style(
                            "border-top:1px solid var(--or-line-2);"
                            + ("background:var(--or-line-2);box-shadow:inset 3px 0 0 var(--q-primary);" if sel else "")) as row:
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            s_ = sev(x)
                            badge({"required": "err", "error": "err", "warning": "warn", "info": "info"}.get(s_, "info"),
                                  s_.upper() if s_ != "info" else "SUGGESTION")
                            ui.label(check_of(x).split(" · ")[0] + (f" +{len(x.reported_by)}" if x.reported_by and ":" not in x.rule else ""))\
                                .classes("or-hint ellipsis")
                            if d["status"] == "accepted":
                                ui.icon("check_circle", size="16px").classes("text-positive q-ml-auto")
                            elif d["status"] == "ignored" or x.id in ignored:
                                ui.icon("visibility_off", size="16px").classes("or-muted q-ml-auto")
                        ui.label(x.title).classes("text-weight-medium")
                        ui.label(label_of(x.subject)).classes("or-hint or-mono ellipsis w-full")
                    row.on("click", lambda x=x: (fs.__setitem__("sel", x.id), render_all()))
                if not items:
                    ui.label("Nothing here.").classes("or-hint q-pa-md")
                n_ign = sum(1 for x in all_items if x.id in ignored)
                if n_ign:
                    ui.button(("Hide" if fs["show_ignored"] else "Show") + f" {n_ign} ignored",
                              on_click=lambda: (fs.__setitem__("show_ignored", not fs["show_ignored"]), render_all())) \
                        .props("flat dense no-caps").classes("q-ma-sm")

        def current():
            items = visible()
            if not items:
                return None
            if fs["sel"] not in {x.id for x in items}:
                fs["sel"] = items[0].id
            return next(x for x in items if x.id == fs["sel"])

        def chosen_option(x):
            d = dec(x)
            if x.fields:
                try:
                    from .fixes.rules import resolve_fields
                    return resolve_fields(x, d["values"], session.graph, session.onto) if not missing_values(x, d["values"]) else None
                except Exception:  # noqa: BLE001
                    return None
            if d.get("custom") and x.rule in ("OB012", "OB013"):
                from rdflib.namespace import RDFS as _RDFS

                from .fixes.model import Option as _Opt
                from .fixes.model import n3 as _n3
                pred = _RDFS.domain if x.rule == "OB012" else _RDFS.range
                return _Opt("Your choice", add=[_n3((URIRef(x.subject), pred, URIRef(d["custom"])))],
                            confidence="high", reason="Chosen by you.")
            return x.options[d["opt"]] if x.options and d["opt"] < len(x.options) else None

        def render_centre() -> None:
            centre.clear()
            x = current()
            if x is None:
                with centre, ui.card().classes("or-card w-full").props("flat"):
                    ui.label("All issues handled. Apply the fixes and build.").classes("or-sec or-hint")
                return
            d = dec(x)
            with centre:
                with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2"):
                    with ui.row().classes("items-center gap-2"):
                        s_ = sev(x)
                        badge({"required": "err", "error": "err", "warning": "warn"}.get(s_, "info"),
                              s_.upper() if s_ != "info" else "SUGGESTION")
                        ui.label(check_of(x)).classes("or-hint")
                    ui.label(x.title).classes("or-h2").style("font-size:20px")
                    ui.label(label_of(x.subject)).classes("or-mono text-primary")
                    if x.reported_by:
                        with ui.row().classes("items-center gap-1"):
                            ui.label("Also reported by").classes("or-hint")
                            for tag in x.reported_by:
                                badge("info", tag)
                    if x.explanation:
                        ui.label(x.explanation).style("color:var(--or-ink-2)")
                with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-3 w-full"):
                    if x.kind == "M":
                        ui.label("Needs a modelling decision").classes("or-h2")
                        ui.label("No automatic fix: edit the ontology yourself. The explanation above shows why.") \
                            .classes("or-hint")
                    else:
                        ui.label("Suggested fix" + ("es" if len(x.options) > 1 else "")).classes("or-h2")
                        for i, o in enumerate(x.options):
                            picked = d["opt"] == i and not d.get("custom")
                            with ui.element("div").classes("w-full cursor-pointer q-pa-md").style(
                                    "border-radius:10px;border:1px solid "
                                    + ("var(--q-primary);background:rgba(37,99,235,.06)" if picked else "var(--or-line)")) as card:
                                with ui.row().classes("items-start gap-3 no-wrap"):
                                    ui.icon("radio_button_checked" if picked else "radio_button_unchecked",
                                            size="20px").classes("text-primary" if picked else "or-muted")
                                    with ui.column().classes("gap-0 grow"):
                                        with ui.row().classes("items-center gap-2"):
                                            ui.label(o.label).classes("text-weight-medium")
                                            badge({"high": "ok", "medium": "warn", "low": "off"}.get(o.confidence, "info"),
                                                  f"{o.confidence.title()} confidence")
                                            badge("info", x.source)
                                        if o.reason:
                                            ui.label(o.reason).classes("or-hint")
                            card.on("click", lambda i=i: (d.__setitem__("opt", i), d.__setitem__("custom", ""), render_all()))
                        if x.kind == "L":
                            mb = x.made_by
                            text_draft = bool(x.options and x.options[0].add and x.options[0].add[0][2].startswith('"'))
                            ui.label(f"AI {'draft' if text_draft else 'suggestion'} by {mb.get('provider') or mb.get('source')} "
                                     f"· {mb.get('model')}" + (" — edit it before accepting if needed" if text_draft else
                                                               " — pick the one that fits")).classes("or-hint")
                            if text_draft:
                                ui.textarea(value=d["text"], on_change=lambda e: d.__setitem__("text", e.value or "")) \
                                    .props("outlined autogrow").classes("w-full").mark("issue-text")
                            elif x.rule in ("OB012", "OB013"):
                                which = "domain" if x.rule == "OB012" else "range"
                                t_ = session.onto.terms.get(x.subject or "")
                                if which == "range" and t_ is not None and t_.kind == "datatype_property":
                                    pool = {f"http://www.w3.org/2001/XMLSchema#{k}": f"xsd:{k}" for k in (
                                        "string", "boolean", "integer", "decimal", "double", "dateTime", "date", "anyURI")}
                                else:
                                    pool = {c.iri: c.label for c in session.onto.terms.values()
                                            if c.kind == "class" and not c.imported}

                                def own_pick(e, which=which, x=x, pool=pool) -> None:
                                    d["custom"] = e.value or ""
                                    d["opt"] = len(x.options) if e.value else 0
                                    render_side()
                                ui.select(pool, label=f"Or choose another {which} yourself", value=d.get("custom") or None,
                                          with_input=True, clearable=True, on_change=own_pick) \
                                    .props("outlined dense").classes("w-full").mark("issue-own-choice")
                        for f in x.fields:
                            def typed(e, n=f.name) -> None:
                                d["values"][n] = e.value or ""
                                render_side()
                            if f.kind == "creators":
                                creator_rows(lambda: d["values"].get("creators", ""),
                                             lambda val: (d["values"].__setitem__("creators", val), render_side()))
                            elif f.kind in ("license", "choice"):
                                with ui.row().classes("w-full items-center no-wrap gap-2"):
                                    ui.select(dict(f.choices), label=f.label, value=d["values"].get(f.name) or None,
                                              on_change=typed, with_input=True).props("outlined dense").classes("grow") \
                                        .mark(f"issue-{f.name}")
                                    if prefs.ai_enabled and f.name in ("domain", "range"):
                                        ui.button("Suggest with AI", icon="auto_awesome",
                                                  on_click=lambda e, n=f.name, x=x: ai_fill(None, n, x, e.sender)) \
                                            .props("outline no-caps").mark("issue-ai-suggest") \
                                            .tooltip("Ranked suggestions with reasons; you pick and accept")
                            elif f.kind == "textarea":
                                with ui.row().classes("w-full items-start no-wrap gap-2"):
                                    ta = ui.textarea(f.label, value=d["values"].get(f.name, ""), placeholder=f.hint,
                                                     on_change=typed).props("outlined dense autogrow").classes("grow") \
                                        .mark(f"issue-{f.name}")
                                    if prefs.ai_enabled and f.name in ("description", "definition"):
                                        ui.button("Draft with AI", icon="auto_awesome",
                                                  on_click=lambda e, ta=ta, n=f.name, x=x: ai_fill(ta, n, x, e.sender)) \
                                            .props("outline no-caps").mark("issue-ai-draft") \
                                            .tooltip("Shown for review; you accept or edit it")
                            else:
                                ui.input(f.label, value=d["values"].get(f.name, ""), placeholder=f.hint,
                                         on_change=typed).props("outlined dense").classes("w-full").mark(f"issue-{f.name}")
                        if session.is_linkml and not session.yaml_writable(x):
                            ui.label("LinkML has no place for this change in the YAML: with it, the fixed version "
                                     "is saved as OWL (Turtle) generated from the schema, plus a patch of the parts "
                                     "the YAML can hold.").classes("or-hint").mark("linkml-owl-note")
                        o = chosen_option(x)
                        if o is not None and (o.add or o.remove):
                            with ui.row().classes("w-full justify-between"):
                                ui.label("Ontology change · Turtle").classes("or-label")
                                ui.html('<span class="or-hint"><b style="color:#b42318">−</b> removed '
                                        '<b style="color:#067647">+</b> added</span>', sanitize=False)
                            lines = "".join(
                                f'<div style="background:{"rgba(180,35,24,.08)" if ln.startswith("-") else "rgba(6,118,71,.08)"};'
                                f'padding:2px 8px;white-space:pre-wrap;word-break:break-all">{html_escape(short_n3(ln))}</div>'
                                for ln in o.turtle_diff().splitlines())
                            ui.html(f'<div class="or-mono" style="font-size:12.5px;border:1px solid var(--or-line);'
                                    f'border-radius:8px;overflow:hidden">{lines}</div>', sanitize=False)
                        with ui.row().classes("gap-2 q-mt-sm"):
                            if d["status"] == "accepted":
                                ui.button("Accepted · Undo", icon="check", on_click=lambda: undo(x)) \
                                    .props("outline no-caps color=positive").mark("issue-undo")
                            else:
                                ui.button("Accept fix", on_click=lambda: accept(x)).props("unelevated no-caps") \
                                    .mark("issue-accept")
                            if not x.required:
                                ui.button("Ignore in future builds", on_click=lambda: ignore(x)) \
                                    .props("outline no-caps").mark("issue-ignore")

        def short_n3(line: str) -> str:
            """A diff line with prefixed names (:Neuron, rdfs:label) instead of full IRIs."""
            nm = session.graph.namespace_manager

            def qname(m) -> str:
                try:
                    return nm.normalizeUri(URIRef(m.group(1)))
                except Exception:  # noqa: BLE001
                    return m.group(0)
            return re.sub(r"<([^>\s]+)>", qname, line)

        def render_side() -> None:
            right.clear()
            x = current()
            if x is None:
                return
            o = chosen_option(x)
            with right:
                with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2 w-full"):
                    ui.label("Ontology impact").classes("or-h2")
                    if o is None:
                        ui.label("Fill in the value to see the change." if x.fields else "No edit.").classes("or-hint")
                    else:
                        annot = {"label", "definition", "comment", "altLabel", "prefLabel", "title", "description",
                                 "license", "creator", "name", "mbox", "versionInfo", "preferredNamespacePrefix",
                                 "preferredNamespaceUri"}
                        logical = any(not any(a in t3[1] for a in annot) for t3 in o.add + o.remove)
                        for k, v in (("Statements added", len(o.add)), ("Statements removed", len(o.remove))):
                            with ui.row().classes("w-full justify-between"):
                                ui.label(k).classes("or-hint")
                                ui.label(str(v)).classes("text-weight-medium")
                        with ui.row().classes("w-full justify-between"):
                            ui.label("Reasoner").classes("or-hint")
                            ui.label("May change: re-check after the build" if logical else "Unchanged (annotations only)") \
                                .classes("text-weight-medium").style("text-align:right")
                        checked = (x.checked.get("options") or []) if x.checked else []
                        c = checked[dec(x)["opt"]] if dec(x)["opt"] < len(checked) else {}
                        if c.get("new_findings"):
                            ui.label("Would add: " + "; ".join(c["new_findings"])).classes("or-hint text-negative")
                with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2 w-full"):
                    ui.label("Docs impact").classes("or-h2")
                    ui.label("Shown on the next build").classes("or-hint")
                    what = {"label": "label", "definition": "definition", "subClassOf": "parents list",
                            "equivalentClass": "equivalences", "domain": "domain", "range": "range", "title": "document title",
                            "description": "introduction", "license": "license and citation", "creator": "authors",
                            "versionInfo": "version", "isReplacedBy": "replacement link", "altLabel": "other labels",
                            "type": "kind of term"}
                    rows = []
                    for t3 in (o.add + o.remove) if o else []:
                        key = next((k for k in what if k in t3[1]), None)
                        if key:
                            rows.append((label_of(str(n3term(t3[0]))), what[key]))
                    if o and any("subClassOf" in t3[1] for t3 in o.add + o.remove):
                        rows.append(("Class diagram", "updated"))
                    rows.append(("Quality report", "issue cleared"))
                    for a, b in list(dict.fromkeys(rows))[:6]:
                        with ui.row().classes("w-full justify-between no-wrap q-pa-xs").style(
                                "background:var(--or-line-2);border-radius:6px"):
                            ui.label(a).classes("or-mono ellipsis").style("font-size:12.5px")
                            ui.label(b).classes("or-hint")
                with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-1 w-full"):
                    ui.label("Made by").classes("or-h2")
                    mb = x.made_by or {}
                    if mb.get("type") == "llm":
                        ui.label(f"AI draft · {mb.get('provider') or mb.get('source')}").classes("text-weight-medium")
                        ui.label(f"{mb.get('model')}" + (f" · {str(mb.get('revision'))[:16]}" if mb.get("revision") else ""))\
                            .classes("or-hint or-mono")
                        ui.label("Recorded as AI-assisted in the provenance when accepted.").classes("or-hint")
                    else:
                        ui.label({"D": "Rule", "A": "Ranked candidates", "U": "Your input", "M": "—"}.get(x.kind, x.source))\
                            .classes("text-weight-medium")
                        ui.label(mb.get("id", x.rule) + (f" · {mb['method']}" if mb.get("method") else "")) \
                            .classes("or-hint or-mono")
                t = session.onto.terms.get(x.subject or "")
                if t is not None and t.kind == "class":
                    chain, cur, seen = [], t, set()
                    while cur is not None and cur.iri not in seen and len(chain) < 6:
                        seen.add(cur.iri)
                        chain.append(cur)
                        nxt = cur.superclasses[0].iri if cur.superclasses else None
                        cur = session.onto.terms.get(nxt) if nxt else None
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-1 w-full"):
                        ui.label("Hierarchy context").classes("or-h2")
                        names = ["owl:Thing"] + [c.curie or c.label for c in reversed(chain)]
                        for depth, nm in enumerate(names):
                            ui.label(nm).classes("or-mono").style(
                                f"padding-left:{depth * 14}px;font-size:12.5px;border-left:1px solid var(--or-line);"
                                + ("color:#b42318;font-weight:600" if depth == len(names) - 1 else ""))
                elif t is not None and t.kind in ("object_property", "datatype_property"):
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-1 w-full"):
                        ui.label("Property context").classes("or-h2")
                        for k, vals in (("Domain", t.domain), ("Range", t.range)):
                            ui.label(f"{k}: " + (", ".join(str(getattr(v, 'label', v)) for v in vals) or "none")) \
                                .classes("or-hint")

        ai_status = {"state": "idle", "msg": ""}      # idle | working | ok | error: colours the header chip

        def sync_header() -> None:
            """The header buttons, rebuilt to show the current count and what is still required."""
            required = session.required_open() if session.cfg.require_metadata else []
            n = len(session.accepted)
            ai = prefs.ai_config()
            ai_text = ("AI: " + {"hf": f"Hugging Face · {ai.hf_model}", "ollama": f"Ollama · {ai.ollama_model}",
                                 "api": f"{ai.api_provider} · {ai.api_model or '?'}"}.get(ai.priority[0], "")) \
                if prefs.ai_enabled else "AI: off"
            verb = "build" if fs["mode"] == "prebuild" else "rebuild"
            header_box.clear()
            with header_box:
                st_ = ai_status["state"]
                chip = ui.button({"working": "AI working… · ", "error": "AI failed · "}.get(st_, "") + ai_text,
                                 icon={"working": "auto_awesome", "ok": "check_circle", "error": "error"}
                                 .get(st_, "auto_awesome"),
                                 on_click=lambda: (state.__setitem__("settings_tab", "ai"), ui.navigate.to("/settings"))) \
                    .props("flat dense no-caps").mark("ai-status") \
                    .tooltip(ai_status["msg"] or "AI drafts are applied only when you accept them · Settings")
                if st_ in ("working", "ok", "error"):
                    chip.classes(f"or-ai-{st_}")
                ui.button("Re-run checks", icon="refresh", on_click=lambda: rerun()).props("outline no-caps")
                if fs["mode"] == "prebuild":
                    sk = ui.button("Skip and build", on_click=lambda: finish(skip=True)).props("outline no-caps") \
                        .mark("issues-skip")
                    sk.set_enabled(not required)
                    sk.tooltip("Accept the required metadata first" if required else "Build from the original file")
                ap = ui.button(f"Apply {n} fix{'es' if n != 1 else ''} & {verb} docs", icon="build",
                               on_click=lambda: finish(skip=False)).props("unelevated no-caps").mark("issues-apply")
                ap.set_enabled(n > 0 and not required)
                if required:
                    ap.tooltip("Accept the required metadata first: " + ", ".join(x.title.lower() for x in required))

        def render_all() -> None:
            render_left()
            render_centre()
            render_side()
            sync_header()

        def accept(x) -> None:
            d = dec(x)
            try:
                if d.get("custom") and x.rule in ("OB012", "OB013"):
                    from .fixes.model import Suggestion as _Sug
                    own = _Sug(x.rule, x.subject, "U", x.title.replace(" (AI suggestion)", ""),
                               "Chosen by you instead of the AI suggestions.", options=[chosen_option(x)],
                               made_by={"type": "user", "id": f"fix-{x.rule.lower()}"})
                    session.replace(own)
                    session.accept(own.id)
                    fs["dec"][own.id] = {"opt": 0, "values": {}, "text": "", "status": "accepted"}
                    fs["sel"] = own.id
                    render_all()
                    return
                if x.fields:
                    session.accept(x.id, values=d["values"])
                elif x.kind == "L":
                    session.accept(x.id, option=d["opt"], text=d["text"])
                else:
                    session.accept(x.id, option=d["opt"])
            except FixError as e:
                notify(str(e), "warning")
                return
            d["status"] = "accepted"
            nxt = next((y for y in visible() if dec(y)["status"] == "open" and y.id != x.id), None)
            if nxt is not None:
                fs["sel"] = nxt.id
            render_all()

        def undo(x) -> None:
            session.reject(x.id)
            dec(x)["status"] = "open"
            render_all()

        def ignore(x) -> None:
            ids = ignored_ids() | {x.id}
            prefs.fix_ignored = " ".join(sorted(ids))
            prefs.save()
            ignored.add(x.id)
            session.reject(x.id)
            dec(x)["status"] = "ignored"
            notify("Ignored in future builds (Show ignored brings it back).")
            render_all()

        ai_lock = {"busy": False}

        def set_ai(state_: str, msg: str = "") -> None:
            ai_status.update(state=state_, msg=msg)
            sync_header()

        def mark_btn(btn, how: str, text: str, icon: str) -> None:
            """Show on the clicked button what the AI is doing (it may be gone after a re-render)."""
            if btn is None or btn.is_deleted:
                return
            btn.classes(remove="or-ai-working or-ai-ok or-ai-err")
            if how:
                btn.classes(f"or-ai-{how}")
            btn.set_text(text)
            btn.props(f"icon={icon}")
            btn.set_enabled(how != "working")

        async def ensure_ai():
            """The AI source, downloaded (Hugging Face, first use) and loaded, with progress on the page."""
            from .fixes.ai import pick_source
            src = await run.io_bound(pick_source, prefs.ai_config(), prefs.hf_token or None)
            if src.name != "hf":
                return src
            ai_bar.set_visibility(True)
            if not await run.io_bound(src.cached):
                total = await run.io_bound(src.total_bytes)

                def tick() -> None:
                    got = src.downloaded_bytes()
                    ai_msg.set_text(f"Downloading {src.model} from Hugging Face (first use only): "
                                    f"{got / 1e9:.1f}" + (f" of {total / 1e9:.1f} GB" if total else " GB"))
                    ai_prog.set_value(min(got / total, 1.0) if total else 0)
                tick()
                timer = ui.timer(1.0, tick)
                try:
                    await run.io_bound(src.prepare)
                finally:
                    timer.cancel()
            ai_msg.set_text(f"Loading {src.model} into memory…")
            ai_prog.props("indeterminate")
            await run.io_bound(src.load)
            ai_prog.props(remove="indeterminate")
            ai_bar.set_visibility(False)
            return src

        async def ai_fill(ta, name: str, x, btn=None) -> None:
            from .fixes.ai import AIError, draft_definition, draft_description
            label = btn.text if btn is not None else "Draft with AI"
            if ai_lock["busy"]:
                notify("AI is already working (see the bar above); try again when it is done.")
                return
            ai_lock["busy"] = True
            what = {"description": "a description", "domain": "domains", "range": "ranges"}.get(name, "a definition")
            mark_btn(btn, "working", "Drafting…" if name in ("description", "definition") else "Suggesting…",
                     "auto_awesome")
            set_ai("working", f"Asking for {what}…")
            ok = False
            try:
                src = await ensure_ai()
                model = src.describe().get("model", "") if hasattr(src, "describe") else ""
                ai_bar.set_visibility(True)
                ai_msg.set_text(f"Asking {model or 'the model'} for {what}… (the first answer can take a minute)")
                ai_prog.props("indeterminate")
                if name == "description":
                    text, prov = await run.io_bound(draft_description, session, src)
                    ta.set_value(text)
                    x.made_by = prov | {"field": "description"}
                elif name in ("domain", "range"):
                    from .fixes.ai import suggest_domain_range
                    sug = await run.io_bound(suggest_domain_range, session, x.subject, name, src)
                    session.replace(sug)
                    fs["sel"] = sug.id
                    render_all()
                else:
                    draft = await run.io_bound(draft_definition, session, x.subject, src)
                    session.replace(draft)
                    fs["sel"] = draft.id
                    render_all()
                ok = True
            except (AIError, Exception) as e:  # noqa: BLE001
                notify(f"AI: {e}", "warning")
                mark_btn(btn, "err", "AI failed · retry", "error")
                set_ai("error", f"Last request failed: {e}")
            finally:
                ai_lock["busy"] = False
                ai_prog.props(remove="indeterminate")
                ai_bar.set_visibility(False)
            if ok:
                mark_btn(btn, "ok", "Drafted · review it" if name == "description" else "Done", "check_circle")
                set_ai("ok", f"{what[0].upper() + what[1:]} ready for review")

                def back() -> None:
                    mark_btn(btn, "", label, "auto_awesome")
                    if ai_status["state"] == "ok":
                        set_ai("idle")
                ui.timer(4.0, back, once=True)

        async def auto_drafts() -> None:
            """AI drafts for every term without a definition, automatically (the model is downloaded on
            first use, with progress); each draft appears as it is ready, applied only when accepted."""
            from .fixes.ai import AIError as _AIError
            from .fixes.ai import draft_definition, suggest_domain_range
            todo = [x for x in session.suggestions if x.rule in ("OB011", "OB012", "OB013") and x.kind == "U"]
            if not prefs.ai_enabled or not todo or ai_lock["busy"]:
                return
            ai_lock["busy"] = True
            set_ai("working", f"Drafting AI suggestions for {len(todo)} issues…")
            failed: list[str] = []
            try:
                src = await ensure_ai()
                if ai_bar.is_deleted:
                    return
                desc = src.describe() if src.name != "hf" else {"provider": "Hugging Face", "model": src.model}
                ai_bar.set_visibility(True)
                for i, x in enumerate(todo, 1):
                    if ai_bar.is_deleted:       # the page was left; stop drafting for it
                        return
                    if x.id in session.accepted or x not in session.suggestions:
                        continue
                    ai_msg.set_text(f"AI suggestions with {desc.get('provider')} · {desc.get('model')}: "
                                    f"{i} of {len(todo)}")
                    ai_prog.set_value(i / len(todo))
                    try:
                        if x.rule == "OB011":
                            draft = await run.io_bound(draft_definition, session, x.subject, src)
                        else:
                            draft = await run.io_bound(suggest_domain_range, session, x.subject,
                                                       "domain" if x.rule == "OB012" else "range", src)
                    except _AIError as e:
                        failed.append(str(e))
                        continue            # keep the field to fill by hand
                    session.replace(draft)
                    if ai_bar.is_deleted:
                        return
                    if fs["sel"] == x.id:
                        fs["sel"] = draft.id
                    render_all()
                if failed and len(failed) == len(todo):      # nothing came back: say why, not "ready"
                    notify(f"AI could not draft any suggestion: {failed[-1]}", "warning")
                    set_ai("error", f"AI drafts failed: {failed[-1]}")
                    return
                notify("AI suggestions ready to review; nothing is applied until you accept."
                       + (f" {len(failed)} could not be drafted ({failed[-1][:120]})." if failed else ""),
                       "positive" if not failed else "warning")
                set_ai("ok", "AI suggestions ready for review")
                ui.timer(4.0, lambda: ai_status["state"] == "ok" and set_ai("idle"), once=True)
            except Exception as e:  # noqa: BLE001
                notify(f"AI: {e}", "warning")
                set_ai("error", f"AI suggestions failed: {e}")
            finally:
                ai_lock["busy"] = False
                if not ai_bar.is_deleted:
                    ai_bar.set_visibility(False)

        async def rerun() -> None:
            from .fixes import FixSession
            try:
                new = await run.io_bound(FixSession, str(session.source))
                await run.io_bound(new.precheck)
            except Exception as e:  # noqa: BLE001
                notify(str(e), "warning")
                return
            fs.update(session=new, dec={}, sel=None)
            ui.navigate.reload()

        async def finish(skip: bool) -> None:
            if state["running"]:
                notify("Another build is running; apply or skip when it has finished (your choices are kept).",
                       "warning")
                return
            # build exactly the ontology reviewed here, with the settings it was started with
            same = job is not None and Path(job.source).expanduser().resolve() == Path(session.source).resolve()
            base = job if same else Settings(**{**asdict(job or s), "source": str(session.source)})
            if not skip:
                try:
                    result = await run.io_bound(session.write)
                except FixError as e:
                    notify(str(e), "warning")
                    return
                base = Settings(**{**asdict(base), "source": str(result.path)})
                notify(f"{result.path.name} written ({result.applied} fixes). Building the docs from it.", "positive")
            SESSION.finish_review(fs.get("key", ""), "skipped" if skip else "built", "" if skip else base.source)
            state["pending_job"] = base
            ui.navigate.to("/")

        async def load_external() -> None:
            """ROBOT, the reasoner, IRI checks, OntoCheck and OOPS! in the background; their issues join the list."""
            if session.external is not None:
                return
            ext_bar.set_visibility(True)
            try:
                reports = await run.io_bound(session.run_external)
                if ext_bar.is_deleted:          # the page was left while the checks ran
                    return
                errs = [f"{r.tool}: {r.error}" for r in reports if r.error]
                ext_msg.set_text("")
                if errs:
                    notify("Some checks could not run: " + "; ".join(errs)[:300], "warning")
                render_all()
            except Exception as e:  # noqa: BLE001
                notify(f"The other checks could not run: {e}", "warning")
            finally:
                if not ext_bar.is_deleted:
                    ext_bar.set_visibility(False)

        async def start_page() -> None:
            await load_external()
            if not ext_bar.is_deleted:
                await auto_drafts()

        render_all()
        ui.timer(0.2, start_page, once=True)

    # ------------------------------------------------------------------ Interoperability
    def interop_view() -> None:  # noqa: C901
        """Cross-domain and scientific interoperability of one ontology, on its own page (like Compare)."""
        from .quality_checks.cdi.si import OECD_FOS

        set_active("interop")
        st = SESSION.interop
        if st["s"] is None:
            st["s"] = Settings(**{**asdict(s), "task": "interop", "output": ""})
        iop: Settings = st["s"]
        iop.task = "interop"
        head = page_head("Interoperability", "How well an ontology connects to other domains (cross-domain, CDI) "
                                             "and to how many scientific fields (scientific, SI).")
        with head:
            run_btn = ui.button("Run checks", icon="hub", on_click=lambda: run_iop()) \
                .props("unelevated no-caps").mark("interop-run")
        with ui.element("div").classes("or-body column gap-4"):
            with ui.row().classes("w-full gap-4 no-wrap max-md:flex-wrap items-stretch"):
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 0; min-width: 0"):
                    with ui.column().classes("or-sec gap-3"):
                        ui.label("Ontology").classes("or-h2")
                        with ui.element("div").props('data-zone="iop-source"').classes("ob-dropzone w-full"):
                            src_box = ui.column().classes("w-full gap-2")
                        with ui.row().classes("gap-2"):
                            ui.button("File", icon="description", on_click=lambda: pick(
                                "ontology", set_source, False, iop.source, title="Choose the ontology")) \
                                .props("outline no-caps dense").classes("px-3")
                            ui.button("URL", icon="link", on_click=lambda: ask_url()).props("outline no-caps dense") \
                                .classes("px-3")
                        src_info = ui.label("Drop an ontology file, choose one, or give a URL.").classes("or-hint")
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 0; min-width: 0"):
                    with ui.column().classes("or-sec gap-2"):
                        ui.label("Save report to").classes("or-h2")
                        with ui.row().classes("w-full no-wrap gap-2 items-center"):
                            out_in = ui.input(on_change=lambda: show_out()).bind_value(iop, "output") \
                                .props('outlined dense clearable aria-label="Save report to"').classes("grow or-mono")
                            ui.button("Browse…", on_click=lambda: pick("any", lambda p: out_in.set_value(p), True,
                                                                       iop.output, "Where to save the report")) \
                                .props("outline no-caps")
                        out_info = ui.label().classes("or-hint or-mono").style("word-break: break-all")
                        ui.label("Runs in the background; you can switch pages. Each run is kept in Run history.") \
                            .classes("or-hint")
            with ui.row().classes("w-full gap-4 no-wrap max-md:flex-wrap items-stretch"):
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 0; min-width: 0"):
                    with ui.column().classes("or-sec gap-3"):
                        ui.label("Cross-domain interoperability").classes("or-h2")
                        ui.checkbox("Score cross-domain interoperability (CDI)").bind_value(iop, "cdi").mark("iop-cdi")
                        ui.label("Reference ontologies, one per line").classes("or-label")
                        refs = ui.textarea(placeholder="ols\nols:envo,chebi\nbioportal:NCIT\n/path/to/ref.owl") \
                            .bind_value(iop, "cdi_references").mark("iop-references") \
                            .props('outlined dense autogrow aria-label="Reference ontologies"').classes("w-full or-mono")

                        def add_refs(paths: list[str]) -> None:
                            lines = [x for x in iop.cdi_references.splitlines() if x.strip()]
                            refs.set_value("\n".join(lines + [p for p in paths if p not in lines]))

                        with ui.element("div").props('data-zone="iop-refs"').classes("ob-dropzone w-full"):
                            with ui.row().classes("w-full items-center no-wrap gap-2"):
                                ui.icon("upload_file", size="20px").classes("text-primary")
                                refs_drop = ui.label("Drop reference ontologies or SSSOM files here").classes("or-hint grow")
                                ui.button("Browse…", on_click=lambda: pick(
                                    "any", lambda p: add_refs([p]), False,
                                    title="Choose a reference ontology or SSSOM file")).props("outline no-caps")
                        repo_picker(add_refs)
                        ui.label("ols / bioportal alone: find ontologies with matching terms and keep the top "
                                 f"{iop.cdi_top_n or 10}. Repositories receive labels and IRIs, never the file.") \
                            .classes("or-hint")
                        ui.label("Own domain(s), left out of discovery").classes("or-label")
                        ui.input(placeholder="e.g. agriculture").bind_value(iop, "cdi_domains") \
                            .props('outlined dense clearable aria-label="Own domains"').classes("w-64")
                with ui.card().classes("or-card").props("flat").style("flex: 1 1 0; min-width: 0"):
                    with ui.column().classes("or-sec gap-3"):
                        ui.label("Scientific interoperability").classes("or-h2")
                        ui.checkbox("Score scientific interoperability (SI)").bind_value(iop, "si").mark("iop-si")
                        same = ui.checkbox("Use the cross-domain reference ontologies",
                                           value=not iop.si_references.strip())
                        with ui.column().classes("w-full gap-2") as own_box:
                            si_refs = ui.textarea(placeholder="ols:envo\nbioportal:NCIT\n/path/to/ref.owl") \
                                .bind_value(iop, "si_references") \
                                .props('outlined dense autogrow aria-label="SI reference ontologies"').classes("w-full or-mono")

                            def add_si(paths: list[str]) -> None:
                                lines = [x for x in iop.si_references.splitlines() if x.strip()]
                                si_refs.set_value("\n".join(lines + [p for p in paths if p not in lines]))
                            ui.button("Browse…", icon="upload_file", on_click=lambda: pick(
                                "any", lambda p: add_si([p]), False, title="Choose a reference ontology")) \
                                .props("outline no-caps")
                            repo_picker(add_si)

                        def same_changed(e) -> None:
                            own_box.set_visibility(not e.value)
                            if e.value:
                                si_refs.set_value("")
                        same.on_value_change(same_changed)
                        own_box.set_visibility(not same.value)
                        with ui.row().classes("gap-4 items-end"):
                            with ui.column().classes("gap-1"):
                                ui.label("Own scientific domain").classes("or-label")
                                ui.select({"": "Detect from title and description",
                                           **{c: f"{c} {n}" for c, n in OECD_FOS.items()}}) \
                                    .bind_value(iop, "si_home_domain") \
                                    .props('outlined dense aria-label="Own scientific domain"').classes("w-80")
                            with ui.column().classes("gap-1"):
                                ui.label("θ_s").classes("or-label")
                                ui.number(min=0, max=1, step=0.05, format="%.2f").bind_value(
                                    iop, "si_theta_s", forward=lambda v: float(0.3 if v is None else v)) \
                                    .props('outlined dense aria-label="Threshold theta s"').classes("w-28")
                        ui.label("Domain of a reference ontology (optional)").classes("or-label")
                        domain_rows(lambda: iop.si_domain_map, lambda v: setattr(iop, "si_domain_map", v))
            results = ui.column().classes("w-full gap-4")

        def show_out() -> None:
            out_info.text = (f"Writes {iop.output_path()}" + ("" if iop.output.strip() else "  (default)")
                             if iop.source else "Choose the ontology first.")

        def render_source() -> None:
            src_box.clear()
            with src_box:
                val = iop.source
                if val:
                    is_url = val.startswith(("http://", "https://"))
                    with ui.element("div").classes("or-chip"):
                        with ui.element("div").classes("or-chipicon"):
                            ui.icon("link" if is_url else "description", size="20px")
                        with ui.column().classes("gap-0 grow min-w-0"):
                            ui.label(val if is_url else Path(val).name).classes("or-label ellipsis w-full")
                            if not is_url:
                                ui.label(str(Path(val).parent) + "/").classes("or-hint or-mono ellipsis w-full")
                        ui.button(icon="close", on_click=lambda: set_source("")) \
                            .props('flat round dense aria-label="Clear the ontology"')
                else:
                    inp = ui.input(placeholder="Type a path or URL and press Enter, or drop a file here") \
                        .props('borderless dense aria-label="Ontology path or URL"').classes("w-full or-mono") \
                        .mark("iop-source")
                    inp.on("keydown.enter", lambda: set_source((inp.value or "").strip()))

        def set_source(value: str) -> None:
            if value and not value.startswith(("http://", "https://")):
                pth = Path(value).expanduser()
                if not pth.exists():
                    notify(f"Not found: {value}", "warning")
                    return
            iop.source = value
            iop.output = iop.output if value else ""
            render_source()
            show_out()

        def ask_url() -> None:
            with ui.dialog() as dlg, ui.card().classes("or-card w-[36rem] max-w-full"):
                ui.label("Ontology URL or path").classes("or-h2")
                inp = ui.input(placeholder="https://… or /path/to/ontology.ttl", value=iop.source) \
                    .props("outlined autofocus").classes("w-full or-mono")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Cancel", on_click=dlg.close).props("flat no-caps")
                    ui.button("Use", on_click=lambda: (set_source(inp.value.strip()), dlg.close())) \
                        .props("unelevated no-caps")
            dlg.open()

        def summaries(res) -> dict[str, dict]:
            """{tool: provenance summary or {"error": …}} from the written report."""
            try:
                data = json.loads(Path(res.index or res.output).read_text("utf-8"))
            except (OSError, ValueError):
                return {}
            entry = next(iter(data.values()), {}) if isinstance(data, dict) else {}
            out = {}
            for ext in entry.get("external", []) if isinstance(entry, dict) else []:
                out[ext["tool"]] = {"error": ext["error"]} if ext.get("error") else \
                    (ext.get("provenance") or {}).get("summary", {})
            return out

        def new_check() -> None:
            if not st["running"]:
                st["last"] = None
                render()

        def render() -> None:
            results.clear()
            run_btn.set_enabled(not st["running"])
            run_btn.text = "Running…" if st["running"] else "Run checks"
            with results:
                if st["running"]:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.row().classes("or-sec items-center gap-3"):
                            ui.spinner(size="22px")
                            ui.label(f"Checking {Path(iop.source).name or iop.source}…").classes("or-h2")
                            ui.label("Repository lookups and the language model can take a few minutes.") \
                                .classes("or-hint")
                    return
                res = st["last"]
                if res is None:
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2 items-center text-center q-py-xl"):
                            ui.icon("hub", size="40px").classes("or-muted")
                            ui.label("No interoperability check yet").classes("or-h2")
                            ui.label("Choose the ontology and its reference ontologies (upload, name them on OLS or "
                                     "BioPortal, or let OntoReview find them), then press Run checks.").classes("or-hint")
                    return
                if isinstance(res, Exception):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-2"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label("Check failed").classes("or-h2")
                                    badge("err", "Failed")
                                ui.button("New check", icon="add", on_click=new_check).props("flat no-caps")
                            ui.label(str(res)).classes("or-mono or-hint")
                    return
                row = res.rows[0]
                sm = summaries(res)
                with ui.card().classes("or-card w-full").props("flat"):
                    with ui.column().classes("or-sec gap-3"):
                        with ui.row().classes("w-full items-start justify-between gap-3"):
                            with ui.column().classes("gap-1 min-w-0"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(row.title or row.name).classes("or-h2")
                                    badge("err", "Failed") if row.problem else badge("ok", "Done")
                                ui.label(f"Interoperability check · {res.seconds:.1f} s · {res.output}") \
                                    .classes("or-hint or-mono")
                            with ui.row().classes("gap-2"):
                                ui.button("New check", icon="add", on_click=new_check).props("flat no-caps") \
                                    .mark("iop-new")
                                ui.button("Open report (JSON)", icon="open_in_new",
                                          on_click=lambda: open_result(res.index or str(res.output))).props("unelevated no-caps")
                                ui.button("Export", icon="download", on_click=lambda: export(str(res.output))) \
                                    .props("outline no-caps")
                                ui.button("Show in folder", icon="folder_open",
                                          on_click=lambda: reveal(str(res.output))).props("outline no-caps")
                        if row.problem:
                            ui.label(row.problem).classes("or-mono or-hint")
                        with ui.row().classes("w-full gap-3"):
                            c = sm.get("Cross-domain interoperability")
                            si_ = sm.get("Scientific interoperability")
                            for label, val, sub_ in (
                                    ("Cross-domain interoperability (CDI)",
                                     None if not c or c.get("error") or c.get("cdi") is None else f"{c['cdi']:.2f}",
                                     (c or {}).get("error") or (("interoperable" if c.get("interoperable") else
                                                                 f"below θ = {c['params']['theta']}") if c and c.get("cdi") is not None else "")),
                                    ("Scientific interoperability (SI)",
                                     None if not si_ or si_.get("error") else str(si_["si"]),
                                     (si_ or {}).get("error") or (f"of {si_['taxonomy_size'] - 1} domains: "
                                                                  + (", ".join(si_["covered_domains"]) or "none covered")
                                                                  if si_ else ""))):
                                if val is None and not sub_:
                                    continue
                                with ui.element("div").classes("or-tile " + ("err" if val is None else "")):
                                    ui.label(label).classes("k")
                                    ui.label(val if val is not None else "–").classes("v")
                                    ui.label(sub_).classes("or-hint").style("word-break:break-word")
                if row.metrics:
                    metrics_grid(row.metrics, "Interoperability", "iop-metrics")
                for n in row.notes:
                    ui.label(n).classes("or-hint")

        async def run_iop() -> None:
            if st["running"]:
                return
            job = Settings(**{**asdict(iop), "task": "interop"})
            problems = job.validate()
            if not job.source.strip():
                problems = ["Choose the ontology first."] + problems
            if problems:
                for p_ in problems:
                    notify(p_, "warning")
                return
            st.update(running=True, started=time.time())
            background_tasks.create(iop_job(job), name="ontoreview-interop")
            iop_sync()

        async def iop_job(job: Settings) -> None:
            """Runs independently of this view: switching pages does not stop or lose it."""
            try:
                res = await run.io_bound(run_task, job)
            except Exception as e:  # noqa: BLE001
                st["last"] = e
                if prefs.keep_history:
                    record_run(job, None, str(e), limit=prefs.history_limit)
                notify(f"Interoperability check failed: {e}", "negative")
            else:
                st["last"] = res
                if prefs.keep_history:
                    record_run(job, res, limit=prefs.history_limit)
                notify("Interoperability check done", "positive")
            finally:
                st["running"] = False

        seen = {"sig": (st["running"], id(st["last"]))}

        def iop_sync() -> None:
            sig = (st["running"], id(st["last"]))
            if results.is_deleted or sig == seen["sig"]:
                return
            seen["sig"] = sig
            render()

        ui.timer(0.3, iop_sync)
        drop_targets.clear()

        def src_dropped(a: dict) -> None:
            target = dropped_path(a, src_info, files_only=True)
            if target:
                set_source(target)

        def refs_dropped(a: dict) -> None:
            files = upload_files(a.get("batch") or "") if a.get("ok") else []
            if not files:
                refs_drop.text = "Nothing usable was dropped: no ontology or .tsv files found."
                return
            add_refs(files)
            refs_drop.text = f"Added {len(files)} reference file(s)."

        drop_targets["iop-source"] = (lambda a: setattr(src_info, "text", "Copying…"), src_dropped)
        drop_targets["iop-refs"] = (lambda a: setattr(refs_drop, "text", "Copying…"), refs_dropped)
        render_source()
        show_out()
        render()

    # ------------------------------------------------------------------ Term database
    def terms_view() -> None:  # noqa: C901
        from .quality_checks import iri as iri_db

        set_active("terms")
        page_head("Term database", "The SQLite database the IRI checks use: bundled W3C vocabularies, everything "
                                   "looked up or downloaded since, and every IRI-check run.")
        st = {"tab": "search", "query": "", "document": None, "document_title": ""}
        with ui.element("div").classes("or-body column gap-4"):
            stats = ui.label().classes("or-hint or-mono").style("word-break: break-all")
            with ui.tabs().classes("or-tabs").props("align=left no-caps inline-label") as tabs:
                t_search = ui.tab("search", "Search", icon="search")
                t_docs = ui.tab("docs", "Ontologies, vocabularies & schemas", icon="library_books")
                t_add = ui.tab("add", "Add ontology", icon="add_circle_outline")
                t_runs = ui.tab("runs", "Runs", icon="history")
            with ui.tab_panels(tabs, value=t_search).classes("w-full").style("background: transparent"):
                with ui.tab_panel(t_search).classes("q-pa-none"):
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-3 w-full"):
                        with ui.row().classes("w-full no-wrap gap-2 items-center"):
                            q_in = ui.input(placeholder="Search IRIs and labels, e.g. Entity or prov#Agent") \
                                .props('outlined dense clearable autofocus aria-label="Search terms"') \
                                .classes("grow").mark("term-search")
                            ui.button("Search", icon="search", on_click=lambda: search()).props("unelevated no-caps")
                        doc_filter = ui.row().classes("items-center gap-2")
                        results_box = ui.column().classes("w-full gap-2")
                    q_in.on("keydown.enter", lambda: search())
                with ui.tab_panel(t_docs).classes("q-pa-none"):
                    docs_box = ui.column().classes("w-full gap-3")
                with ui.tab_panel(t_add).classes("q-pa-none"):
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-3 w-full"):
                        ui.label("From a URL").classes("or-h2")
                        ui.label("An ontology IRI or download URL. RDF is requested with content negotiation "
                                 "(Turtle, RDF/XML, N-Triples); HTML pages are rejected.").classes("or-hint")
                        with ui.row().classes("w-full no-wrap gap-2 items-center"):
                            url_in = ui.input(placeholder="https://www.w3.org/ns/dcat3.ttl") \
                                .props('outlined dense clearable aria-label="Ontology URL"').classes("grow or-mono") \
                                .mark("term-add-url")
                            ui.button("Add", icon="cloud_download", on_click=lambda: add(url=url_in.value)) \
                                .props("unelevated no-caps").mark("term-add-url-go")
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-3 w-full"):
                        ui.label("From a file").classes("or-h2")
                        with ui.element("div").props('data-zone="termdb"').classes("ob-dropzone w-full"):
                            with ui.column().classes("w-full items-center gap-1 q-py-lg"):
                                ui.icon("upload_file", size="32px").classes("or-muted")
                                ui.label("Drop ontology files here (.ttl, .owl, .rdf, .nt, .jsonld)").classes("or-label")
                                ui.button("Choose file…", icon="description", on_click=lambda: pick(
                                    "ontology", lambda p_: add(path=p_), False, title="Add an ontology to the database")) \
                                    .props("outline no-caps dense").classes("q-mt-sm")
                        add_info = ui.label().classes("or-hint").props('aria-live="polite"')
                        ui.label("Each document is indexed by its owl:Ontology IRI (or its URL / file name): typed "
                                 "classes, properties and individuals with their labels and deprecation flags. "
                                 "Adding the same document again replaces it.").classes("or-hint")
                with ui.tab_panel(t_runs).classes("q-pa-none"):
                    runs_box = ui.column().classes("w-full gap-3")

        def show_stats(groups) -> None:
            b = [g for g in groups if g["where"] == "bundled"]
            c = [g for g in groups if g["where"] == "cache"]
            stats.text = (f"Bundled: {len(b)} ontologies/vocabularies, {sum(g['terms'] for g in b):,} terms · "
                          f"Cache: {len(c)} ontologies/vocabularies, {sum(g['terms'] for g in c):,} terms · "
                          f"{iri_db.default_cache_path()}")

        async def search() -> None:
            query = (q_in.value or "").strip()
            st["query"] = query
            results_box.clear()
            doc_filter.clear()
            if st["document"]:
                with doc_filter:
                    ui.label("In").classes("or-hint")
                    ui.chip(st["document_title"] or "selected", removable=True).props("dense outline").on(
                        "remove", lambda: (st.update(document=None, document_title=""), background_tasks.create(search())))
            if not query and not st["document"]:
                with results_box:
                    ui.label("Type part of an IRI or label. Prefix aliases don't matter: terms are stored by full "
                             "IRI, so prov:Entity and ap:Entity are the same term.").classes("or-hint q-py-sm")
                return
            rows = await run.io_bound(iri_db.search_terms, query, None, 300, st["document"])
            if results_box.is_deleted:
                return
            with results_box:
                ui.label(f"{len(rows)} term{'s' if len(rows) != 1 else ''}" + (" (first 300)" if len(rows) >= 300 else "")) \
                    .classes("or-hint")
                if rows:
                    short = lambda t: t.rsplit("#", 1)[-1].rsplit("/", 1)[-1]  # noqa: E731
                    data = [{"id": n, "iri": r["iri"], "label": ", ".join(r["labels"][:2]),
                             "types": ", ".join(short(t) for t in r["types"][:3]), "document": r["vocabulary"],
                             "where": r["where"], "deprecated": "deprecated" if r["deprecated"] else ""}
                            for n, r in enumerate(rows)]
                    cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                            (("label", "Label"), ("iri", "IRI"), ("types", "Type"), ("document", "Ontology / vocabulary"),
                             ("where", "Stored"), ("deprecated", ""))]
                    ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 25}) \
                        .classes("or-table").props("flat dense wrap-cells").mark("term-results")

        async def show_docs() -> None:
            from urllib.parse import urlsplit

            from .config import Config

            max_age = Config().evaluation.iri_cache_days
            groups = await run.io_bound(iri_db.list_groups)
            if docs_box.is_deleted:
                return
            show_stats(groups)
            docs_box.clear()
            with docs_box:
                for where, title, hint in (("cache", "Added and downloaded", "Your writable database: ontologies, "
                                            "vocabularies and schemas added here, downloaded during IRI checks, or "
                                            "found in OLS/BioPortal. Click one for details."),
                                           ("bundled", "Bundled with OntoReview", "Read-only W3C vocabulary snapshots "
                                            "(see data/iri/THIRD_PARTY_NOTICES.txt). Click one for details.")):
                    section = [g for g in groups if g["where"] == where]
                    with ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2 w-full"):
                        ui.label(f"{title} ({len(section)})").classes("or-h2")
                        ui.label(hint).classes("or-hint")
                        if not section:
                            ui.label("Nothing here yet. Add an ontology, or run a build: external terms are cached "
                                     "automatically.").classes("or-hint q-py-sm")
                        for g in section:
                            age = g.get("age_days")
                            old = age is not None and age > max_age > 0
                            hosts = sorted({urlsplit(u).netloc or Path(urlsplit(u).path).name for u in g["sources"]})
                            n_docs = len(g["documents"])
                            with ui.row().classes("w-full items-center gap-3 no-wrap q-py-sm cursor-pointer").style(
                                    "border-top: 1px solid var(--or-line-2)").on(
                                    "click", lambda g=g: group_details(g, max_age)).mark("term-vocab"):
                                with ui.column().classes("gap-0 grow min-w-0"):
                                    ui.label(g["title"]).classes("text-weight-medium ellipsis w-full").style(
                                        "font-size: 15px")
                                    ui.label(f"{g['terms']:,} terms"
                                             + (f" · {n_docs} documents" if n_docs > 1 else "")
                                             + (f" · {', '.join(hosts[:2])}" if hosts else "")
                                             + f" · retrieved {g['fetched_at'][:10]}"
                                             + (f" ({age:.0f} days ago)" if age is not None else "")) \
                                        .classes("or-hint ellipsis w-full").style(
                                            "color: var(--or-warn, #B54708)" if old else "")
                                    ui.label(g["group"]).classes("or-hint or-mono ellipsis w-full").style("font-size: 11px")
                                ui.button("Browse", on_click=lambda g=g: browse_group(g)) \
                                    .props("flat dense no-caps").on("click.stop", lambda: None)
                                ui.icon("chevron_right", size="20px").classes("or-muted")

        def browse_group(g: dict) -> None:
            st.update(document=g["keys"], document_title=g["title"])
            tabs.set_value("search")
            background_tasks.create(search())

        def group_details(g: dict, max_age: float) -> None:
            age = g.get("age_days")
            with docs_box, ui.dialog() as dlg, ui.card().classes("or-card w-[52rem] max-w-full"):
                ui.label(g["title"]).classes("or-h2")
                ui.label("Bundled with OntoReview (read-only)" if g["where"] == "bundled"
                         else "In your writable database").classes("or-hint")

                def field(name: str, value: str, mono: bool = False) -> None:
                    if not value:
                        return
                    with ui.row().classes("w-full no-wrap gap-4 items-start"):
                        ui.label(name).classes("or-label").style("min-width: 150px")
                        ui.label(value).classes("grow" + (" or-mono" if mono else "")).style("word-break: break-all")

                field("IRI", g["group"], True)
                field("Terms", f"{g['terms']:,}")
                field("Version IRI", ", ".join(g["version_iris"]), True)
                field("License", ", ".join(g["licenses"]))
                field("Source", "\n".join(g["sources"][:3]) + (f"\n… {len(g['sources']) - 3} more"
                                                                 if len(g["sources"]) > 3 else ""), True)
                field("Retrieved", f"{g['fetched_at'][:19].replace('T', ' ')} UTC"
                      + (f" ({age:.0f} days ago)" if age is not None else ""))
                if age is not None and age > max_age > 0:
                    ui.label(f"Older than {max_age:g} days: refreshed automatically on the next online IRI check, "
                             "or now with Refresh. Builds keep the release they were checked against in their own "
                             "provenance.").classes("or-hint").style("color: var(--or-warn, #B54708)")
                if len(g["documents"]) > 1:
                    ui.label(f"{len(g['documents'])} documents (the server answers per term)").classes("or-label q-mt-sm")
                    data = [{"id": n, "key": d["key"], "terms": d["terms"], "sha": d["sha256"][:12],
                             "fetched": d["fetched_at"][:10]} for n, d in enumerate(g["documents"])]
                    cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                            (("key", "Document"), ("terms", "Terms"), ("fetched", "Retrieved"), ("sha", "SHA-256"))]
                    ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 8}) \
                        .classes("or-table").props("flat dense wrap-cells")
                else:
                    field("SHA-256", g["documents"][0]["sha256"], True)
                with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
                    ui.button("Browse terms", on_click=lambda: (dlg.close(), browse_group(g))).props("flat no-caps")
                    if any(u.startswith(("http://", "https://", "file://")) for u in g["sources"]):
                        ui.button("Refresh", icon="refresh",
                                  on_click=lambda: (dlg.close(), background_tasks.create(refresh_group(g)))) \
                            .props("outline no-caps")
                    if g["where"] == "cache":
                        ui.button("Remove", icon="delete_outline",
                                  on_click=lambda: (dlg.close(), background_tasks.create(remove_group(g)))) \
                            .props("outline no-caps color=negative")
                    ui.button("Close", on_click=dlg.close).props("unelevated no-caps")
            dlg.open()

        async def refresh_group(g: dict) -> None:
            notify(f"Refreshing {g['title']}…")
            done, errors = 0, []
            for key in g["keys"]:
                try:
                    await run.io_bound(iri_db.refresh_document, key)
                    done += 1
                except Exception as e:  # noqa: BLE001
                    errors.append(str(e)[:120])
            notify(f"{g['title']}: refreshed {done} of {len(g['keys'])}" + (f" ({errors[0]})" if errors else ""),
                   "positive" if not errors else "warning")
            await show_docs()

        async def remove_group(g: dict) -> None:
            for key in g["keys"]:
                await run.io_bound(iri_db.remove_document, key)
            notify(f"Removed {g['title']}", "positive")
            await show_docs()

        async def add(url: str | None = None, path: str | None = None) -> None:
            url = (url or "").strip() or None
            if not url and not path:
                notify("Enter a URL or choose a file.", "warning")
                return
            add_info.text = f"Adding {url or Path(path).name}…"
            try:
                res = await run.io_bound(lambda: iri_db.add_document(url=url, path=path))
            except Exception as e:  # noqa: BLE001
                add_info.text = f"Could not add it: {e}"
                notify(f"Could not add: {str(e)[:160]}", "negative")
                return
            add_info.text = f"Added {res['key']}: {res['terms']:,} terms from {res['source_url']}"
            notify(f"Added {res['terms']:,} terms", "positive")
            if url:
                url_in.set_value("")
            await show_docs()

        async def show_runs() -> None:
            runs = await run.io_bound(iri_db.recent_runs, None, 100)
            if runs_box.is_deleted:
                return
            runs_box.clear()
            with runs_box, ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2 w-full"):
                ui.label(f"IRI-check runs ({len(runs)})").classes("or-h2")
                ui.label("Every build or check with IRI checks on is recorded: settings, a summary, and each external "
                         "term's status, source and lookup attempts. The latest 500 runs are kept.").classes("or-hint")
                if not runs:
                    ui.label("No runs yet.").classes("or-hint q-py-sm")
                    return
                data = []
                for r in runs:
                    sm = r.get("summary") or {}
                    stt = sm.get("statuses", {})
                    try:
                        when = when_text(datetime.fromisoformat(r["started_at"]).timestamp())
                    except (TypeError, ValueError):
                        when = r.get("started_at") or ""
                    data.append({"id": r["id"], "when": when,
                                 "ontology": Path(r.get("source") or "").name or (r.get("ontology_iri") or ""),
                                 "terms": sm.get("external_terms", ""),
                                 "result": ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(stt.items())) or
                                           ("unfinished" if not r.get("finished_at") else "no external terms"),
                                 "offline": "offline" if (r.get("settings") or {}).get("offline") else ""})
                cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                        (("id", "#"), ("when", "When"), ("ontology", "Ontology"), ("terms", "External terms"),
                         ("result", "Result"), ("offline", ""))]
                tbl = ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 20}) \
                    .classes("or-table").props("flat dense wrap-cells").mark("term-runs")
                tbl.on("rowClick", lambda e: background_tasks.create(run_details(e.args[1]["id"])))
                ui.label("Click a run to see each term.").classes("or-hint")
            await show_cdi_runs()

        async def show_cdi_runs() -> None:
            runs = await run.io_bound(iri_db.recent_cdi_runs, None, 100)
            if runs_box.is_deleted:
                return
            with runs_box, ui.card().classes("or-card w-full").props("flat"), ui.column().classes("or-sec gap-2 w-full"):
                ui.label(f"Cross-domain interoperability runs ({len(runs)})").classes("or-h2")
                ui.label("Every CDI score is recorded with its settings, the scores, each reference ontology and "
                         "the release it was checked against, and every correspondence. Reference ontologies you "
                         "provide are added to the database.").classes("or-hint")
                if not runs:
                    ui.label("No runs yet.").classes("or-hint q-py-sm")
                    return

                def f(x):
                    return "–" if x is None else f"{x:.2f}"
                data = []
                for r in runs:
                    sm = r.get("summary") or {}
                    try:
                        when = when_text(datetime.fromisoformat(r["started_at"]).timestamp())
                    except (TypeError, ValueError):
                        when = r.get("started_at") or ""
                    data.append({"id": r["id"], "when": when,
                                 "ontology": Path(r.get("source") or "").name or (r.get("ontology_iri") or ""),
                                 "scores": f"CDI {f(sm.get('cdi'))} · Align {f(sm.get('align'))} · Gen {f(sm.get('gen'))}"
                                 if sm else "unfinished",
                                 "refs": len(sm.get("reference_ontologies") or [])})
                cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                        (("id", "#"), ("when", "When"), ("ontology", "Ontology"), ("scores", "Scores"),
                         ("refs", "References"))]
                tbl = ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 20}) \
                    .classes("or-table").props("flat dense wrap-cells").mark("cdi-runs")
                tbl.on("rowClick", lambda e: background_tasks.create(cdi_run_details(e.args[1]["id"])))
                ui.label("Click a run to see what it was checked against.").classes("or-hint")

        async def cdi_run_details(run_id: int) -> None:
            rows = await run.io_bound(iri_db.cdi_run_references, run_id)
            if runs_box.is_deleted:
                return
            with runs_box, ui.dialog() as dlg, ui.card().classes("or-card w-[64rem] max-w-full"):
                ui.label(f"CDI run #{run_id}: {len(rows)} reference ontologies").classes("or-h2")

                def rel_text(rel):
                    rel = rel or {}
                    what = rel.get("version_iri") or rel.get("version")
                    if what:
                        return what
                    if not rel:
                        return "not recorded"
                    return f"version not reported ({rel.get('identified_by', 'retrieval time')})"
                data = [{"id": n, "ref": r["ontology_id"], "title": r.get("title") or "",
                         "status": (r.get("status") or "").replace("-", " "), "given": "given" if r["given"] else "",
                         "align": "" if r.get("align_d") is None else f"{r['align_d']:.2f}",
                         "n": r.get("n_correspondences") or 0, "release": rel_text(r.get("release")),
                         "source": (r.get("release") or {}).get("source", ""),
                         "when": ((r.get("release") or {}).get("retrieved") or "")[:10]}
                        for n, r in enumerate(sorted(rows, key=lambda r: (r.get("status") != "selected",
                                                                           -(r.get("align_d") or 0))))]
                cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                        (("title", "Ontology"), ("ref", "Id"), ("status", "Status"), ("given", ""),
                         ("align", "Align_d"), ("n", "Correspondences"), ("release", "Checked against"),
                         ("source", "From"), ("when", "Retrieved"))]
                ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 15}) \
                    .classes("or-table").props("flat dense wrap-cells")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Close", on_click=dlg.close).props("flat no-caps")
            dlg.open()

        async def run_details(run_id: int) -> None:
            def load():
                from .quality_checks.iri.store import TermStore
                c = TermStore(iri_db.default_cache_path())
                try:
                    return c.run_results(run_id)
                finally:
                    c.close()
            rows = await run.io_bound(load)
            if runs_box.is_deleted:
                return
            with runs_box, ui.dialog() as dlg, ui.card().classes("or-card w-[64rem] max-w-full"):
                ui.label(f"Run #{run_id}: {len(rows)} external terms").classes("or-h2")
                def rel_text(rel):
                    rel = rel or {}
                    return rel.get("version_iri") or " ".join(x for x in (rel.get("ontology"), rel.get("version")) if x) \
                        or (rel.get("sha256") or "")[:12]

                data = [{"id": n, "iri": r["iri"], "status": r["status"].replace("_", " "),
                         "source": r.get("source") or "", "detail": (r.get("detail") or "")[:160],
                         "release": rel_text(r.get("release")), "stale": "stale" if r.get("stale") else "",
                         "tried": " → ".join(a.get("provider", "") + ":" + str(a.get("status", "")) for a in r["attempts"])}
                        for n, r in enumerate(rows)]
                cols = [{"name": k, "label": lbl, "field": k, "align": "left"} for k, lbl in
                        (("iri", "IRI"), ("status", "Status"), ("source", "Source"), ("release", "Release"),
                         ("stale", ""), ("tried", "Lookups"), ("detail", "Detail"))]
                ui.table(rows=data, columns=cols, row_key="id", pagination={"rowsPerPage": 15}) \
                    .classes("or-table").props("flat dense wrap-cells")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Close", on_click=dlg.close).props("flat no-caps")
            dlg.open()

        def on_tab(e) -> None:
            st["tab"] = e.value
            if e.value == "docs":
                background_tasks.create(show_docs())
            elif e.value == "runs":
                background_tasks.create(show_runs())
        tabs.on_value_change(on_tab)

        drop_targets.clear()

        def dropped(a: dict) -> None:
            target = dropped_path(a, add_info, files_only=False)
            if not target:
                return
            files_ = [target] if Path(target).is_file() else sorted(
                str(f) for f in Path(target).rglob("*") if f.suffix.lower() in (".ttl", ".owl", ".rdf", ".nt", ".jsonld", ".xml"))
            for f in files_:
                background_tasks.create(add(path=f))
        drop_targets["termdb"] = (lambda a: setattr(add_info, "text", "Copying…"), dropped)
        background_tasks.create(search())
        background_tasks.create(show_docs())

    # ------------------------------------------------------------------ Help
    def help_view() -> None:
        set_active("help")
        import html as _html
        import re as _re

        page_head("Help", "How to build, read, publish and configure your ontology documentation.")
        cards: dict[str, object] = {}
        navs: dict[str, object] = {}
        # what a search matches: title, steps and note, without HTML
        texts = {a: _html.unescape(_re.sub(r"<[^>]+>", " ", " ".join([t, *st, nt]))).lower()
                 for a, t, _, st, nt, _ in HELP}
        with ui.element("div").classes("or-body"):
            with ui.row().classes("w-full items-center gap-3 q-mb-md"):
                search = ui.input(placeholder="Search help, e.g. deploy, scientific, export, θ_s, OLS") \
                    .props('outlined dense clearable autofocus aria-label="Search help"') \
                    .classes("grow").style("max-width: 640px").mark("help-search")
                search.add_slot("prepend", '<q-icon name="search" />')
                found = ui.label().classes("or-hint").props('aria-live="polite"')
            with ui.row().classes("w-full gap-6 items-start no-wrap max-lg:flex-wrap"):
                with ui.element("nav").props('aria-label="Help topics"').classes("column gap-1 flex-none lg:sticky") \
                        .style("top: 16px; width: 230px"):
                    ui.label("On this page").classes("or-hint text-uppercase q-mb-xs").style("letter-spacing:.6px")
                    for anchor, title, *_ in HELP:
                        navs[anchor] = ui.link(title, f"#{anchor}").classes("or-hint").style("color: var(--or-ink-2)")
                with ui.column().classes("gap-4 grow min-w-0"):
                    nothing = ui.label().classes("or-hint q-pa-md")
                    for n, (anchor, title, shot, steps, note, links) in enumerate(HELP, 1):
                        with ui.card().classes("or-card w-full").props(f'flat id="{anchor}"') as card:
                            cards[anchor] = card
                            with ui.column().classes("or-sec gap-3"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.html(f'<span class="or-step">{n}</span>', sanitize=False)
                                    ui.label(title).classes("or-h2").style("font-size:17px")
                                with ui.row().classes("w-full gap-6 items-start no-wrap max-xl:flex-wrap"):
                                    items = "".join(f"<li>{x}</li>" for x in steps)
                                    with ui.column().classes("gap-2").style("flex: 1 1 380px; min-width: 0"):
                                        ui.html(f'<ol class="or-helplist">{items}</ol>', sanitize=False)
                                        if note:
                                            ui.html(f'<p class="or-hint" style="margin:0">{note}</p>', sanitize=False)
                                        with ui.row().classes("gap-2 q-mt-xs"):
                                            for label, target in links:
                                                external = target.startswith("http")
                                                ui.button(label, icon="open_in_new" if external else "arrow_forward",
                                                          on_click=lambda t=target: go(t)) \
                                                    .props("outline dense no-caps size=sm") \
                                                    .classes("px-2")
                                    shots = [x for x in ((shot,) if isinstance(shot, str) else shot)
                                             if x and (ASSETS / "help" / x).is_file()]
                                    if shots:
                                        with ui.column().classes("gap-3").style("flex: 1 1 520px; max-width: 760px"):
                                            for x in shots:
                                                img = ui.image(f"{STATIC_URL}/help/{x}") \
                                                    .props(f'alt="Screenshot: {title}" fit=contain no-spinner') \
                                                    .classes("or-shot cursor-pointer w-full")
                                                img.on("click", lambda x=x, title=title: zoom(x, title))

        def filter_topics(text: str | None) -> None:
            words = [w for w in (text or "").lower().split() if w]
            shown = 0
            for a in cards:
                ok = all(w in texts[a] for w in words)
                cards[a].set_visibility(ok)
                navs[a].set_visibility(ok)
                shown += ok
            found.text = f"{shown} of {len(cards)} topics" if words else ""
            nothing.text = f"No help topic mentions “{text.strip()}”." if words and not shown else ""
            nothing.set_visibility(bool(words and not shown))

        search.on_value_change(lambda e: filter_topics(e.value))
        filter_topics("")

        def go(target: str) -> None:
            if target.startswith("http"):
                ui.navigate.to(target, new_tab=True)
            elif target.startswith("settings:"):
                state["settings_tab"] = target.split(":", 1)[1]
                ui.navigate.to("/settings")
            else:
                ui.navigate.to(target)

        def zoom(shot: str, title: str) -> None:
            with ui.dialog() as d, ui.card().classes("or-card q-pa-sm").style("max-width: 96vw; width: 1400px"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(title).classes("or-h2")
                    ui.button(icon="close", on_click=d.close).props('flat round dense aria-label="Close"')
                ui.image(f"{STATIC_URL}/help/{shot}").props(f'alt="Screenshot: {title}" fit=contain').classes("w-full")
            d.open()

    ui.sub_pages({"/": build_view, "/history": history_view, "/compare": compare_view, "/terms": terms_view,
                  "/interoperability": interop_view,
                  "/issues": issues_view,
                  "/settings": settings_view,
                  "/about": about_view,
                  "/help": help_view}) \
        .classes("w-full")


DEFAULT_PORT = 8765


def port_free(host: str, port: int) -> bool:
    import socket

    fam = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(fam, socket.SOCK_STREAM) as sock:
        # the server binds with SO_REUSEADDR, so a port whose old connections are still closing
        # (TIME_WAIT) is usable; only a port another process is listening on counts as busy
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            sock.listen(1)
        except OSError:
            return False
    return True


def choose_port(host: str, wanted: int | None) -> int:
    """The port to serve on. An explicit port must be free; otherwise the first free port from 8765 up."""
    if wanted:
        if not port_free(host, wanted):
            raise SystemExit(f"Port {wanted} is already in use on {host}. Pick another with --port, "
                             f"or leave --port out to use the first free port from {DEFAULT_PORT}.")
        return wanted
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 50):
        if port_free(host, port):
            return port
    raise SystemExit(f"No free port between {DEFAULT_PORT} and {DEFAULT_PORT + 49}; pass one with --port.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ontoreview-ui", description="OntoReview local web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1, this machine only).")
    env_port = os.environ.get("ONTOREVIEW_UI_PORT")
    parser.add_argument("--port", type=int, default=int(env_port) if env_port and env_port.isdigit() else None,
                        help=f"Port to serve on (env ONTOREVIEW_UI_PORT). Default: the first free port from {DEFAULT_PORT}.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--native", action="store_true", help="Open in a desktop window (needs pywebview).")
    args = parser.parse_args(argv)
    try:
        from nicegui import app, ui
    except ImportError:
        msg = ("ontoreview-ui needs NiceGUI (Python 3.11+). Install it with:\n"
               '    pip install "ontoreview[ui]"')
        if sys.version_info < (3, 11):
            msg += f"\nThis Python is {sys.version.split()[0]}; NiceGUI 4 requires 3.11 or newer."
        print(msg, file=sys.stderr)
        raise SystemExit(1) from None
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("Warning: the UI can read and write files on this machine; binding to "
              f"{args.host} exposes that to your network.", file=sys.stderr)
    port = choose_port(args.host, args.port)
    if not args.port and port != DEFAULT_PORT:
        print(f"Port {DEFAULT_PORT} is busy; using {port}.", file=sys.stderr)
    register_upload_route(app)
    if telemetry.enabled():
        notice = telemetry.first_run_notice()
        if notice:
            print(notice, file=sys.stderr)
        telemetry.start_session()
        app.on_shutdown(telemetry.end_session)
    ui.run(build_page, host=args.host, port=port, title="OntoReview", reload=False,
           show=not args.no_browser, native=args.native, favicon=str(ASSETS / "favicon.svg"),
           show_welcome_message=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
