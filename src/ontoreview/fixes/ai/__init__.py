"""AI drafts for fixes: definitions for terms without one, refined definitions, and an ontology
description. Each draft is an ``L`` suggestion: shown with the model that wrote it, applied only
when the user accepts it (as is, or edited).

    src = pick_source(cfg.ai)                       # Hugging Face → Ollama → API, per priority
    s = draft_definition(session, term_iri, src)    # Suggestion; session.accept(s.id, text=…)
"""

from __future__ import annotations

import hashlib

from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, RDFS, SKOS

from ..model import Option, Suggestion, n3
from .sources import AIError, extract_json, make_source, pick_source

SYSTEM = ("You help ontology authors. You write precise, neutral English for ontology annotations. "
          "You never invent facts beyond what the context implies.")
DEF_SCHEMA = {"type": "object", "properties": {"definition": {"type": "string"}, "reason": {"type": "string"}},
              "required": ["definition"]}
DESC_SCHEMA = {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]}
IAO_DEF = URIRef("http://purl.obolibrary.org/obo/IAO_0000115")
DEF_PROPS = (SKOS.definition, IAO_DEF, RDFS.comment)


def _ask(source, user: str, schema: dict, key: str) -> tuple[dict, dict]:
    """Ask once, retry once on invalid output; return (answer, provenance)."""
    last = None
    for _ in range(2):
        try:
            ans = source.generate(SYSTEM, user, schema)
            text = ans.get(key)
            if (isinstance(text, str) and text.strip()) or (isinstance(text, list) and text):
                prov = source.describe() | {"type": "llm",
                                            "prompt_sha256": hashlib.sha256(user.encode()).hexdigest()[:16]}
                return ans, prov
            last = f"the answer has no {key}"
        except (ValueError, KeyError, TypeError) as e:
            last = str(e)
    raise AIError(f"The model's answer was not usable ({last}); nothing was suggested.")


def _context(onto, t) -> str:
    lines = [f"Term: {t.label} ({t.kind_label})", f"IRI: {t.iri}"]
    if t.superclasses:
        lines.append("Parents: " + ", ".join(r.label for r in t.superclasses[:5]))
    if t.subclasses:
        lines.append("Children: " + ", ".join(r.label for r in t.subclasses[:5]))
    if getattr(t, "domain", None):
        lines.append("Domain: " + ", ".join(str(getattr(d, "label", d)) for d in t.domain[:3]))
    if getattr(t, "range", None):
        lines.append("Range: " + ", ".join(str(getattr(r, "label", r)) for r in t.range[:3]))
    syn = [x for v in t.labels.values() for x in v if x != t.label][:5]
    if syn:
        lines.append("Other labels: " + ", ".join(syn))
    if onto.metadata.title:
        lines.append(f"Ontology: {onto.metadata.title}")
    return "\n".join(lines)


def draft_definition(session, iri: str, source) -> Suggestion:
    """A definition for a term that has none (genus–differentia: "A <parent> that …")."""
    t = session.onto.terms[iri]
    user = (f"{_context(session.onto, t)}\n\nWrite one definition for this term, in the form "
            "\"A <parent> that <distinguishing features>.\" One sentence, no circular wording.")
    ans, prov = _ask(source, user, DEF_SCHEMA, "definition")
    text = ans["definition"].strip()
    return Suggestion("OB011", iri, "L", "Add a definition (AI draft)",
                      f"Drafted from the label, parents and children of “{t.label}”. Check it before accepting.",
                      options=[Option("Use this definition", add=[n3((URIRef(iri), SKOS.definition, Literal(text, lang="en")))],
                                      confidence="medium", reason=ans.get("reason", ""))],
                      made_by=prov)


def refine_definition(session, iri: str, source, instruction: str = "") -> Suggestion:
    """A clearer (or more general) version of an existing definition, on the same property."""
    t = session.onto.terms[iri]
    g = session.graph
    old = next(((p, o) for p in DEF_PROPS for o in g.objects(URIRef(iri), p) if isinstance(o, Literal)), None)
    if old is None:
        return draft_definition(session, iri, source)
    p, o = old
    how = instruction or "clearer and more precise, in genus–differentia form, keeping its meaning"
    user = (f"{_context(session.onto, t)}\nCurrent definition: {o}\n\nRewrite the definition to be {how}. "
            "One or two sentences.")
    ans, prov = _ask(source, user, DEF_SCHEMA, "definition")
    text = ans["definition"].strip()
    s = Suggestion("FX010", iri, "L", "Refined definition: AI draft",
                   f"Current: “{o}”.",
                   options=[Option("Use the refined definition", remove=[n3((URIRef(iri), p, o))],
                                   add=[n3((URIRef(iri), p, Literal(text, lang=o.language or "en")))],
                                   confidence="medium", reason=ans.get("reason", ""))],
                   made_by=prov)
    return s


