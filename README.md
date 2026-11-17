# OntoReview

**Beautiful, self-contained documentation for OWL, RDFS, SKOS and LinkML models.**
A pure-Python alternative to [Widoco](https://github.com/dgarijo/Widoco). No Java, no web services, one command.

```bash
pip install "ontoreview[ui]"              # Python 3.11+
ontoreview ui                             # opens the app at http://127.0.0.1:8765
```

Pick an ontology (or a whole folder, or drag it in), choose **Website**, press **Build docs**. The app shows the quality issues found by the built-in checks, ROBOT and OOPS!, and keeps a history of your runs.

For scripts and CI, the same features are commands (see [Commands](#commands)):

```bash
ontoreview build my-ontology.ttl          # → docs/index.html
ontoreview check my-ontology.ttl --fail-on error
```

## Why OntoReview?

| | Widoco | OntoReview |
|---|---|---|
| Runtime | Java 8+ | Python ≥ 3.10 (`pip install`) |
| Inputs | OWL (RDF/XML, Turtle, …) | Any RDF syntax, **LinkML YAML**, SKOS |
| Opening `index.html` from disk | Broken unless `-uniteSections` | Works offline (`file://`) |
| Missing metadata | Placeholder prose you must edit | Auto-written intro + quality warnings |
| Search | — | Fuzzy search across all terms (⌘K or `/`) |
| Visualization | Separate WebVOWL page | Embedded VOWL-style graph or UML diagram (focus, filter, PNG export) |
| Quality checks | OOPS! web service | 25 offline rules, CI exit codes |
| Changelog | Bubastis-based | Built-in term and axiom diff (`ontoreview diff`) |
| License lookup | Licensius web service | Offline SPDX/CC table |
| Dark mode, mobile, print | — | ✓ |
| Theming | Custom CSS | Override any Jinja template, plus plugins |
| Exports | HTML | HTML, Markdown (MkDocs), MyST (Sphinx) |

## Features

- **Term documentation:** classes, object/datatype/annotation properties, individuals, datatypes and SKOS concepts. For each term it shows labels, definitions (Markdown supported), examples, notes, and superclasses and subclasses (asserted, plus inferred with `--reason`). Restrictions and equivalences are rendered in **Manchester syntax**. Properties get domain/range, characteristics, inverses and property chains. Every term also gets "used in" back-links, mappings and deprecation status.
- **Metadata** comes from standard annotations (dcterms, dc, schema.org, vann, PAV, FOAF, PROV, bibo). That covers title, abstract, authors with ORCID and affiliation, license, versions, DOI, citation and logo. Anything can be overridden in `ontoreview.toml`.
- **Generated sections:** introduction, metadata, overview with A–Z index, visualization, reference, namespaces, changelog, quality report, downloads, how to cite (text, BibTeX and `CITATION.cff`) and provenance (PROV-O).
- **Publishing:** Turtle, RDF/XML, JSON-LD and N-Triples serializations. Content-negotiation configs for Apache (`.htaccess`), nginx and w3id.org. schema.org JSON-LD for search engines. `.nojekyll` for GitHub Pages.
- **Multilingual:** `--lang en,es,pt` builds one site per language, each with a language switcher. Labels and definitions fall back between languages. UI strings exist for en, es, pt, fr, de, it and zh.
- **Single or multi-page** layouts.

## Competency questions

Competency questions can be written in YAML, JSON, CSV/TSV or Excel. Each question can have a SPARQL query, and OntoReview **runs every query** against the ontology, plus any example data you supply. The page then shows each question with its query, status (answerable, not answerable, query error, not tested) and first results. Each question links to the terms it uses, and each of those term entries links back to the question. A question that can't be answered becomes a quality finding, so `ontoreview check` catches it in CI.

```bash
ontoreview cq-template competency-questions.xlsx     # or .yaml / .csv / .tsv
ontoreview build ontology.ttl --cq competency-questions.xlsx
```

```yaml
example_data: [examples/data.ttl]
questions:
  - id: CQ1
    question: Which pizzas have a meat topping?
    sparql: SELECT ?pizza WHERE { ?pizza pizza:hasTopping/a pizza:MeatTopping }
    answer: Pepperoni
```

Spreadsheet column names are matched loosely: "CQ ID", "Competency question", "SPARQL query", "Expected answer" and "Related terms" are all recognised.

## A folder of ontologies

Give `build`, `export` or `check` a folder instead of a file to document every ontology in it:

```
ontoreview build ontologies/ -o docs
ontoreview export ontologies/ -o docs-md            # or --format myst
ontoreview check ontologies/ --fail-on error        # CI: checks every file, JSON keyed by file
```

Each ontology gets its own sub-folder in the output, mirroring the source folder, plus an index page that links them all:

```
ontologies/                 docs/
  core.ttl          ->        core/index.html
  bio/anatomy.owl   ->        bio/anatomy/index.html
  bio/cells.ttl     ->        bio/cells/index.html
                              index.html          (lists every ontology, with term counts and quality)
                              collection.json     (machine-readable manifest)
```

- Sub-folders are searched recursively. RDF files (`.ttl`, `.owl`, `.rdf`, `.jsonld`, `.nt`, `.n3`, `.trig`, `.nq`) and LinkML schemas are picked up. A `.json` file counts only if it's JSON-LD, and a `.yaml` file only if it's a LinkML schema, so competency-question files and other data are ignored. Hidden folders, `.venv`, `node_modules` and the output folder itself are skipped.
- If two files share a name (`core.ttl` and `core.owl`), the extension is kept in their folder names (`core-ttl/`, `core-owl/`).
- An `ontoreview.toml` inside a sub-folder applies to the ontologies in that sub-folder. Use it for per-ontology settings like `previous_version` or competency questions, which are ignored when given for the whole folder.
- One broken file doesn't stop the rest. It's listed on the index page and the command exits with status 1. OWL functional and Manchester syntax files (`.ofn`, `.omn`) are listed as skipped.
- `--single-file` writes one self-contained `index.html` per sub-folder.
- `source = "ontologies/"` in `ontoreview.toml` works too.

## External evaluators: OOPS! and ROBOT

- **ROBOT** (`robot report`) runs by default, on your machine, in Docker using the official `obolibrary/robot` image. You don't need Java or `robot.jar`. The first build pulls the image. A `robot` executable on your PATH, or one set with `evaluation.robot_path`, is used instead of Docker when present. Use `evaluation.robot_image` (or `ROBOT_DOCKER_IMAGE`) to pin a version tag, such as `obolibrary/robot:<version>`.
- **OOPS!** is the fallback. When ROBOT can't run (Docker isn't installed or running, or ROBOT fails), OntoReview calls the [OOPS! web service](https://oops.linkeddata.es/webservice.html) instead. **This sends your ontology to oops.linkeddata.es.** Set `evaluation.oops = "off"` (or pass `--no-oops`) to never upload it, or `"on"` (`--oops`) to run OOPS! alongside ROBOT.
- To skip external evaluators entirely, set `evaluation.robot = "off"`; OOPS! then runs only if `oops = "on"`.

Both tools' results go in the quality report next to OntoReview's own checks, with affected elements linked to their term entries.

## For LLMs and agents

Every build also writes Stripe-style machine-readable versions of the docs, which appear in their own "For LLMs and agents" section of the page:
- `llms.txt`, an index following [llmstxt.org](https://llmstxt.org)
- `llms-full.txt`, the whole document as one Markdown file
- a `.md` version of every page
- `ontology.json`, every term with its IRI, label, definition, hierarchy and domain/range

Turn this off with `llm = false`.

## The app (`ontoreview ui`)

If you'd rather not use the command line, use the local app built with [NiceGUI](https://nicegui.io/):

```
pip install "ontoreview[ui]"      # Python 3.11+
ontoreview ui                     # or: ontoreview-ui; opens http://127.0.0.1:8765
```

- **Build:** choose a file, a folder or a URL (or drag files and folders onto the page), pick the output (**Website** is recommended for publishing docs), and press **Build docs**. You'll see progress step by step, then the term count, errors and warnings, and a filterable list of issues from the built-in checks, ROBOT and OOPS!. **Open docs** and **Show in folder** take you to the result. The equivalent `ontoreview` command is under **Command line**, ready for CI.
- **Run history:** every run, searchable and filterable. Each can be opened, shown in its folder, re-run with the same settings or removed from the list.
- **Settings:** defaults for every build. *General* covers the output folder, default format and history. *Documentation* covers layout, languages, public URL, imports, reasoning, competency questions and previous version. *Quality checks* covers ROBOT (Docker or a local `robot`), the OOPS! service and when a check fails. *Appearance* covers the theme and compact layout. A project's `ontoreview.toml` overrides these.
- **About:** version, system info for bug reports, and links.
- The sidebar shows whether ROBOT (Docker) and the OOPS! service are available. **OOPS! uploads your ontology to oops.linkeddata.es.** By default it only runs when ROBOT can't, and you can turn it off in Settings.
- Settings, preferences and history are stored in `~/.config/ontoreview/` (set `ONTOREVIEW_UI_SETTINGS` to move them). Dropped files are copied to `~/.config/ontoreview/uploads/`.
- The app listens on `127.0.0.1` only. It uses the first free port from 8765, or `--port N` (or `ONTOREVIEW_UI_PORT`). `--no-browser` skips opening a tab. `--host` exposes it to your network, and anyone who can reach it could read and write files on your machine.

`ontoreview studio` is still available as the minimal open-a-file-and-preview tool.

## Studio and single-file export

```bash
ontoreview studio                 # open an ontology, preview it, then Export HTML
ontoreview build onto.ttl --single-file -o onto.html
```

The studio is a local page with a compact toolbar: open an ontology (or drop files, including multi-file LinkML schemas), preview the generated document, and export it as **one self-contained HTML file** with CSS, JS, data and serializations inlined.

## Look and layout (`[ui]`)

The default theme is a typeset, paper-like document: a white sheet with a quiet numbered table of contents. The Reference entries in the table of contents expand into class and property hierarchies. The figure uses WebVOWL-style notation by default: classes are circles sized by their number of subclasses, object properties are blue labelled boxes between domain and range, datatype properties are green boxes pointing at yellow literal boxes, inverse properties share one box, and subclass edges are dashed. Readers can switch it to a UML class diagram from the figure toolbar. Every part of this is configurable:

```toml
[ui]
term_index = "sidebar"        # "sidebar" | "section" (an Index of terms on the page) | "both" | "none"
sidebar_expanded = false
section_numbers = true
font = "serif"                # or "sans"
accent = "#174a8b"
width = "wide"                # or "normal"
graph_notation = "vowl"       # or "uml"
graph_layout = "auto"         # "force" | "hierarchy" | "concentric" (auto: force for VOWL, hierarchy for UML)
graph_property_edges = "auto" # true | false | auto (on for small ontologies)
section_order = ["introduction", "competency-questions", "reference", "graph"]

[evaluation]
robot = "auto"                # ROBOT via local robot or Docker; "on" | "off"
oops = "auto"                 # OOPS! web service only when ROBOT can't run; "on" | "off"
robot_image = "obolibrary/robot"
```

## LinkML

Point OntoReview at a LinkML schema; local `imports` are followed.

```bash
ontoreview build schema/personinfo.yaml
```

OntoReview converts the schema to OWL internally and documents it in OntoReview's own style, so checks, diff and serializations all work. The output is not a copy of `gen-doc`. LinkML maps to OWL as follows:

| LinkML | becomes |
|---|---|
| classes (`is_a`, `mixins`) | classes and superclasses |
| slots and attributes | object or datatype properties, depending on range |
| `required` / `multivalued` / `slot_usage` | cardinality restrictions such as `email exactly 1 xsd:string` |
| `pattern`, `minimum_value`, `maximum_value` | datatype facets such as `xsd:integer[>= 0, <= 999]` |
| enums | `{a, b, c}` classes whose permissible values are individuals (using `meaning` IRIs) |
| `class_uri`, `slot_uri`, mappings | real IRIs and `skos:*Match` |

## Commands

```bash
ontoreview build [SOURCE] [-o docs] [--layout multi] [--lang en,es] [--previous v1.ttl] [--reason]
ontoreview serve [SOURCE]                     # rebuilds on change, live reload
ontoreview check [SOURCE] [--fail-on warning] [--format console|json|html]
ontoreview diff OLD NEW [--format console|markdown|json]
ontoreview export [SOURCE] --format markdown|myst -o docs-md
ontoreview init [SOURCE] [--from-widoco config.properties]   # ontoreview.toml + GitHub Pages workflow
```

Python API:

```python
import ontoreview

result = ontoreview.build("ontology.ttl", out="docs", layout="multi", languages=["en", "es"])
print(result.report.summary)             # {'error': 0, 'warning': 3, 'info': 5}

onto, report = ontoreview.check("ontology.ttl")
log = ontoreview.compare_files("v1.ttl", "v2.ttl")
```

## Configuration (`ontoreview.toml`)

```toml
source = "ontology.ttl"
output = "docs"
layout = "single"
languages = ["en", "es"]
base_url = "https://w3id.org/my-ontology"
previous_version = "releases/1.0.0.ttl"   # enables the changelog
introduction = "docs/intro.md"
custom_css = "docs/custom.css"
theme = "theme/"                          # theme/templates/** overrides any template
definition_properties = ["ex:gloss"]      # extra annotation properties to treat as definitions
plugins = ["mypkg.ontoreview_plugin"]

[sections]
graph = true
quality = true

[checks]
disable = ["OB019"]
severity = { OB011 = "error" }

[metadata]
title = "My Ontology"
license = "https://creativecommons.org/licenses/by/4.0/"

[[metadata.creators]]
name = "Ada Lovelace"
iri = "https://orcid.org/0000-0000-0000-0000"

[[custom_sections]]
title = "Examples"
file = "docs/examples.md"
position = "after-terms"
```

## Plugins

A plugin is any module or object with some of these hooks:
- `sections(ontology, config)`
- `term_blocks(term, ontology)`
- `rules()`
- `template_dirs()`
- `postprocess(out_dir, ontology, config)`

Register plugins via the `ontoreview.plugins` entry point, or list them under `plugins` in the config.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
python scripts/build_examples.py && python -m http.server -d examples
```

Test fixtures include W3C PROV-O, FOAF, ORG, SKOS and DCAT 3.
