# Fixing quality findings: what can be automated, and how

Status: plan only. Nothing here is implemented. Written 2026-11-21; updated the same day after review (decisions in section 9, LLM providers in section 7, items still to verify in section 12).

**No LayaLink.** Candidates (mappings, successors, parents, duplicates) are ranked with **OntoAligner**, which is already a dependency through the CDI check. [fix-ideation.md](fix-ideation.md) recommends LayaLink; that recommendation is superseded. Its notes on small Ollama models still apply.

## 1. The rule

OntoReview never changes anything on its own.

- **Every fix is a suggestion.** The user reviews each one and accepts or rejects it.
- **Check first, then suggest.** A fix is tested on a copy *before* it is shown. Fixes that would create new problems are dropped or marked. After the user accepts fixes, validation runs again on the written file.
- **The source ontology is never overwritten.** Accepted changes go to a *new* ontology file, plus a patch (section 9).
- **The generated docs are never edited.** They only ever reflect the ontology and `ontoreview.toml`. Suggestions don't appear in the docs, and the docs change only when the user rebuilds from the new version.
- **The same applies to the user's own LLM.** Its suggestions go through the same review and are never applied automatically.

## 2. Categories

| Category | Meaning | Who decides |
|---|---|---|
| **D: deterministic** | An exact edit computed by rules, with no model. Some offer two or three exact options. | The user accepts it. |
| **A: aligner** | Candidates ranked by OntoAligner (no LLM): mappings, successors, parents, likely duplicates. An LLM, if configured, only writes the explanation. | The user picks a candidate or rejects all. |
| **U: user input** | The fix needs a value only the user knows (license, creators), or the user must confirm a guess. | The user fills in or confirms a value. |
| **L: LLM** | The fix needs new text: definitions, descriptions, distinguishing labels. | The LLM drafts; the user accepts, edits or rejects. |
| **M: manual** | A modelling decision. No edit is proposed; the tool shows the evidence, and an LLM may explain likely causes. | The ontology author. |

**Flags on each fixer:**
- **safe:** exactly one option, no guessing, not breaking, no change in meaning. Only safe fixes can be accepted in bulk.
- **guess:** the fix rests on a heuristic, such as string similarity or a dominant language. It is never bulk-accepted, and the user confirms it.
- **breaking:** the fix renames an IRI. Renames are opt-in, and only in the **deprecate-and-replace** form: the old IRI stays, marked `owl:deprecated true` with `dcterms:isReplacedBy` pointing to the new IRI, so old links keep working. Fixing the label is the default.

## 3. Classification of every finding

### 3.1 Built-in rules (`src/ontoreview/quality_checks/rules.py`)

