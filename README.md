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

## External evaluators: ROBOT, reasoner, IRI checks, OntoCheck and OOPS!

For the full list of quality checks, their order and how to configure them, see [quality_check.md](quality_check.md).

- **ROBOT** (`robot report`) runs by default, on your machine, in Docker using the official `obolibrary/robot` image. You don't need Java or `robot.jar`. The first build pulls the image. A `robot` executable on your PATH, or one set with `evaluation.robot_path`, is used instead of Docker when present. Use `evaluation.robot_image` (or `ROBOT_DOCKER_IMAGE`) to pin a version tag, such as `obolibrary/robot:<version>`.
- **Logical consistency** runs an OWL reasoner (HermiT by default, or ELK) through the same ROBOT set-up (`robot reason`). It reports an inconsistent ontology and unsatisfiable classes as errors. Set `evaluation.reasoner = "elk"` for speed on large ontologies, or `"off"` (`--reasoner off`) to skip it.
- **IRI checks** cover IRI syntax, the ontology header and version IRI, whether the ontology IRI resolves, and whether reused external classes and properties exist in their vocabulary, with the right type and not deprecated. Lookups go to a bundled SQLite database of 10 W3C vocabularies first, then your cache, OLS, BioPortal and a direct download. IRI syntax follows the full RFC 3987 grammar. Every result records the vocabulary release it was verified against, cached entries expire after `iri_cache_days` (30), and every run is recorded. Browse, search and extend the database on the app's **Term database** page or with `ontoreview terms`. Use `--offline` for SQLite only, or turn the checks off with `evaluation.iri_checks = "off"` or `--no-iri`.
- **OntoCheck** ([docs](https://ontocheck.readthedocs.io)) adds a scorecard of 17 metrics in four groups: labeling (labels, alternative labels, definitions), structural (isolated elements, class connections, domains and ranges, leaf classes, links to BFO/CCO), accessibility (SPARQL endpoint, RDF dump, human-readable license, external links) and naming conventions (capitalisation, spaces, spelling, duplicate labels, class search). It runs in-process. Only the endpoint and dump checks use the network (`evaluation.ontocheck_network`). Turn it off with `evaluation.ontocheck = "off"` or `--no-ontocheck`.
- **OOPS!** runs alongside ROBOT, because it checks modelling (unconnected elements, missing domains, ranges, inverses and disjointness, naming) where ROBOT checks annotations. When the ROBOT report ran, OOPS! leaves out the three pitfalls ROBOT already covers (P08, P32, P41) and says so in the review. Without ROBOT it runs the full catalogue. It calls the [OOPS! web service](https://oops.linkeddata.es/webservice.html), so **it sends your ontology to oops.linkeddata.es.** Set `evaluation.oops = "off"` (or pass `--no-oops`) to keep it local, or `"on"` (`--oops`) for the full catalogue every time. See [quality_check.md](quality_check.md).
- **Cross-domain interoperability** (on by default; turn off with `evaluation.cdi = "off"` or `--no-cdi`) scores whether the ontology can serve beyond its own domain. *Align* is the mean strength of each entity's best correspondence into reference ontologies from other domains (direct, lexical, or inherited through superclasses). *Gen* is how domain-neutral the class definitions are, rated by a zero-shot language model. *CDI* is their weighted harmonic mean. See [Cross-domain interoperability](#cross-domain-interoperability).
- To skip external evaluators entirely, set both `evaluation.robot = "off"` and `evaluation.oops = "off"`. With ROBOT off, OOPS! runs its full catalogue unless it is off too.

Both tools' results go in the quality report next to OntoReview's own checks, with affected elements linked to their term entries.

## Cross-domain interoperability

An ontology is cross-domain interoperable when it aligns with ontologies from other domains **and** defines its classes in general, domain-neutral terms. OntoReview scores both and combines them:

- **Align** is, for each class and property, the strength of its best correspondence into a reference ontology (`confidence × relation weight × 0.8^steps`, counted from τ = 0.5), averaged over all entities. Correspondences come from shared IRIs, `owl:equivalentClass`/`rdfs:subClassOf` axioms, SSSOM mappings, exact label and synonym matches, and superclasses (up to 3 steps). OntoAligner can add automatic matches for file references.
- **Gen** is, for each class, 1 minus the expected specificity of its definition on a five-level scale (from "broad, abstract statement" to "highly specific, measurable details"), rated by a zero-shot NLI model (`facebook/bart-large-mnli`). Classes without a definition count as 0.
- **CDI** = (1+β²)·Align·Gen / (Align + β²·Gen). With β = 1 both weigh the same, and CDI ≥ θ = 0.5 counts as interoperable.

Reference ontologies can be mixed:

```bash
ontoreview check my.ttl --cdi ols --cdi-domain agriculture       # discover: top 10 OLS ontologies by coverage, own domain left out
ontoreview check my.ttl --cdi ols:envo,chebi --cdi bioportal:NCIT  # named repository ontologies
ontoreview check my.ttl --cdi ref1.owl --cdi https://example.org/ref2.ttl --cdi maps.sssom.tsv
ontoreview check my.ttl --cdi "ols@https://service.tib.eu/ts4tib/api" --cdi "ontoportal:AGROVOC@https://data.agroportal.lirmm.fr"
```

It runs by default, like every other check (`--no-cdi` or `evaluation.cdi = "off"` to skip it); with no references given it discovers them on OLS. In the app it is under **Settings → Quality checks → Cross-domain interoperability**. List one reference per line, or drop several reference ontologies or SSSOM files at once. API keys are optional. OLS needs none. OntoPortal services (BioPortal, AgroPortal, …) answer only with a key, and your own key avoids shared rate limits; without one, those references are skipped and the review says so. Enter keys in Settings, pass `--cdi-api-key bioportal=KEY` (or `ontoportal=KEY` for any other OntoPortal service), or set `BIOPORTAL_API_KEY` / `ONTOPORTAL_API_KEY`. Keys are never written to reports, `ontoreview.toml`, the run history or the command line shown in the app. Repositories receive the ontology's labels, synonyms and IRIs, never the file. `--offline` skips repositories and URLs.

**Term database.** CDI uses the term database first (the bundled W3C vocabularies plus your cache; see IRI checks). Every stored vocabulary is matched offline as a reference. Details of OLS and BioPortal ontologies (title, domain, version IRI, version, load or release date) are read from the database before the service is asked, and saved once fetched, for `iri_cache_days` (30). Reference ontologies you provide (files, uploads, URLs) are indexed into the database, so it grows and later runs find them without being told. Each run is recorded there (Term database › Runs) with its settings, scores, every correspondence and the release of each reference ontology. Not every ontology states a version IRI or version, and not every repository reports a load date. A release is then identified by what is available (release date, the file's SHA-256, or a SHA-256 fingerprint of the repository's answer), marked "version not reported", and never dropped. The same release list appears in the docs' quality section, `cdi.json` and `provenance.ttl` (`prov:used`). Set `evaluation.cdi_term_db = false` to skip the database.

Gen needs a language model: `pip install "ontoreview[cdi]"` (transformers, torch and OntoAligner; Python 3.10–3.13 for OntoAligner). The same extra enables OntoAligner for file and URL references: `--cdi-ontoaligner fuzzy` (string similarity) or `sbert` (sentence embeddings), or the matcher choice in Settings. The model, about 1.6 GB, is downloaded on first use and runs locally. Without it, only Align is scored and the report says why. The review shows the scores, Align per reference ontology, entities without any correspondence, and classes with very specific definitions. The docs folder gets a `cdi.json` with every correspondence. Parameters (`cdi_tau`, `cdi_c_lex`, `cdi_rho_sub`, `cdi_gamma`, `cdi_k_max`, `cdi_top_n`, `cdi_beta`, `cdi_theta`, `cdi_model`, `cdi_ontoaligner`, …) go under `[evaluation]`:

```toml
[evaluation]
cdi = "on"
cdi_references = ["ols", "ols:envo,chebi", "refs/upper.owl", "refs/maps.sssom.tsv"]
cdi_domains = ["agriculture"]
```

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
- **Compare:** drop or choose a previous and a current version of an ontology (files or URLs). The comparison runs as soon as both are there. It shows added, removed and modified terms with the exact statements that changed, and writes a standalone HTML report (open it or download it) plus `changes.md` and `changes.json`. This is the same as `ontoreview diff OLD NEW --format html|markdown|json`. On Build, **Compare versions** is a shortcut for the ontology you're documenting. To put a changelog inside the website instead, set **Previous version** in Settings › Documentation.
- **Run history:** every run, searchable and filterable. Each can be opened, shown in its folder, re-run with the same settings or removed from the list.
- **Settings:** defaults for every build. *General* covers the output folder, default format and history. *Documentation* covers layout, languages, public URL, imports, reasoning, competency questions and previous version. *Quality checks* covers ROBOT (Docker or a local `robot`), the OOPS! service and when a check fails. *Appearance* covers the theme and compact layout. A project's `ontoreview.toml` overrides these.
- **Project config:** the **Project config** menu on Build creates `ontoreview.toml` from a commented template, or opens the existing file in an editor that checks it before saving. It can also save what you selected, or load another config. The file keeps your settings with the ontology, so the command line, CI and teammates build the same docs.
- **About:** version, system info for bug reports, and links. **Help:** step-by-step instructions with screenshots (regenerate them with `uv run --extra ui --with playwright python scripts/ui_screenshots.py`).
- Found a bug or have an idea? Use **About › Report an issue**, which offers bug report, feature request and suggestion forms.
- The sidebar shows whether ROBOT (Docker) and the OOPS! service are available. **OOPS! uploads your ontology to oops.linkeddata.es.** It runs alongside ROBOT by default; turn it off in Settings for private ontologies.
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
oops = "auto"                 # OOPS! alongside ROBOT (skips what ROBOT covers); "on" = full catalogue | "off"
reasoner = "hermit"           # logical consistency via ROBOT; "elk" | "off"
ontocheck = "on"              # OntoCheck metrics (labeling, structural, accessibility, naming); "off"
iri_checks = "on"             # IRI syntax, header, resolution, external terms; iri_network = false for offline
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
ontoreview ui [--port N] [--no-browser]       # the app (recommended); same as ontoreview-ui

# Advanced / CI. SOURCE is a file, a URL or a folder of ontologies
ontoreview build [SOURCE] [-o docs] [--layout multi] [--lang en,es] [--previous v1.ttl] [--reason]
                 [--base-url URL] [--cq cq.yaml] [--single-file] [--robot auto|on|off] [--reasoner hermit|elk|off]
                 [--ontocheck/--no-ontocheck] [--iri/--no-iri] [--offline]
                 [--oops/--no-oops] [--open]
ontoreview serve [SOURCE] [--port 8000]       # rebuilds on change, live reload
ontoreview check [SOURCE] [--fail-on warning] [--format console|json|html] [-o report] [--reasoner hermit|elk|off] [--no-ontocheck] [--no-iri] [--offline]
ontoreview diff OLD NEW [--format console|markdown|json|html] [-o changes.html]
ontoreview export [SOURCE] --format markdown|myst -o docs-md
ontoreview init [SOURCE] [--from-widoco config.properties]   # ontoreview.toml + GitHub Pages workflow
ontoreview cq-template competency-questions.xlsx             # or .yaml / .csv / .tsv
ontoreview terms list | search TEXT | add URL-OR-FILE | refresh KEY | runs  # the IRI term database
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
