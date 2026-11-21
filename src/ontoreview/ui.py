"""``ontoreview-ui``: a local web UI (NiceGUI) to configure and run builds, exports and checks.

    pip install "ontoreview[ui]"
    ontoreview-ui                     # opens http://127.0.0.1:8765 in your browser

Runs on this machine only (bound to 127.0.0.1 by default); paths are local paths.
Pages: Build, Run history, Settings, About; a sidebar shows whether ROBOT and OOPS! are available.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
import time
import uuid
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__
from .ui_core import (
    DOCS_TASKS,
    MAX_UPLOAD_BYTES,
    TASKS,
    Prefs,
    Settings,
    browse,
    change_counts,
    clear_history,
    describe_source,
    existing_output,
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
LOGO_SVG = """<svg width="{s}" height="{s}" viewBox="0 0 30 30" aria-hidden="true"><rect width="30" height="30" rx="8" fill="#2F4FD8"/>
<circle cx="10" cy="10" r="3" fill="#fff"/><circle cx="20" cy="15" r="3" fill="#fff"/><circle cx="10" cy="21" r="3" fill="#fff"/>
<path d="M12.6 11.3 17.4 13.7M12.6 19.7 17.4 16.3" stroke="#fff" stroke-width="1.6"/></svg>"""

NAV = [  # key, path, label, svg path data
    ("build", "/", "Build", '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 13 9 5 9-5"/>'),
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
        "cross-domain interoperability, OOPS!, render.",
        "When it finishes, the tiles show how many terms were documented and how many errors and warnings were found.",
        "<b>Quality metrics</b> is a scorecard: OntoCheck's labeling, structure, accessibility and naming metrics, "
        "and the cross-domain interoperability scores (CDI, Align, Gen, and Align per reference ontology). Hover a "
        "metric to see what it measures.",
        "<b>Issues</b> lists every problem: filter by errors or warnings. ROBOT, reasoner, OntoCheck and OOPS! findings are merged with "
        "OntoReview's own checks; <b>Affected</b> names the term, or how many elements share the problem.",
        "<b>Logical consistency</b> errors come from an OWL reasoner (HermiT by default): an inconsistent ontology, "
        "or classes that can never have members. Use Protégé's explanations to find the axioms responsible.",
        "<b>Open docs</b> opens the website in a new tab; <b>Show in folder</b> opens it in Finder / Explorer.",
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
    ("history", "Run history", "history.png", [
        "Every build and check is listed with its status, issues and time.",
        "Search by ontology or output path, filter documentation vs. checks, and hide runs whose output was deleted.",
        "Use the row buttons to open the output, show it in its folder, load its settings to run again, or remove it "
        "from the list (files are kept).",
    ], "", [("Open Run history", "/history")]),
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
]


def _icon(paths: str, size: int = 18) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths}</svg>')


CSS = """
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
        self.cmp: dict = {"old": "", "new": "", "output": "", "last": None, "running": False, "filter": "all",
                          "done": None}
        self.verbose = False

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
        with ui.row().classes("items-center gap-3 no-wrap").style("padding: 0 10px 26px"):
            ui.html(LOGO_SVG.format(s=30), sanitize=False)
            with ui.column().classes("gap-0"):
                ui.label("OntoReview").style("font-weight:700;font-size:16px;color:#fff;letter-spacing:-.2px")
                ui.label("Docs & quality review").style("font-size:11px;color:var(--or-side-muted)")
        with ui.element("nav").props('aria-label="Main"').classes("column gap-1 w-full"):
            for key, path, label, icon in NAV:
                with ui.link(target=path).classes("or-nav") as link:
                    ui.html(_icon(icon), sanitize=False)
                    ui.label(label)
                    if key in ("build", "compare"):
                        nav_busy[key] = ui.spinner(size="14px").classes("q-ml-auto").tooltip("Running")
                        nav_busy[key].set_visibility(False)
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

    ui.timer(0.5, show_busy)

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
                            .props('flat round dense aria-label="Clear source"')
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
            render_source()
            render_formats()
            describe_later()
            output.props(f'placeholder="{s.default_output()}"')
            per_run = s.separate_runs and s.task in DOCS_TASKS
            op = s.output_path().resolve()
            out_txt = (op.parent / f"{op.stem if op.suffix.lower() == '.html' else op.name}-<date>-<time>"
                       / (op.name if op.suffix.lower() == ".html" else ""))
            output_info.text = (f"Writes to: {out_txt}  (a new folder each run)"
                                if per_run else
                                f"Writes to: {s.output_path().resolve()}" + ("" if s.output.strip() else "  (default)"))
            separate_cb.set_visibility(s.task in DOCS_TASKS)
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
                            ui.button("Open report (JSON)", on_click=lambda: open_result(str(res.output))) \
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

        async def start() -> None:
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
                     "exists": e.exists} for e in shown]
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
                <div class="or-hint or-mono">→ {{ props.row.out }}</div></q-td>''')
            tbl.add_slot("body-cell-act", r'''<q-td :props="props" class="text-no-wrap">
                <q-btn flat round dense size="sm" icon="tune"
                  aria-label="View configuration" @click.stop="() => $parent.$emit('details', props.row)"><q-tooltip>View configuration, edit and re-run</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="open_in_new" :disable="!props.row.index || !props.row.exists"
                  aria-label="Open output" @click.stop="() => $parent.$emit('open', props.row)"><q-tooltip>Open output</q-tooltip></q-btn>
                <q-btn flat round dense size="sm" icon="download" :disable="!props.row.exists"
                  aria-label="Export output" @click.stop="() => $parent.$emit('export', props.row)"><q-tooltip>Export output (folders as .zip)</q-tooltip></q-btn>
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
                t_look = ui.tab("Appearance")

        def row(label: str, hint: str = ""):
            r = ui.row().classes("w-full items-center gap-4 q-py-md no-wrap max-sm:flex-wrap or-setrow") \
                .style("border-bottom: 1px solid var(--or-line-2)")
            with r:
                with ui.column().classes("gap-0").style("flex: 1 1 320px"):
                    ui.label(label).classes("or-label")
                    if hint:
                        ui.label(hint).classes("or-hint")
            return r

        with ui.element("div").classes("or-body").style("padding-top: 16px"):
            start_tab = {"general": t_general, "docs": t_docs, "checks": t_checks, "look": t_look} \
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
                with ui.tab_panel(t_look).classes("q-pa-none").style("max-width: 900px"):
                    with ui.card().classes("or-card w-full").props("flat"):
                        with ui.column().classes("or-sec gap-3"):
                            ui.label("Theme").classes("or-h2")
                            theme_box = ui.element("div").props('role="radiogroup" aria-label="Theme"') \
                                .classes("w-full gap-0").style("display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px")
                            ui.checkbox("Compact layout").bind_value(work, "compact")
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
                ui.html(LOGO_SVG.format(s=72), sanitize=False)
                with ui.column().classes("gap-1").style("flex: 1 1 320px"):
                    ui.label("OntoReview").style("font-size:28px;font-weight:700;letter-spacing:-.6px")
                    ui.label("Turn ontology files into documentation and review their quality with ROBOT and "
                             "OOPS! — from one window or the command line.").style(
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
                data = json.loads(Path(res.output).read_text("utf-8"))
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
                                          on_click=lambda: open_result(str(res.output))).props("unelevated no-caps")
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
        page_head("Help", "How to build, read, publish and configure your ontology documentation.")
        with ui.element("div").classes("or-body"):
            with ui.row().classes("w-full gap-6 items-start no-wrap max-lg:flex-wrap"):
                with ui.element("nav").props('aria-label="Help topics"').classes("column gap-1 flex-none lg:sticky") \
                        .style("top: 16px; width: 230px"):
                    ui.label("On this page").classes("or-hint text-uppercase q-mb-xs").style("letter-spacing:.6px")
                    for anchor, title, *_ in HELP:
                        ui.link(title, f"#{anchor}").classes("or-hint").style("color: var(--or-ink-2)")
                with ui.column().classes("gap-4 grow min-w-0"):
                    for n, (anchor, title, shot, steps, note, links) in enumerate(HELP, 1):
                        with ui.card().classes("or-card w-full").props(f'flat id="{anchor}"'):
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
    ui.run(build_page, host=args.host, port=port, title="OntoReview", reload=False,
           show=not args.no_browser, native=args.native, favicon=str(ASSETS / "favicon.svg"),
           show_welcome_message=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