| Rule | Finding | Cat. | Suggested fix | Flags |
|---|---|---|---|---|
| OB001 | No title | U (L can draft) | Add `dcterms:title` | |
| OB002 | No description | L | Draft `dcterms:description` / abstract from the ontology's terms | |
| OB003 | No license | U | Add `dcterms:license`, chosen from the SPDX/CC list in `model/licenses.py` | |
| OB004 | No version info | U + D | User gives `owl:versionInfo`. `owl:versionIRI` is derived from a pattern the user can configure and confirms: default `<ontology IRI>/<version>/`, with an OBO-style `<base>/releases/<date>/<file>` option | |
| OB005 | No creators | U | Add `dcterms:creator` (name, ORCID) | |
| OB006 | No preferred prefix | D | Add `vann:preferredNamespacePrefix` / `Uri` from the prefix bound to the namespace | safe |
| OB010 | Term without label | D, else U/L | Label from a *readable* local name (split camelCase/snake_case). Opaque IDs such as `CL_0000540` are detected and fall back to the user or the LLM | safe only for readable names |
| OB011 | Term without definition | L | Definition in "genus–differentia" form ("An X that …") from the label, parents, siblings and external matches | |
| OB012 | Property without domain | L (D seed) | Seed: classes the property is used on in restrictions; the LLM proposes the rest | |
| OB013 | Property without range | L (D seed) | Seed: fillers of `someValuesFrom` / `allValuesFrom`; the LLM proposes the rest | |
| OB014 | Subclass cycle | D (choice) for 2 classes; M for longer | Two classes: remove one axiom (the narrower term stays under the broader) or declare them equivalent, ranked (section 10). Longer cycles: show the path | |
| OB015 | Undeclared term | D (choice) / A | Declare `rdf:type` from where it's used. For properties this is a choice (object or datatype), since usage can be ambiguous. Or suggest the declared IRI it most resembles, as a likely typo | guess |
| OB016 | Duplicate labels | L (or U) | Propose distinguishing labels for each term | |
| OB017 | Several labels in one language | U | User picks which label stays `rdfs:label`; the others become `skos:altLabel` | |
| OB018 | Deprecated without replacement | A (+ L explanation) | OntoAligner ranks the ontology's own terms as successors; add `dcterms:isReplacedBy` / `IAO:0100001` | |
| OB019 | Naming convention | D | Default: fix the label. Opt-in: rename the IRI (deprecate-and-replace) | breaking (rename) |
| OB020 | Subclass of and disjoint with | M | Show both axioms; the author removes one | |
| OB021 | Transitive and functional | M | Explain the conflict; the author removes one characteristic | |
| OB022 | Self-reference | D | Remove `X subClassOf X` / `X equivalentClass X` / `P subPropertyOf P` | safe |
| OB023 | Orphan class | A (+ L explanation) | OntoAligner ranks existing classes as parents | |
| OB024 | Wrong kind of range | D (choice) | Option A: change the range. Option B: switch the property type (Datatype ↔ Object). Option B affects every assertion using the property, so it is ranked second | close to breaking (option B) |
| OB025 | Inverse of itself, not symmetric | D (choice) | Ranked first: add `owl:SymmetricProperty`. In OWL, `P owl:inverseOf P` already implies symmetry, so this only makes it explicit and **changes nothing logically**. Second: remove `owl:inverseOf`, which **changes the meaning** | |
| OB026 | Missing language tags | U (D proposes) | Proposes the dominant language tag; the user confirms, because the untagged label may be in another language | guess |
| OB027 | Term outside the namespace | M | Informational; nothing to edit | |
| OB028 | Multiple domains / ranges | D (choice) | Rewrite as `owl:unionOf`, warning that this changes the meaning (intersection → union); or keep as is | |

