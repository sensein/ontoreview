# Quality checks in OntoReview

This page lists every quality check OntoReview runs, the order they run in, and how to configure them.

## When checks run

Checks run when you produce:

- a **Website** or a **Single HTML file** (the results appear in the "Quality report" section of the docs and in the app's Issues table),
- a **Quality check only** report in the app, or `ontoreview check` on the command line.

Markdown and MyST exports, and **Compare versions**, don't run quality checks.

## Order

1. **Parse and extract** the ontology. This is not a check itself; every rule works on its output.
2. **Built-in rules** OB001 → OB028, in ID order, then any rules added by plugins.
3. **ROBOT report**, using a local `robot` command or the `obolibrary/robot` Docker image.
4. **Logical consistency**, an OWL reasoner (HermiT by default, or ELK) run with `robot reason` through the same local `robot` or Docker image. It needs ROBOT, so it is skipped when ROBOT is off or unavailable.
5. **OOPS! pitfall scan**, the OOPS! web service. By default it runs only when ROBOT couldn't (no Docker, or ROBOT failed). Set it to "always" to run it as well, or "off" never to run it. **OOPS! uploads the ontology to oops.linkeddata.es.**
6. **Competency questions**, when a competency-questions file is given. Each SPARQL query runs against the ontology plus any example data.

Results are not shown in run order. Built-in findings are sorted by severity (errors, then warnings, then info), then by rule ID and term. ROBOT, logical-consistency and OOPS! results appear as their own sections of the quality report. In the app's Issues table, all of them are merged and sorted by severity.

## Built-in rules

### Ontology metadata

| ID | Severity | Rule | What it checks |
|---|---|---|---|
| OB001 | warning | Ontology has no title | `dcterms:title` (or `rdfs:label`) on the `owl:Ontology` node |
| OB002 | warning | Ontology has no description | `dcterms:description` or `dcterms:abstract` |
| OB003 | warning | No license declared | `dcterms:license` |
| OB004 | info | No version information | `owl:versionInfo` and `owl:versionIRI` |
| OB005 | warning | No creators | `dcterms:creator` |
| OB006 | info | No preferred prefix/namespace | `vann:preferredNamespacePrefix` and `vann:preferredNamespaceUri` |

### Documentation of terms

| ID | Severity | Rule | What it checks |
|---|---|---|---|
| OB010 | warning | Term without a label | every term has an `rdfs:label` or `skos:prefLabel` (OOPS! P08) |
| OB011 | warning | Term without a definition | every term has `skos:definition`, IAO:0000115 or `rdfs:comment` (OOPS! P08) |
| OB016 | warning | Duplicate labels | no two terms share a label |
| OB017 | warning | Multiple labels in one language | no term has two labels in the same language |
| OB026 | info | Missing language tags | if some labels have language tags, all of them do |
| OB018 | info | Deprecated term without replacement | deprecated terms point to a replacement with `dcterms:isReplacedBy` |

### Structure and logic

| ID | Severity | Rule | What it checks |
|---|---|---|---|
| OB014 | error | Cycle in class hierarchy | no class is (indirectly) a subclass of itself (OOPS! P06) |
| OB015 | error | Undeclared term | every term used in the ontology namespace is declared with `rdf:type` (OOPS! P34/P35) |
| OB020 | error | Class both subclass of and disjoint with another | no class is a *direct* asserted subclass of a class it is disjoint with |
| OB021 | error | Transitive property used as functional | no property is both transitive and (inverse) functional (not allowed in OWL 2 DL) |
| OB024 | error | Wrong kind of range | datatype properties have a datatype range; object properties have a class range |
| OB022 | warning | Self-referencing definition | no class is equivalent to, or a subclass of, itself (OOPS! P24/P27) |
| OB025 | warning | Inverse of itself but not symmetric | a property that is its own inverse is declared symmetric instead (OOPS! P25) |
| OB028 | warning | Multiple domains or ranges | properties don't have several `rdfs:domain`/`rdfs:range` axioms, which are read as their intersection (OOPS! P19) |
| OB012 | info | Property without domain | properties declare `rdfs:domain`; ignored when the property is used in class axioms (OOPS! P11) |
| OB013 | info | Property without range | properties declare `rdfs:range` (OOPS! P11) |
| OB023 | info | Orphan class | no class lacks superclasses, subclasses and any use |

### Style

| ID | Severity | Rule | What it checks |
|---|---|---|---|
| OB019 | info | Inconsistent naming convention | classes are UpperCamelCase and properties lowerCamelCase (OOPS! P22) |
| OB027 | info | Term outside the ontology namespace | lists declared terms in other namespaces (they are documented as external) |

## Competency questions

| ID | Severity | Rule | When it is reported |
|---|---|---|---|
| CQ001 | warning | Competency question not answerable | the question's SPARQL query returned no results |
| CQ002 | error | Competency question query error | the query could not be run, for example because of a syntax error |

Questions without a query are listed as "not tested" and are not reported as findings.

## External checkers

**ROBOT report** (<http://robot.obolibrary.org/report>) runs ROBOT's quality-control queries. These include missing or duplicate labels, missing definitions, references to deprecated terms and multiple labels. ROBOT grades each result as error, warning or info.

**Logical consistency** (<http://robot.obolibrary.org/reason>) runs an OWL reasoner over the ontology (including loaded imports). Nothing leaves your machine.

| Code | Severity | Reported when |
|---|---|---|
| `inconsistent_ontology` | error | the ontology has no model, for example an individual typed with two disjoint classes |
| `unsatisfiable_class` | error | a class can never have members, for example a subclass of two disjoint classes; the classes are listed |

When there are no problems, the section says "Consistent; all classes satisfiable (HermiT)". HermiT is complete for OWL 2 DL but can be slow on very large ontologies. ELK is much faster but only understands OWL 2 EL, so it can miss problems that depend on other constructs. The reasoner stops after `evaluation.reasoner_timeout` seconds (default 600). For an explanation of a problem, open the ontology in Protégé and use its explanation feature.

**OOPS!** (<https://oops.linkeddata.es>) reports pitfalls from its catalogue, such as P04, P08, P10, P11, P13 and P22. It grades them critical, important or minor, which OntoReview shows as error, warning and info.

If a checker can't run, the reason is shown in its section of the report (for example "ROBOT is not available" or "OOPS! request failed"). The build still finishes.

## Configuration

In `ontoreview.toml`:

```toml
[checks]
disable = ["OB019", "OB023"]            # turn rules off
severity = { OB023 = "warning" }         # change a rule's severity

[evaluation]
robot = "auto"     # "auto" (local robot, else Docker) | "on" (also report when unavailable) | "off"
oops = "auto"      # "auto" (only if ROBOT can't run) | "on" (always) | "off" (never upload)
reasoner = "hermit"  # logical consistency: "hermit" | "elk" (fast, OWL 2 EL only) | "off"
reasoner_timeout = 600
```

In the app, use **Settings › Quality checks** for ROBOT (Docker or a local `robot`), the reasoner (**Logical consistency** card), the OOPS! service and when a check run fails.

On the command line:

```bash
ontoreview check my-ontology.ttl --fail-on error          # exit 1 on any error (for CI)
ontoreview check my-ontology.ttl --format json -o quality.json
ontoreview check ontologies/                               # every ontology in a folder
ontoreview check my-ontology.ttl --reasoner elk            # faster consistency check (or off)
```

`--fail-on` accepts `error`, `warning`, `info` or `never`.

## What is not checked

- **Logical consistency without ROBOT.** The reasoner runs through ROBOT, so when ROBOT is off or neither Docker nor a local `robot` is available, consistency is not checked. The built-in rule OB020 still catches the simplest case, a direct subclass of a disjoint class.
- **Explanations.** The reasoner reports *that* the ontology is inconsistent or *which* classes are unsatisfiable, not which axioms cause it.
- **Inferred superclasses** (`--reason`, Settings › Documentation) use RDFS semantics through owlrl. They only add information to the documentation; they are not a check.

## Where the code lives

Checks and reports are kept apart. `ontoreview/quality_checks/` only evaluates the ontology; `ontoreview/report/` turns the results into something to read.

**`quality_checks/`: evaluation**

| Module | What it does |
|---|---|
| `__init__.py` | the rule framework (`Rule`, `rule`, `run_checks`) |
| `rules.py` | built-in rules OB001–OB028 |
| `robot.py` | finds ROBOT (local or Docker) and runs `robot report` |
| `logical_consistency.py` | runs the reasoner (`robot reason`) |
| `oops.py` | sends the ontology to the OOPS! web service |
| `evaluators.py` | runs ROBOT, the reasoner and OOPS! in order |

**`report/`: report generation**

| Module | What it does |
|---|---|
| `models.py` | result types (`Finding`, `Report`, `ExternalItem`, `ExternalReport`), severity order, and `TOOLS` (each external checker's name and URL) |
| `robot.py` | ROBOT report TSV → findings |
| `reasoner.py` | `robot reason` output → consistency findings |
| `oops.py` | OOPS! RDF/XML response → pitfall findings |
| `issues.py` | rows for the app's Issues table |
| `console.py` | `ontoreview check` terminal output |
| `html.py` | `ontoreview check --format html` page |

The quality section of the generated documentation is the theme template `themes/default/templates/sections/quality.html`. To add a new external checker, add a runner in `quality_checks/`, a parser in `report/` and an entry in `TOOLS`, then call the runner from `evaluators.py`.

Competency questions are in `ontoreview/cq.py`, because the documentation also uses them.