def draft_description(session, source) -> tuple[str, dict]:
    """Text for the ontology description (the required-metadata field), from its title and classes."""
    onto = session.onto
    classes = [t.label for t in onto.terms.values() if t.kind == "class" and not t.imported][:25]
    user = (f"Ontology title: {onto.metadata.title or '(none)'}\nNamespace: {onto.namespace}\n"
            f"Some classes: {', '.join(classes)}\n\nWrite a 1–2 sentence description of what this ontology covers "
            "and who it is for.")
    ans, prov = _ask(source, user, DESC_SCHEMA, "description")
    return ans["description"].strip(), prov


CHOICE_SCHEMA = {"type": "object", "properties": {"choices": {"type": "array", "items": {
    "type": "object", "properties": {"iri": {"type": "string"}, "reason": {"type": "string"}}, "required": ["iri"]}}},
    "required": ["choices"]}
XSD = "http://www.w3.org/2001/XMLSchema#"


def suggest_domain_range(session, iri: str, which: str, source) -> Suggestion:
    """Up to three ranked domain (or range) candidates for a property, each with a reason. Only IRIs of the
    ontology's own classes (or XSD types for a datatype range) are kept; anything else is discarded."""
    from rdflib.namespace import RDFS as _RDFS
    t = session.onto.terms[iri]
    if which == "range" and t.kind == "datatype_property":
        cands = {f"{XSD}{x}": f"xsd:{x}" for x in ("string", "boolean", "integer", "decimal", "double", "dateTime",
                                                   "date", "anyURI")}
    else:
        cands = {c.iri: c.label for c in session.onto.terms.values() if c.kind == "class" and not c.imported}
    if not cands:
        raise AIError("No classes to choose from.")
    listing = "\n".join(f"{k} | {v}" for k, v in list(cands.items())[:80])
    user = (f"{_context(session.onto, t)}\nDefinition: {t.definition or '(none)'}\n\nWhich class is the {which} of this "
            f"property ({'the things it describes' if which == 'domain' else 'the values it points to'})? Choose up to "
            f"three from this list (IRI | label), best first, with a short reason each:\n{listing}")
    ans, prov = _ask(source, user, CHOICE_SCHEMA, "choices")
    pred = _RDFS.domain if which == "domain" else _RDFS.range
    opts = []
    for i, c in enumerate([c for c in ans["choices"] if isinstance(c, dict) and c.get("iri") in cands][:3]):
        opts.append(Option(f"{which.title()}: {cands[c['iri']]}", add=[n3((URIRef(iri), pred, URIRef(c["iri"])))],
                           confidence=("high", "medium", "low")[i], reason=str(c.get("reason", ""))))
    if not opts:
        raise AIError("The model suggested no class of this ontology; pick one yourself.")
    return Suggestion("OB012" if which == "domain" else "OB013", iri, "L", f"Add a {which} (AI suggestion)",
                      "Suggested from the property's name, definition and the ontology's classes. Check before accepting.",
                      options=opts, made_by=prov)


def ai_suggestions(session, source, limit: int = 20) -> list[Suggestion]:
    """AI drafts for terms without a definition (OB011), added to the session."""
    out = []
    for f in session.report.findings:
        if len(out) >= limit or f.subject not in session.onto.terms:
            continue
        if f.rule == "OB011":
            out.append(session.replace(draft_definition(session, f.subject, source)))
        elif f.rule in ("OB012", "OB013") and any(x.rule == f.rule and x.subject == f.subject and x.kind == "U"
                                                 for x in session.suggestions):
            try:
                out.append(session.replace(suggest_domain_range(
                    session, f.subject, "domain" if f.rule == "OB012" else "range", source)))
            except AIError:
                pass        # keep the plain choice
    return out


__all__ = ["AIError", "DCTERMS", "ai_suggestions", "suggest_domain_range", "draft_definition", "draft_description", "extract_json",
           "make_source", "pick_source", "refine_definition"]