(OB007–OB009 don't exist.)

### 3.2 Competency questions (`src/ontoreview/build.py:37`, `src/ontoreview/cq.py`)

| Code | Finding | Cat. | Suggested fix |
|---|---|---|---|
| CQ001 | Question not answerable | L | Suggest missing terms or axioms, or an adjusted SPARQL query |
| CQ002 | SPARQL query error | L | Fix the query. This edits the CQ file, not the ontology |

### 3.3 ROBOT report (`src/ontoreview/report/robot.py`)

ROBOT's rule names come from its report profile; the code has no fixed list. The rules below are ROBOT's default profile, taken from ROBOT's documentation, so verify them against a real report.

| ROBOT rule | Cat. | Suggested fix | Flags |
|---|---|---|---|
| missing_label | D, else U/L | As OB010 | as OB010 |
| missing_definition | L | As OB011 | |
| duplicate_label | L | As OB016 | |
| multiple_labels | U | As OB017 | |
| label_whitespace, annotation_whitespace | D | Trim and collapse whitespace (needs the offending value: see gaps) | safe |
| label_formatting | D | Remove the illegal characters reported | |
| lowercase_definition | D | Capitalise the first letter | safe |
| duplicate_definition, multiple_definitions | U | User picks or merges | |
| duplicate_exact_synonym, duplicate_scoped_synonym, duplicate_label_synonym | D | Remove the duplicate triple | safe |
| missing_ontology_title / description / license | U / L / U | As OB001 / OB002 / OB003 | |
| deprecated_class_reference, deprecated_property_reference | D if a replacement is recorded, else A | Replace the reference with the successor term | |
| missing_obsolete_label, misused_obsolete_label | D | Add or remove the "obsolete " label prefix | safe |
| misused_replaced_by | D | Remove `replaced_by` from the non-deprecated term | safe |
| missing_superclass | A (+ L explanation) | As OB023 | |
| equivalent_pair, multiple_equivalent_classes | M | Show them; the author decides | |
| invalid_xref | D, else U | Reformat to `PREFIX:ID` when unambiguous | |

### 3.4 Logical consistency (`src/ontoreview/report/reasoner.py`)

| Code | Cat. | Suggested fix |
|---|---|---|
| inconsistent_ontology | M | No edit. An LLM may explain likely causes once reasoner explanations are available (see gaps) |
| unsatisfiable_class | M | Same |
| outside_owl2_dl | M | Show ROBOT's message; the author removes the non-DL construct |

### 3.5 IRI checks (`src/ontoreview/report/iri.py`, `src/ontoreview/quality_checks/iri/`)

| Code | Cat. | Suggested fix | Flags |
|---|---|---|---|
| invalid_iri (own term) | D | Percent-encode or rename (deprecate-and-replace) | breaking |
| invalid_iri (external reference) | D / A | Percent-encode, or match against known terms in the term database | |
| no_ontology_header | D | Add an `owl:Ontology` named by the namespace (without the trailing `#`/`/`) | |
| multiple_ontology_headers | U | User picks the one to keep | |
| version_iri_equals_ontology_iri | U + D | Propose a versionIRI from the configured pattern (as OB004) | |
| ontology_iri_not_resolvable | M | A publishing issue, not an ontology edit. Point to the generated `.htaccess` / w3id files | |
| stale_term_lookup | action | "Refresh" the vocabulary; no ontology edit | |
| release_mismatch | D | Point `owl:imports` at the verified release, or refresh | |
| deprecated_external_term | D if OLS gives a replacement, else A | Replace references with `term_replaced_by`; else OntoAligner ranks OLS candidates | |
| external_term_wrong_type | A (+ L explanation) | OntoAligner ranks OLS candidates of the expected type, or "none" | |
| unverified_external_term | A (or U) | As above; or the user adds the vocabulary to the term database | |

### 3.6 OntoCheck (`src/ontoreview/report/ontocheck.py`)

| Code | Cat. | Suggested fix | Flags |
|---|---|---|---|
| checkLabel | D, else U/L | As OB010 | as OB010 |
| definitionCheck | L | As OB011 (OntoCheck only looks at `skos:definition`) | |
| isolatedElements | A (+ L explanation) | As OB023 | |
| missingDomainRange | L (D seed) | As OB012 / OB013 | |
| classCapitalCheck | D | Capitalise the label; renaming the IRI is opt-in | breaking (rename) |
| classSpaceCheck | D | Replace spaces in the IRI (deprecate-and-replace) | breaking |
| duplicateLabels | L | As OB016 | |
| spellCheck | D | Apply the computed correction, per word (needs word → subject: see gaps) | guess |
| humanLicense | U | As OB003 | |
| sparqlEndpoint, rdfDump | U | User corrects or removes the URL | |

### 3.7 OOPS! (`src/ontoreview/quality_checks/oops.py`, `src/ontoreview/report/oops.py`)

| Pitfall | Cat. | Suggested fix |
|---|---|---|
| P04 unconnected elements | A (+ L explanation) | As OB023 |
| P07 merging different concepts | M | Explain; the author splits the class |
| P08 missing annotations | D (label) / L (definition) | As OB010 / OB011 |
| P10 missing disjointness | L | Propose sibling pairs to make disjoint; the user confirms |
| P11 missing domain or range | L | As OB012 / OB013 |
| P12 equivalent properties not explicit | D (confirm) | Add `owl:equivalentProperty` for the reported pair (needs pairs kept: see gaps) |
| P13 inverse relationships not explicit | L | Propose inverse pairs; the user confirms |
| P19 multiple domains or ranges | D (choice) | As OB028 |
| P22 inconsistent naming | D | As OB019 |
| P30 equivalent classes not explicit | D (choice) / A | "Likely duplicate classes": OntoAligner confirms the pair; then declare `owl:equivalentClass`, or merge (deprecate one with a replacement) |
| P34 untyped class, P35 untyped property | D | As OB015 |
| P38 no ontology declaration | D | As no_ontology_header |
| P41 no license | U | As OB003 |
| other P-codes | M | Show OOPS!'s explanation |

### 3.8 Cross-domain interoperability (`src/ontoreview/report/cdi.py`)

| Code | Cat. | Suggested fix | Data used |
|---|---|---|---|
| CDI-A unaligned entity | A (+ L explanation) | Candidates are the best correspondence below the threshold plus OLS search, ranked by OntoAligner. Propose `skos:closeMatch` / `skos:exactMatch`, never `owl:equivalentClass` | `per_entity.best_target`, `relation`, `confidence` (`cdi/core.py`) |
| CDI-G very specific definition | L | Rewrite the definition in more general terms, keeping its meaning | The definition, `p_l1…p_l5` |

### 3.9 Summary

| Category | Roughly |
|---|---|
| D (safe) | prefixes, self-references, whitespace, duplicate synonyms, lowercase definitions, obsolete-label prefixes, labels from readable names |
| D (choice, guess or breaking) | cycles of two classes, range kind, inverse-of-itself, union domains, declarations, typo matches, spelling, versionIRI, opt-in renames |
| A | successors, parents and orphans, likely duplicates, external-term candidates, CDI mappings |
| U | title, version, creators, license, choosing between labels/definitions/headers, confirming language tags, URLs |
| L | definitions, descriptions, distinguishing labels, domains/ranges, inverse/disjointness pairs, CQs, generalising definitions |
| M | longer cycles, disjointness conflicts, characteristic conflicts, inconsistency, unsatisfiable classes, equivalent pairs, publishing setup |

## 4. Corrections the code already computes

| What | Where |
|---|---|
| Spelling corrections (first 25 unknown words) | `src/ontoreview/quality_checks/ontocheck.py:178-198` |
| OLS `term_replaced_by` for deprecated external terms | `src/ontoreview/quality_checks/iri/providers.py:102` (`repository_evidence[].replacement`) |
| Expected type for wrong-type external terms | `missing_expected_types`, `src/ontoreview/quality_checks/iri/validate.py:277` |
| Candidate mappings for unaligned entities | `per_entity` in `src/ontoreview/quality_checks/cdi/core.py` (`best_target`, `relation`, `confidence`, `via`) |
| OntoAligner matching (SBERT / fuzzy) | `OntoAlignerSource`, `src/ontoreview/quality_checks/cdi/core.py` |
| Label → IRIs map for duplicate labels | OntoCheck `detail.labels`, `src/ontoreview/quality_checks/ontocheck.py:209` |
| Cycle path | OB014's message |
| Imported vs verified release | `release_mismatches()`, `src/ontoreview/quality_checks/iri/__init__.py` |
| License table | `src/ontoreview/model/licenses.py` |

## 5. Data gaps to close before fixing

| Gap | Where | Why it matters |
|---|---|---|
| ROBOT's Property and Value columns are dropped | `src/ontoreview/report/robot.py:33` | Whitespace and formatting fixes need the offending value |
| OLS replacement isn't carried into the IRI finding | `src/ontoreview/report/iri.py` | deprecated_external_term can't propose the successor |
| OB016 keeps only the first term | `src/ontoreview/quality_checks/rules.py:150` | All duplicates need suggestions |
| OB015 and OB001–OB006 have no subject | `rules.py` | Fixes need a target (the term, or the ontology header) |
| OOPS! equivalence/inverse pairs are flattened | `src/ontoreview/report/oops.py:38` | P12/P13/P30 fixes need the pairing |
| Spell corrections aren't tied to subjects | `quality_checks/ontocheck.py` | Need word → subject → property |
| The reasoner gives no explanations | `src/ontoreview/report/reasoner.py` | An LLM can only explain with justifications (e.g. `robot explain`) |
| OntoAligner is wired only for CDI references | `quality_checks/cdi/core.py` (`OntoAlignerSource`) | It needs a within-ontology mode (successors, parents, duplicates) and a candidate-list mode (OLS results) |
| Folder sources and imports don't record which file each triple came from | `src/ontoreview/loader.py` | The new file and the patch must edit the right file |

## 6. Process: end to end

1. **Run the checks.** As today: built-in rules, ROBOT, reasoner, IRI checks, OntoCheck, CDI, OOPS!.
2. **Build candidates.**
   - **Deterministic fixers:** for D and U findings.
   - **OntoAligner rankings:** for A findings. No LLM is needed.
   - **LLM drafts:** for L findings, only if the user configured an LLM and turned it on.
3. **Check before suggesting.** Apply each candidate to an in-memory copy and re-run **all built-in rules** (cheap), not only the one that fired.
   - If the fix creates a new finding (e.g. a rename triggers OB015 where the old IRI is still used), drop it or show it with that warning.
   - For logical changes, mark whether the reasoner should be re-run (section 10).
   - LLM output must match a JSON schema. Retry once; otherwise discard and say so.
4. **Suggest.** Only checked candidates are shown, with:
   - the finding
   - the options, ranked, with confidence and a reason
   - a diff preview
   - flags (safe / guess / breaking)
   - the source (rule, aligner or LLM)
5. **Decide.** Accept, edit or reject each one. Only fixes flagged **safe** can be accepted in bulk.
6. **Prepare the write.**
   - **Stale check:** the triples a fix removes must still be in the source file. If the file changed since the build, the fix is marked *stale*.
   - **Conflict check:** accepted fixes that touch the same term are detected. Order: annotation fixes, then logical fixes, then renames last.
7. **Write.**
   - **New ontology file:** e.g. `ontology-v2.ttl`, next to the source; the source is never overwritten.
   - **Patch:** a change list / SPARQL Update, so authors can apply it in their own editor.
   - **Formatting:** rdflib reserialization loses comments, ordering and layout. The tool warns about this and points to the patch.
   - **Folders and imports:** each change goes to the file its triple came from.
8. **Validate again.** Re-run the checks on the new file and report what was fixed and anything new.
9. **Record provenance.** For each accepted suggestion, record:
   - **Who and when:** who accepted it, and when.
   - **What produced it:**
     - **Rule:** the fixer id.
     - **OntoAligner:** the matcher type, the embedding model and its version, and the threshold. A different embedding model ranks candidates differently.
     - **LLM:** the provider, endpoint, model name and **model revision**, plus the prompt hash. The revision is the model digest for Ollama, since a tag like `qwen3.5:4b` can change. For cloud providers it is the exact model id the response reports (e.g. a dated snapshot).

   This is stored in the term database and in a sidecar `fix-changes.json`, never inside the user's ontology.
10. **Compare.** Open the existing Compare view (source against new file).
11. **Rebuild.** The user rebuilds the docs from the new file. Only then do the docs change.

**Stable keys.** A suggestion's id is a hash of rule + subject + change. That way its status (accepted, rejected, ignored) survives across builds, and the sidebar badge stays correct. When a subject is renamed through deprecate-and-replace, the ignore entries for that subject follow the `isReplacedBy` link.

## 7. User-provided LLM for documentation

- **What it can suggest:**
  - definitions for terms that have none
  - an ontology description and abstract
  - polished labels
  - alternative labels and synonyms
  - usage examples and notes
  - translations of labels and definitions for multilingual docs (`--lang`)
  - explanations for aligner (A) candidates
- **How:** each is an L suggestion and goes through the same check-then-suggest review (section 6). Nothing is applied automatically, and the generated docs are not touched.
- **Providers:**
  - **Default provider** (used when the user turns AI suggestions on): a small Qwen model on local Ollama (`qwen3.5:4b`, or `qwen3.5:2b` on small machines). It runs on this computer with no key, and the ontology never leaves the machine. The user can pick any other Ollama model.
  - **With an API key (optional):**

    | Provider | API | Base URL (preset) | Key from |
    |---|---|---|---|
    | OpenRouter | OpenAI-compatible | `https://openrouter.ai/api/v1` | Settings or `OPENROUTER_API_KEY` |
    | OpenAI | OpenAI | `https://api.openai.com/v1` | Settings or `OPENAI_API_KEY` |
    | Anthropic | Anthropic Messages API (native) | `https://api.anthropic.com` | Settings or `ANTHROPIC_API_KEY` |
    | Google Gemini | OpenAI-compatible endpoint | Gemini's OpenAI-compatible URL | Settings or `GEMINI_API_KEY` |
    | Mistral, Groq, Together, DeepSeek, … | OpenAI-compatible | their URL | Settings or the provider's env var |
    | Azure OpenAI | OpenAI-compatible, plus deployment name and `api-version` | the user's resource URL | Settings or `AZURE_OPENAI_API_KEY` |
    | Custom (LM Studio, vLLM, LiteLLM, company gateway) | OpenAI-compatible | any URL | optional key |

  - **Two adapters cover all of these:** an OpenAI-compatible chat client (Ollama, OpenRouter, OpenAI, Gemini, Mistral, Groq, Together, DeepSeek, Azure, custom) and a native Anthropic Messages client. Presets only fill in the base URL and the key's environment variable; the user picks the model.
  - **Structured output:** request JSON matching the task's schema where the provider supports it (`response_format` with a JSON schema on OpenAI-compatible APIs, a tool definition on Anthropic, `format` on Ollama). Otherwise, prompt for JSON. Either way, validate against the schema, retry once, and discard on failure.
  - **A "Test connection" button** sends a tiny request and shows the model the provider reports.
- **Privacy:**
  - AI suggestions are off by default, with an on/off switch on the Quality issues page.
  - Cloud providers send text off the machine. Choosing any endpoint that isn't on this computer (anything other than local Ollama or a localhost URL) asks for consent once per provider, and the app shows which provider each suggestion came from.
  - Before the first request, the app shows exactly what text is sent (labels, definitions, parents).
  - With AI off, the page says that AI suggestions are hidden rather than showing nothing.
- **Secrets:** API keys (one per provider) are handled the same way as the CDI keys today. A key typed in Settings takes precedence over the provider's environment variable:
  - `repr=False` in the config
  - the preferences file is readable only by the user
  - never written to TOML, run history, last-run settings, run records or the command line

  Fields named `*_key` / `*_token` get this automatically (`src/ontoreview/ui_core.py`).
- **Models:** the default is small Qwen on Ollama. Other small Ollama models (Gemma 4, Granite 4) are noted in [fix-ideation.md](fix-ideation.md). With a key, any model the provider offers can be used. Candidate ranking is OntoAligner's job, not the LLM's.

## 8. Design sketch

- **Suggestion:**
  - `id`: a stable hash of rule + subject + change
  - `finding`: rule/code and subject
  - `kind`: D/A/U/L/M
  - `title`, `explanation`
  - `change`: triples added and removed, each with its source file
  - `options`: ranked, each with a confidence and a reason
  - `flags`: safe / guess / breaking
  - `checked`: the result of the pre-suggestion check, including any new findings
  - `provenance`: as in section 6
  - `status`: pending / accepted / rejected / ignored / stale / conflict
- **Fixer registry:** keyed by finding code, `fix(finding, graph, ontology, evidence) → candidates`. Each fixer declares its flags. Plugins can add fixers next to their rules (`src/ontoreview/plugins.py` already has `rules()`).
- **LLM client:** a small `Suggester` protocol for text generation, like the CDI `CallableBackend` (`src/ontoreview/quality_checks/cdi/core.py`). It has two adapters:
  - **OpenAI-compatible:** Ollama, OpenRouter, OpenAI, Gemini, Mistral, Groq, Together, DeepSeek, Azure, custom.
  - **Anthropic Messages:** native.

  A provider preset sets the base URL, the key's environment variable and the structured-output method. Input comes from the extracted `Term`; output is checked against a JSON schema. Requests use the same timeout and retry style as the CDI HTTP client (`_HTTP` in `cdi/core.py`), and no provider SDK is required.
- **Reuse:**
  - **OntoAligner wrapper** in `src/ontoreview/quality_checks/cdi/` for candidate ranking. That means external alignment (CDI-A, external-term findings) and alignment within the ontology (successors, parents, duplicates).
  - **Previews:** `TermChange` / `Changelog` and their HTML/Markdown output (`src/ontoreview/diff/__init__.py`).
  - **Suggestions log:** the term database, following the same pattern as the CDI run tables in `src/ontoreview/quality_checks/iri/store.py`.
  - **PROV records:** `add_iri_provenance` (`src/ontoreview/report/iri.py`).
- **Interfaces (proposed):**
  - `ontoreview fix suggest SRC [--llm]` writes `suggestions.json` and a review page
  - `ontoreview fix apply suggestions.json --accept ID… [--accept-safe]` writes the new file and patch, then validates again
  - a "Quality issues" page in the app (section 10)

## 9. Decisions

| Decision | Chosen |
|---|---|
| Where accepted changes go | A **new ontology file** plus a **patch**; the source is never overwritten. No doc-only overrides, because they would let the docs drift from the ontology. |
| How fixes are validated | **Check first, then suggest:** each candidate is tested on a copy before it is shown. The checks run **again** on the written file. |
| Which LLMs | Default: a **small Qwen model on local Ollama** (no key). With an **API key**: OpenRouter, OpenAI, **Anthropic** (native API), Google Gemini, Mistral, Groq, Together, DeepSeek, Azure OpenAI, or any OpenAI-compatible URL. Two adapters: OpenAI-compatible and Anthropic. |
| Candidate ranking | **OntoAligner** (already a dependency through CDI). **No LayaLink**, and no separate judge model. |
| Phase order | **Deterministic first.** The data gaps have to be closed anyway, and D fixers are the easiest to test. |
| Breaking changes | **Fix the label by default.** Renames are opt-in, and only as deprecate-and-replace. |
| Bulk accept | **Yes, only for fixers flagged safe.** |

## 10. App design: the "Quality issues" page

Based on the mockup shared on 2026-11-21 (example: `neuro-celltypes.ttl`), with the review's corrections.

### Layout

- **Sidebar:** a new **Quality issues** entry between Build and Run history, with a badge counting open issues.
- **Page header:**
  - Title "Quality issues" and the subtitle "From the last build of `<file>` · <output type> · each fix shows what changes in the ontology and in the docs."
  - An **AI suggestions on/off** switch (off by default), showing the active provider and model (e.g. "Ollama · qwen3.5:4b" or "OpenRouter · <model>").
  - **Re-run checks**.
  - The write step is split into **Write accepted version (N)**, then Compare (opens automatically), then **Rebuild docs**. A single "apply and rebuild" button would skip the Compare step.
- **Left column, "Found in this build":**
  - Header: "N open · N handled".
  - Filter chips: All, Errors, Warnings, Suggestions.
  - One row per issue: severity badge, source check, short title and the affected terms in monospace. Examples:
    - "Cycle in subClassOf", `:Interneuron ⇄ :GABAergicInterneuron`
    - "Likely duplicate classes", `:PyramidalCell ≈ :PyramidalNeuron`
    - "Orphan class", `:Microglia`
  - States shown on rows: *stale* (the file changed since the build) and *clash* (conflicts with another accepted fix).
- **Centre column, the selected issue:**
  - **Header card:** severity, source and check, title, the affected terms (linked) and a plain explanation. Example: **"Built-in rules · OB014"**, "Cycle in subClassOf": "Each class is declared a subclass of the other, so the reasoner treats them as equivalent and the class diagram loops." This is not an "unsatisfiable hierarchy": a two-class cycle makes the classes equivalent, not unsatisfiable, and the reasoner doesn't report it.
  - **"Suggested fixes" card:**
    - **Options:** ranked radio cards, each with a title, a confidence tag, a one-line reason and a **source badge**: **Rule** (deterministic), **Aligner** (OntoAligner ranking) or **Draft** (LLM text).
    - **Ontology change · Turtle:** a diff of the selected option.
    - **Flags:** safe / guess / breaking.
    - **Actions:** **Accept fix**, **Edit first** (edit the Turtle, which is parsed and checked again before acceptance) and **Ignore in future builds**.
  - **When AI is off:** a card says "AI suggestions are hidden. Turn on AI suggestions to see drafted definitions and explanations." Rule and Aligner suggestions still show.
- **Right column:**
  - **Ontology impact:** axioms added and removed, and "Reasoner after fix" (see costs below).
  - **Docs impact:** "Pages regenerated on the next build", e.g. Interneuron · parents list, Class diagram · loop removed, Quality report · error cleared. This is a *preview*; nothing is written.
  - **Provenance** for the selected suggestion: rule id; or OntoAligner matcher, embedding model, version and threshold; or LLM provider, endpoint, model, revision/digest and prompt hash.
  - **Context card for the issue type:** e.g. "Hierarchy context" with the class path (owl:Thing → :Cell → :Neuron → :Interneuron → :GABAergicInterneuron) highlighted. Other issue types get their own: label conflicts, a property's domain and range, or external candidates.

The mockup's "Domain makes astrocytes neurons" example is **dropped**, because no check produces it. It would only appear as `unsatisfiable_class` (category M) if `:Neuron` and `:GlialCell` were declared disjoint, and then only with reasoner explanations.

### How this fits the rule (section 1)

- **Accept fix only marks a fix as accepted.** Nothing is written.
- **Write accepted version** is the one action that writes. It creates the new file and the patch, never touching the source, then validates them again.
- **Rebuild docs** is a separate, explicit step, taken after Compare.
- **Ignore in future builds** records a suppression in the config (`checks.ignore = [{rule, subject}]`, keyed by the stable suggestion key). It is a config change the user makes and doesn't edit the ontology.

### Cost of the impact panels

- **Annotation-only changes** (labels, definitions, synonyms) can't change what the reasoner infers, so "Reasoner after fix" is skipped for them.
- **Logical changes:** the reasoner runs **on demand** (a "Check with reasoner" button), not every time an option is selected. HermiT can take minutes on large ontologies.
- **Docs impact:** the dry run (extract the model from the patched copy and diff it with the `diff` module) is cached per suggestion.

### Changes this design implies

- **Per-finding suppression:** `checks.ignore`. Today only `checks.disable` (a whole rule) and `checks.severity` exist (`src/ontoreview/config.py`).
- **Ranking two-class cycles and duplicates:** a heuristic decides which term is narrower by label and definition, or has more subclasses. OntoAligner can confirm duplicates. An LLM, if on, only writes the reason text.
- **A short human title and a context renderer for each finding type.**
- **The sidebar badge and the "handled" count** need the suggestions log (section 8), keyed by the stable id.

## 11. Phases and verification

**Phases:**
1. **Deterministic:** close the data gaps (section 5); add the suggestion model with stable ids and flags, the D and U fixers, check-then-suggest, the stale and conflict checks, writing the new file and patch, validating again, and the CLI.
2. **App:** the "Quality issues" page (section 10).
3. **OntoAligner:** candidate ranking for A findings, in-ontology and OLS-candidate modes.
4. **LLM:** the two adapters (OpenAI-compatible, Anthropic) with provider presets, Settings fields for each provider's key and model, a "Test connection" button, then suggestions for L findings, explanations, and documentation improvements (section 7).

**Verification:**
- **Each fixer:** a fixture with the defect → candidate → pre-check → apply → the finding is gone, **no new finding from the built-in rules**, and the graph is otherwise unchanged.
- **Stale and conflict:** edit the source after the build → the suggestion is marked stale. Accept a rename and a label fix on the same term → a conflict, applied in order.
- **Renames:** the old IRI is still present, marked deprecated with `dcterms:isReplacedBy`.
- **Patch:** applying the patch to the source gives a graph isomorphic to the new file.
- **LLM path:** stub servers in tests, one OpenAI-compatible and one Anthropic Messages. Check schema validation, the retry, discarding bad output, key precedence (Settings over environment variable), that keys never appear in records, and that nothing is applied without acceptance.
- **The rule, as a test:** generated docs are byte-identical whether or not suggestions exist.
- **Live:** OntoAligner and local Ollama `qwen3.5:4b` on the CDI examples (`examples/cdi-soil`, `cdi-sosa`, `cdi-prov-o`). Then the same with one key-based provider (OpenRouter or Anthropic).

## 12. Still to verify before implementing

- **ROBOT rule names:** the names in section 3.3 come from ROBOT's documentation, not our code. Check them against a real report.
- **Qwen 3.5 licence:** not verified (see [fix-ideation.md](fix-ideation.md)). Confirm it before making it the default.
- **Gemini and Azure:** both are expected to work through the OpenAI-compatible adapter, and Azure also needs a deployment name and API version. Test both before listing them as supported.
- **Structured output per provider:** confirm which of `response_format` (JSON schema), Anthropic tools and Ollama `format` each preset can use. Fall back to prompting for JSON.
- **OntoAligner modes:** confirm OntoAligner can rank candidates within one ontology (successors, parents, duplicates) and rank a given candidate list (OLS results), not only align two files as the CDI check does now.
