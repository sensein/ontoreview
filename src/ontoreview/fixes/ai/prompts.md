# OntoReview AI prompts

These are the prompts OntoReview sends to the language model (Ollama, Hugging Face or an API) for
fix suggestions. The code reads this file: edit a prompt here and the next AI draft uses it.

To use your own wording without editing the package, copy this file, change the sections you want
and set `ONTOREVIEW_PROMPTS=/path/to/prompts.md`. Sections you leave out keep the defaults below.

How the file works:

- Each `## name` heading is one prompt; its text is the fenced block under it.
- `{placeholders}` are filled in by OntoReview (listed under each prompt). Keep them, or the
  prompt loses that information. To write a literal brace, double it: `{{` or `}}`.
- The answer is always JSON. Ollama, OpenAI-compatible APIs and Anthropic enforce the schema
  themselves; for Hugging Face models (and APIs without structured output) the `json_answer`
  instruction is appended.
- Each suggestion's provenance records the model and a SHA-256 of the prompt it was sent, so a
  changed prompt can be told apart in `provenance.ttl` and the `.fixes.json` record.

## system

Sent as the system message with every request.

```text
You help ontology authors. You write precise, neutral English for ontology annotations. You never invent facts beyond what the context implies.
```

## definition

A definition for a term that has none (issue OB011). Answer: `{"definition": "...", "reason": "..."}`.

- `{context}`: the term context block (see "Term context" below)

```text
{context}

Write one definition for this term, in the form "A <parent> that <distinguishing features>." One sentence, no circular wording.
```

## refine

A clearer version of an existing definition, kept on the same property. Answer: `{"definition": "...", "reason": "..."}`.

- `{context}`: the term context block
- `{current}`: the current definition
- `{how}`: what the user asked for, or `refine_default` below

```text
{context}
Current definition: {current}

Rewrite the definition to be {how}. One or two sentences.
```

## refine_default

Used for `{how}` in `refine` when the user gives no instruction.

```text
clearer and more precise, in genus–differentia form, keeping its meaning
```

## description

The ontology description (required metadata, issue OB002). Answer: `{"description": "..."}`.

- `{title}`: the ontology title, or `(none)`
- `{namespace}`: the ontology namespace
- `{classes}`: up to 25 class labels, comma-separated

```text
Ontology title: {title}
Namespace: {namespace}
Some classes: {classes}

Write a 1–2 sentence description of what this ontology covers and who it is for.
```

## domain_range

Up to three ranked domain (or range) candidates for a property (issues OB012, OB013). Answer:
`{"choices": [{"iri": "...", "reason": "..."}]}`. Only IRIs from `{listing}` are kept.

- `{context}`: the term context block
- `{definition}`: the property's definition, or `(none)`
- `{which}`: `domain` or `range`
- `{role}`: `role_domain` or `role_range` below
- `{listing}`: candidate classes (or XSD types), one `IRI | label` per line, at most 80

```text
{context}
Definition: {definition}

Which class is the {which} of this property ({role})? Choose up to three from this list (IRI | label), best first, with a short reason each:
{listing}
```

## role_domain

```text
the things it describes
```

## role_range

```text
the values it points to
```

## json_answer

Appended to the user message for models without structured output. `{schema}` is the JSON
Schema of the expected answer.

```text
Answer with one JSON object only, matching: {schema}
```

## Term context

Not a prompt you can edit here: the `{context}` block is built from the ontology, one line each
when present, for example:

```text
Term: soil pH (class)
IRI: https://example.org/soil#SoilPH
Parents: Soil property
Children: Topsoil pH
Domain: …
Range: …
Other labels: soil acidity
Ontology: Soil sensing
```
