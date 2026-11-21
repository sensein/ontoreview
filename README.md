# OntoReview

**Documentation, quality review and interoperability scores for OWL, RDFS, SKOS and LinkML ontologies.**
Pure Python, no Java. One app or one command; the result is a self-contained website you can publish anywhere.

![Generated documentation: header and overview](guide/images/docs-overview.png)

## Quick start

```bash
pip install "ontoreview[ui]"          # Python 3.11+; add [cdi] for the interoperability language model
ontoreview ui                         # opens the app at http://127.0.0.1:8765
```

Choose an ontology (file, folder or URL, or drag it in), keep **Website**, press **Build docs**.

For scripts and CI:

```bash
ontoreview build my-ontology.ttl -o docs          # the website
ontoreview check my-ontology.ttl --fail-on error  # quality checks only, CI exit code
```

## Key features

- **Documentation website.** Every class, property, individual and SKOS concept with labels, definitions, axioms in Manchester syntax and back-links; an overview with statistics; an interactive diagram (VOWL or UML); search; downloads in Turtle, RDF/XML, JSON-LD and N-Triples; how to cite. Works offline, in dark mode, on phones and in print. Also as one `standalone.html`, Markdown or MyST.
- **Quality review.** 25 built-in rules plus ROBOT, a reasoner (HermiT/ELK), IRI checks, OntoCheck metrics and OOPS!, in one report with a summary per check.
- **Cross-domain interoperability (CDI).** How well the ontology aligns with ontologies from other domains, and how general its definitions are.
- **Scientific interoperability (SI).** In how many scientific fields (the 41 OECD fields of science) it is interoperable, ignoring upper-level ontologies.
- **Reference ontologies your way.** Upload files or SSSOM mappings, find and add ontologies on OLS or BioPortal by name, or let OntoReview discover them.
- **Provenance you can cite.** Each run records when it ran, the source file's SHA-256, and the exact release of every reference ontology it was checked against (once, with what used it), as JSON and PROV-O.
- **Compare versions.** Added, removed and changed terms and axioms, as an HTML report or a changelog in the docs.
- **Run history.** Every run with its configuration: re-run it as is, change it and run again, or export it as a .zip. Each run gets its own folder and is never overwritten.
- **Deploy in one click.** Every website includes `DEPLOY.md`, a Dockerfile, an nginx config and a GitHub Pages workflow. The app can push a website to GitHub and publish it on GitHub Pages.
- **Also:** LinkML schemas, folders of ontologies, multilingual sites, competency questions, files for LLMs and agents (`llms.txt`), themes and plugins.

## Screenshots

| | |
|---|---|
| ![The app after a build: results, Deploy, Export](src/ontoreview/ui_assets/help/results.png) | ![Interoperability page: CDI and SI](src/ontoreview/ui_assets/help/interop-results.png) |
| **Build** – results, quality metrics and issues | **Interoperability** – CDI and SI for one ontology |
| ![Generated docs: quality report](guide/images/docs-quality.png) | ![Generated docs: provenance timeline](guide/images/docs-provenance.png) |
| **Docs** – quality report with a summary per check | **Docs** – provenance with timestamps |
| ![Generated docs: diagram](guide/images/docs-graph.png) | ![Generated docs: scientific interoperability](guide/images/docs-si.png) |
| **Docs** – interactive diagram | **Docs** – scientific interoperability per domain |
| ![Run history: configuration, re-run and export](src/ontoreview/ui_assets/help/history-config.png) | ![Deploy to GitHub Pages](src/ontoreview/ui_assets/help/deploy.png) |
| **Run history** – re-run as is or changed, export | **Deploy** – push to GitHub Pages |
| ![Compare two versions](src/ontoreview/ui_assets/help/compare.png) | ![Settings: scientific interoperability](src/ontoreview/ui_assets/help/si-settings.png) |
| **Compare** – what changed between versions | **Settings** – references, domains, OLS/BioPortal search |

## Commands

| Command | What it does |
|---|---|
| `ontoreview ui` | The app (recommended) |
| `ontoreview build SOURCE -o docs` | Documentation website (`--single-file` for one HTML file) |
| `ontoreview check SOURCE` | Quality checks; `--interop-only` for CDI and SI only |
| `ontoreview diff OLD NEW` | Compare two versions |
| `ontoreview export SOURCE --format markdown` | Markdown or MyST pages |
| `ontoreview serve SOURCE` | Live preview while you edit |
| `ontoreview init SOURCE` | Create `ontoreview.toml` and a CI workflow |

`SOURCE` is a file, a URL or a folder of ontologies. Settings can live in `ontoreview.toml` next to the
ontology, so the app, the command line and CI build exactly the same docs.

## Learn more

- **[Guide](guide/GUIDE.md):** every feature, option, check and configuration key.
- **In the app:** Help (searchable, with screenshots).
- **Examples:** `python scripts/build_examples.py && python -m http.server -d examples`.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

MIT License.
