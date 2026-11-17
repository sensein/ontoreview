# OntoReview

**Beautiful, self-contained documentation for OWL, RDFS, SKOS and LinkML models.**
A pure-Python alternative to [Widoco](https://github.com/dgarijo/Widoco). No Java, no web services, one command.

```bash
pip install ontoreview
ontoreview build my-ontology.ttl          # → docs/index.html
ontoreview serve my-ontology.ttl          # live-reload preview
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

## External evaluators: OOPS! and ROBOT

- **ROBOT** (`robot report`) runs on your machine in Docker, using the official `obolibrary/robot` image, so you don't need Java or `robot.jar`. With the default `robot = "auto"` it runs when the image has already been pulled (`docker pull obolibrary/robot`). `robot = "on"` or `--robot on` pulls the image if needed. A `robot` executable on your PATH, or set with `evaluation.robot_path`, is used instead of Docker when present. Use `evaluation.robot_image` (or `ROBOT_DOCKER_IMAGE`) to pin a version tag, such as `obolibrary/robot:<version>`.
- **OOPS!** sends the ontology to https://oops.linkeddata.es, so it runs only when you turn it on with `--oops` or `evaluation.oops = true`.

Both tools' results go in the quality report next to OntoReview's own checks, with affected elements linked to their term entries.

## For LLMs and agents

Every build also writes Stripe-style machine-readable versions of the docs, which appear in their own "For LLMs and agents" section of the page:
- `llms.txt`, an index following [llmstxt.org](https://llmstxt.org)
- `llms-full.txt`, the whole document as one Markdown file
- a `.md` version of every page
- `ontology.json`, every term with its IRI, label, definition, hierarchy and domain/range

Turn this off with `llm = false`.

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
oops = false
robot = "auto"                # "on" (pulls the Docker image if needed) | "off"
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
