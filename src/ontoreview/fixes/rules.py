"""Fixers for the built-in rules: exact edits (D), values only the user knows (U), and manual
issues shown with their evidence (M). One function per finding code, in :data:`FIXERS`.

A fixer gets the finding, the graph and the extracted ontology, and returns a :class:`Suggestion`
(or None when it cannot help). It never edits the graph.
"""

from __future__ import annotations

import re
from collections import Counter

from rdflib import Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, FOAF, OWL, RDF, RDFS, SKOS

from ..model.licenses import _LICENSES
from .model import Field_, Option, Suggestion, n3

VANN = Namespace("http://purl.org/vocab/vann/")
IAO_DEF = URIRef("http://purl.obolibrary.org/obo/IAO_0000115")
LABEL_PROPS = (RDFS.label, SKOS.prefLabel)
TEXT_PROPS = (RDFS.label, SKOS.prefLabel, SKOS.altLabel, SKOS.definition, IAO_DEF, RDFS.comment,
              DCTERMS.title, DCTERMS.description)
DEF_PROPS = (SKOS.definition, IAO_DEF, RDFS.comment)
OPAQUE = re.compile(r"^[A-Za-z]{1,10}[_:]?\d{3,}$|^\d+$")       # CL_0000540, GO0008150, 12345
REQUIRED = ("OB001", "OB002", "OB003", "OB005")

FIXERS: dict = {}


def fixer(code: str):
    def deco(fn):
        FIXERS[code] = fn
        return fn
    return deco


def ontology_node(g, onto) -> tuple[URIRef, list]:
    """The owl:Ontology node, and the triple that creates it when the file has none."""
    for s in g.subjects(RDF.type, OWL.Ontology):
        if isinstance(s, URIRef):
            return s, []
    ns = onto.namespace or "urn:ontology:"
    node = URIRef(ns.rstrip("#/") or ns)
    return node, [n3((node, RDF.type, OWL.Ontology))]


def made_by(code: str) -> dict:
    return {"type": "rule", "id": f"fix-{code.lower()}"}


# ---------------------------------------------------------------- required metadata (U)
@fixer("OB001")
def title(f, g, onto):
    node, _ = ontology_node(g, onto)
    tail = re.split(r"[/#]", str(node).rstrip("/#"))[-1]
    guess = re.sub(r"[-_]+", " ", tail).strip() if tail and not tail.startswith("urn") else ""
    return Suggestion(f.rule, onto.metadata.iri, "U", "Add a title",
                      "The ontology has no title. It is the heading of the docs and of citations.",
                      fields=[Field_("title", "Title", value="", hint=guess.title() if guess else "e.g. Soil Sensing Ontology")],
                      required=True, made_by=made_by(f.rule))


@fixer("OB002")
def description(f, g, onto):
    return Suggestion(f.rule, onto.metadata.iri, "U", "Add a description",
                      "One or two sentences on what the ontology covers and who it is for. An AI draft can "
                      "suggest one; you confirm it.",
                      fields=[Field_("description", "Description", "textarea")],
                      required=True, made_by=made_by(f.rule))


def license_choices() -> list[tuple[str, str]]:
    seen, out = set(), []
    for url, label in _LICENSES.items():
        if label not in seen:
            seen.add(label)
            out.append((f"https://{url}/" if "creativecommons" in url else f"https://{url}", label))
    return out


@fixer("OB003")
def license_(f, g, onto):
    return Suggestion(f.rule, onto.metadata.iri, "U", "Add a license",
                      "Without a license nobody knows how they may reuse the ontology.",
                      fields=[Field_("license", "License", "license", license_choices(),
                                     value="https://creativecommons.org/licenses/by/4.0/")],
                      required=True, made_by=made_by(f.rule))


@fixer("OB005")
def creators(f, g, onto):
    return Suggestion(f.rule, onto.metadata.iri, "U", "Add the creators",
                      "Credit the authors: one row per creator, with an ORCID and a contact email if you have them.",
                      fields=[Field_("creators", "Creators", "creators",
                                     hint="Ada Lovelace https://orcid.org/0000-0002-1825-0097")],
                      required=True, made_by=made_by(f.rule))


@fixer("OB004")
def version(f, g, onto):
    if "versionInfo" not in f.message:          # the versionIRI half follows from the version
        return None
    return Suggestion(f.rule, onto.metadata.iri, "U", "Add a version",
                      "A version (owl:versionInfo) and a version IRI make releases citable and comparable.",
                      fields=[Field_("version", "Version", value="1.0.0",
                                     hint="The version IRI becomes <ontology IRI>/<version>/")],
                      made_by=made_by(f.rule))


def resolve_fields(s: Suggestion, values: dict, g, onto) -> Option:
    """Turn the user's values for a U suggestion into an exact change."""
    node, create = ontology_node(g, onto)
    add = list(create)
    v = {k: (values.get(k) or "").strip() for k in [x.name for x in s.fields]}
    if s.rule == "OB001":
        add.append(n3((node, DCTERMS.title, Literal(v["title"], lang="en"))))
    elif s.rule == "OB002":
        add.append(n3((node, DCTERMS.description, Literal(v["description"], lang="en"))))
    elif s.rule == "OB003":
        add.append(n3((node, DCTERMS.license, URIRef(v["license"]))))
    elif s.rule == "OB005":
        for c in parse_creators(v["creators"]):
            if c["orcid"]:
                orcid = URIRef(c["orcid"])
                add += [n3((node, DCTERMS.creator, orcid)), n3((orcid, FOAF.name, Literal(c["name"])))]
                if c["email"]:
                    add.append(n3((orcid, FOAF.mbox, URIRef(f"mailto:{c['email']}"))))
            else:          # "Name <email>" is read back as a name with a contact address
                add.append(n3((node, DCTERMS.creator, Literal(f"{c['name']} <{c['email']}>" if c["email"] else c["name"]))))
    elif s.rule == "OB011":
        add = [n3((URIRef(s.subject), SKOS.definition, Literal(v["definition"], lang="en")))]
    elif s.rule in ("OB012", "OB013"):
        key = "domain" if s.rule == "OB012" else "range"
        add = [n3((URIRef(s.subject), RDFS.domain if key == "domain" else RDFS.range, URIRef(v[key])))]
    elif s.rule == "OB010":
        add = [n3((URIRef(s.subject), RDFS.label, Literal(v["label"], lang="en")))]
    elif s.rule == "OB004":
        add.append(n3((node, OWL.versionInfo, Literal(v["version"]))))
        if not onto.metadata.version_iri and v["version"]:
            add.append(n3((node, OWL.versionIRI, URIRef(f"{str(node).rstrip('/#')}/{v['version']}/"))))
    return Option("Use these values", add=add, reason="Values you entered.")


ORCID_RE = re.compile(r"(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.I)
EMAIL_RE = re.compile(r"<?([^\s<>@]+@[^\s<>@]+\.[^\s<>@]+)>?")


def parse_creators(text: str) -> list[dict]:
    """Creators, one per line: "Name | ORCID | email" (the app's rows) or free text such as
    "Ada Lovelace <ada@example.org> https://orcid.org/0000-0002-1825-0097". Lines without a name are skipped."""
    out = []
    for line in [x.strip() for x in (text or "").splitlines() if x.strip()]:
        if "|" in line:
            name, orcid, email = ([p.strip() for p in line.split("|")] + ["", "", ""])[:3]
        else:
            orcid = (m.group(0) if (m := ORCID_RE.search(line)) else "")
            email = (m.group(1) if (m := EMAIL_RE.search(line.replace(orcid, ""))) else "")
            name = re.sub(r"\s+", " ", line.replace(orcid, "").replace(f"<{email}>", "").replace(email, "")).strip(" ,;")
        om = ORCID_RE.search(orcid or "")
        orcid = f"https://orcid.org/{om.group(1).upper()}" if om else ""
        em = EMAIL_RE.search(email or "")
        if name:
            out.append({"name": name, "orcid": orcid, "email": em.group(1) if em else ""})
    return out


def creator_text(c: dict) -> str:
    """One creator as LinkML text, read back by the LinkML loader: "Name <email> https://orcid.org/…"."""
    return " ".join(x for x in (c["name"], f"<{c['email']}>" if c["email"] else "", c["orcid"]) if x)


def missing_values(s: Suggestion, values: dict) -> list[str]:
    out = [x.label for x in s.fields if not (values.get(x.name) or "").strip()]
    if s.rule == "OB005" and "Creators" not in out and not parse_creators(values.get("creators", "")):
        out.append("Creators (a name)")
    bad = [line for line in (values.get("creators") or "").splitlines()
           if "|" in line and line.split("|")[1].strip() and not ORCID_RE.search(line.split("|")[1])]
    if s.rule == "OB005" and bad:
        out.append("a valid ORCID (0000-0000-0000-0000)")
    return out


# ---------------------------------------------------------------- exact edits (D)
@fixer("OB006")
def prefix(f, g, onto):
    node, create = ontology_node(g, onto)
    ns = onto.namespace
    if not ns:
        return None
    bound = next((p for p, u in g.namespaces() if str(u) == ns and p), None)
    guess = bound is None
    pre = bound or re.sub(r"[^a-z0-9]", "", str(node).rstrip("/#").rsplit("/", 1)[-1].lower())[:12] or "onto"
    return Suggestion(f.rule, str(node), "D", "Add the preferred prefix",
                      f"Readers and tools use `{pre}:` for this namespace.",
                      options=[Option(f"Prefix {pre}:", add=create + [
                          n3((node, VANN.preferredNamespacePrefix, Literal(pre))),
                          n3((node, VANN.preferredNamespaceUri, Literal(ns)))],
                          confidence="medium" if guess else "high",
                          reason="Guessed from the ontology IRI." if guess else "The prefix bound to the namespace.")],
                      flags=["guess"] if guess else ["safe"], made_by=made_by(f.rule))


def readable(local: str) -> str | None:
    """A label from a readable local name (camelCase, snake_case); None for opaque ids."""
    if not local or OPAQUE.match(local):
        return None
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", re.sub(r"[_\-]+", " ", local)).strip()
    words = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", words)
    if not re.search(r"[A-Za-z]{2,}", words):
        return None
    parts = words.split()
    return " ".join(p if p.isupper() and len(p) > 1 else p.lower() for p in parts)


@fixer("OB010")
def label(f, g, onto):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    lab = readable(t.local_name)
    if lab is None:
        return Suggestion(f.rule, t.iri, "U", "Add a label",
                          f"`{t.local_name}` is an id, not a name: type the label.",
                          fields=[Field_("label", "Label")], made_by=made_by(f.rule))
    return Suggestion(f.rule, t.iri, "D", "Add a label from the name",
                      f"“{lab}”, from `{t.local_name}`.",
                      options=[Option(f"Label “{lab}”", add=[n3((URIRef(t.iri), RDFS.label, Literal(lab, lang="en")))],
                                      reason="Split from the IRI's local name.")],
                      flags=["safe"], made_by=made_by(f.rule))


@fixer("OB014")
def cycle(f, g, onto):
    a = URIRef(f.subject)
    others = [o for o in g.objects(a, RDFS.subClassOf) if isinstance(o, URIRef) and (o, RDFS.subClassOf, a) in g]
    if not others:
        return Suggestion(f.rule, f.subject, "M", "Cycle in the class hierarchy",
                          f"{f.message}. Longer cycles need a modelling decision: remove one subClassOf on the path.",
                          made_by=made_by(f.rule))
    b = others[0]
    ta, tb = onto.terms.get(str(a)), onto.terms.get(str(b))

    def narrowness(t) -> tuple:
        return (len(t.label) if t else 0, -(len(t.subclasses) if t else 0))
    narrow, broad = (a, b) if narrowness(ta) >= narrowness(tb) else (b, a)
    ln = lambda x: onto.terms[str(x)].label if str(x) in onto.terms else str(x)  # noqa: E731
    return Suggestion(f.rule, f.subject, "D", "Cycle in subClassOf",
                      f"“{ln(a)}” and “{ln(b)}” are declared subclasses of each other, so a reasoner treats them as "
                      "equivalent and the class diagram loops.",
                      options=[Option(f"Remove the inverted axiom: keep “{ln(narrow)}” under “{ln(broad)}”",
                                      remove=[n3((broad, RDFS.subClassOf, narrow))], confidence="high",
                                      reason=f"“{ln(narrow)}” looks narrower (longer name, fewer subclasses)."),
                               Option("Declare them equivalent",
                                      remove=[n3((a, RDFS.subClassOf, b)), n3((b, RDFS.subClassOf, a))],
                                      add=[n3((a, OWL.equivalentClass, b))], confidence="medium",
                                      reason="If both names mean the same set of things.")],
                      made_by=made_by(f.rule))


@fixer("OB017")
def several_labels(f, g, onto):
    s = URIRef(f.subject)
    by_lang: dict = {}
    for p in LABEL_PROPS:
        for o in g.objects(s, p):
            if isinstance(o, Literal):
                by_lang.setdefault(o.language or "", []).append((p, o))
    lang, labs = next(((k, v) for k, v in by_lang.items() if len({str(x[1]) for x in v}) > 1), (None, []))
    if not labs:
        return None
    opts = []
    for _, keep in labs:
        opts.append(Option(f"Keep “{keep}”", remove=[n3((s, p, o)) for p, o in labs if o != keep],
                           add=[n3((s, SKOS.altLabel, o)) for p, o in labs if o != keep],
                           confidence="medium", reason="The other labels become alternative labels (skos:altLabel)."))
    return Suggestion(f.rule, f.subject, "D", "Several labels in one language",
                      f"Pick the label to keep{' (@' + lang + ')' if lang else ''}; nothing is lost.",
                      options=opts, made_by=made_by(f.rule))


@fixer("OB022")
def self_reference(f, g, onto):
    s = URIRef(f.subject)
    rem = [n3((s, p, s)) for p in (RDFS.subClassOf, OWL.equivalentClass, RDFS.subPropertyOf) if (s, p, s) in g]
    if not rem:
        return None
    return Suggestion(f.rule, f.subject, "D", "Remove the self-reference",
                      "A term that is a subclass/subproperty of, or equivalent to, itself says nothing.",
                      options=[Option("Remove it", remove=rem, reason="Always true; removing it changes nothing logically.")],
                      flags=["safe"], made_by=made_by(f.rule))


@fixer("OB025")
def inverse_self(f, g, onto):
    s = URIRef(f.subject)
    return Suggestion(f.rule, f.subject, "D", "Inverse of itself",
                      "A property that is its own inverse is symmetric.",
                      options=[Option("Declare it symmetric", add=[n3((s, RDF.type, OWL.SymmetricProperty))],
                                      confidence="high", reason="Already implied; makes it explicit, changes nothing logically."),
                               Option("Remove owl:inverseOf", remove=[n3((s, OWL.inverseOf, s))], confidence="medium",
                                      reason="Changes the meaning: the property is no longer symmetric.")],
                      made_by=made_by(f.rule))


@fixer("OB026")
def language_tags(f, g, onto):
    s = URIRef(f.subject)
    langs = Counter(o.language for o in g.objects(None, RDFS.label) if isinstance(o, Literal) and o.language)
    if not langs:
        return None
    lang = langs.most_common(1)[0][0]
    untagged = [o for o in g.objects(s, RDFS.label) if isinstance(o, Literal) and not o.language]
    if not untagged:
        return None
    return Suggestion(f.rule, f.subject, "D", f"Tag the label as @{lang}",
                      f"Most labels are @{lang}. Check that “{untagged[0]}” is in that language.",
                      options=[Option(f"Tag @{lang}", remove=[n3((s, RDFS.label, o)) for o in untagged],
                                      add=[n3((s, RDFS.label, Literal(str(o), lang=lang))) for o in untagged],
                                      confidence="medium", reason=f"The ontology's main language is {lang}.")],
                      flags=["guess"], made_by=made_by(f.rule))


# ---------------------------------------------------------------- definitions, domain/range (U, AI drafts)
@fixer("OB011")
def definition(f, g, onto):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    return Suggestion(f.rule, t.iri, "U", "Add a definition",
                      f"“{t.label}” has no definition. Type one, or let AI draft it (you review it before it is used).",
                      fields=[Field_("definition", "Definition", "textarea",
                                     hint=f"A {(t.superclasses[0].label if t.superclasses else 'thing')} that …")],
                      made_by=made_by(f.rule))


def _class_choices(onto) -> list[tuple[str, str]]:
    return sorted(((t.iri, t.label) for t in onto.terms.values() if t.kind == "class" and not t.imported),
                  key=lambda x: x[1].lower())


def _usage(g, prop: URIRef) -> tuple[list[str], list[str]]:
    """(domain seeds, range seeds) from restrictions on the property: the classes it restricts and the fillers."""
    doms, rngs = [], []
    for r in g.subjects(OWL.onProperty, prop):
        for cls in g.subjects(RDFS.subClassOf, r):
            if isinstance(cls, URIRef):
                doms.append(str(cls))
        for p_ in (OWL.someValuesFrom, OWL.allValuesFrom):
            for o in g.objects(r, p_):
                if isinstance(o, URIRef):
                    rngs.append(str(o))
    for s_, o in g.subject_objects(prop):          # assertions: the types of subjects and objects
        doms += [str(c) for c in g.objects(s_, RDF.type) if isinstance(c, URIRef) and c != OWL.NamedIndividual]
        rngs += [str(c) for c in g.objects(o, RDF.type) if isinstance(c, URIRef) and c != OWL.NamedIndividual]
    return list(dict.fromkeys(doms)), list(dict.fromkeys(rngs))


def _domain_range(f, g, onto, which: str):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    p = URIRef(t.iri)
    seeds = _usage(g, p)[0 if which == "domain" else 1]
    pred = RDFS.domain if which == "domain" else RDFS.range
    lab = lambda i: onto.terms[i].label if i in onto.terms else i  # noqa: E731
    if seeds:
        return Suggestion(f.rule, t.iri, "D", f"Add a {which}",
                          f"“{t.label}” is used with these classes; pick the {which}.",
                          options=[Option(f"{which.title()}: {lab(c)}", add=[n3((p, pred, URIRef(c)))],
                                          confidence="medium", reason="From how the property is used in the ontology.")
                                   for c in seeds[:4]],
                          flags=["guess"], made_by=made_by(f.rule))
    choices = _class_choices(onto)
    if which == "range" and t.kind == "datatype_property":
        choices = [(f"http://www.w3.org/2001/XMLSchema#{x}", f"xsd:{x}")
                   for x in ("string", "boolean", "integer", "decimal", "double", "dateTime", "date", "anyURI")]
    if not choices:
        return None
    return Suggestion(f.rule, t.iri, "U", f"Add a {which}", f"Pick the {which} of “{t.label}”.",
                      fields=[Field_(which, which.title(), "choice", choices)], made_by=made_by(f.rule))


FIXERS["OB012"] = lambda f, g, onto: _domain_range(f, g, onto, "domain")
FIXERS["OB013"] = lambda f, g, onto: _domain_range(f, g, onto, "range")


# ---------------------------------------------------------------- undeclared terms, wrong range type
@fixer("OB015")
def undeclared(f, g, onto):
    m = re.search(r"`([^`]+)`", f.message)
    if not m:
        return None
    iri = URIRef(m.group(1))
    as_pred = any(True for _ in g.triples((None, iri, None)))
    as_class = any((None, p_, iri) in g for p_ in (RDF.type, RDFS.subClassOf, RDFS.domain, RDFS.range,
                                                  OWL.someValuesFrom, OWL.allValuesFrom, OWL.equivalentClass))
    opts = []
    if as_pred:
        lit = any(isinstance(o, Literal) for o in g.objects(None, iri))
        kinds = [(OWL.DatatypeProperty, "datatype property"), (OWL.ObjectProperty, "object property")]
        for k, name in (kinds if lit else kinds[::-1]):
            opts.append(Option(f"Declare it an {name}" if name[0] in "o" else f"Declare it a {name}",
                               add=[n3((iri, RDF.type, k))], confidence="medium",
                               reason="It is used as a property" + (" with text values." if lit else ".")))
    if as_class or not opts:
        opts.insert(0 if as_class else len(opts), Option("Declare it a class", add=[n3((iri, RDF.type, OWL.Class))],
                                                         confidence="high" if as_class else "low",
                                                         reason="It is used where a class is expected."))
    declared = [t.iri for t in onto.terms.values() if not t.imported]
    from difflib import get_close_matches
    close = get_close_matches(str(iri), declared, n=1, cutoff=0.85)
    if close:
        new = URIRef(close[0])
        rem, add = [], []
        for t3 in g:
            if iri in t3:
                rem.append(n3(t3))
                add.append(n3(tuple(new if x == iri else x for x in t3)))
        opts.append(Option(f"Replace with `{close[0].rsplit('/', 1)[-1].rsplit('#', 1)[-1]}` (likely a typo)",
                           add=add, remove=rem, confidence="medium", reason="A declared term with an almost identical IRI."))
    return Suggestion(f.rule, str(iri), "D", "Undeclared term",
                      f"`{iri}` is used but never declared.", options=opts, flags=["guess"], made_by=made_by(f.rule))


@fixer("OB024")
def wrong_range(f, g, onto):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    p = URIRef(t.iri)
    new_kind = OWL.ObjectProperty if t.kind == "datatype_property" else OWL.DatatypeProperty
    old_kind = OWL.DatatypeProperty if t.kind == "datatype_property" else OWL.ObjectProperty
    ranges = [o for o in g.objects(p, RDFS.range) if isinstance(o, URIRef)]
    return Suggestion(f.rule, t.iri, "D", "Wrong kind of range", f.message,
                      options=[Option("Remove the range", remove=[n3((p, RDFS.range, r)) for r in ranges],
                                      confidence="medium", reason="Keeps the property type; add the right range later."),
                               Option(f"Make it {'an object' if new_kind == OWL.ObjectProperty else 'a datatype'} property",
                                      remove=[n3((p, RDF.type, old_kind))], add=[n3((p, RDF.type, new_kind))],
                                      confidence="low", reason="Changes every statement that uses the property.")],
                      made_by=made_by(f.rule))


# ---------------------------------------------------------------- ranked candidates (lexical, until OntoAligner)
def _rank(onto, t, pool) -> list[tuple[float, object]]:
    from difflib import SequenceMatcher
    words = set(re.findall(r"[a-z]{3,}", t.label.lower()))
    scored = []
    for c in pool:
        if c.iri == t.iri:
            continue
        cw = set(re.findall(r"[a-z]{3,}", c.label.lower()))
        overlap = len(words & cw) / (len(cw) or 1)
        ratio = SequenceMatcher(None, t.label.lower(), c.label.lower()).ratio()
        score = 0.6 * overlap + 0.4 * ratio
        if score > 0.25:
            scored.append((round(score, 2), c))
    return sorted(scored, key=lambda x: -x[0])[:3]


@fixer("OB023")
def orphan(f, g, onto):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    pool = [c for c in onto.terms.values() if c.kind == "class" and not c.imported]
    ranked = _rank(onto, t, pool)
    if not ranked:
        return None
    s_ = URIRef(t.iri)
    return Suggestion(f.rule, t.iri, "A", "Orphan class: pick a parent",
                      f"“{t.label}” is not connected to anything. Candidates ranked by label similarity.",
                      options=[Option(f"Under “{c.label}” ({sc})", add=[n3((s_, RDFS.subClassOf, URIRef(c.iri)))],
                                      confidence="medium" if sc > 0.5 else "low", reason="Similar names.")
                               for sc, c in ranked], flags=["guess"], made_by=made_by(f.rule) | {"method": "lexical"})


@fixer("OB018")
def successor(f, g, onto):
    t = onto.terms.get(f.subject)
    if t is None:
        return None
    pool = [c for c in onto.terms.values() if c.kind == t.kind and not c.deprecated and not c.imported]
    ranked = _rank(onto, t, pool)
    if not ranked:
        return None
    return Suggestion(f.rule, t.iri, "A", "Deprecated term: pick its replacement",
                      f"“{t.label}” is deprecated without a replacement.",
                      options=[Option(f"Replaced by “{c.label}” ({sc})",
                                      add=[n3((URIRef(t.iri), DCTERMS.isReplacedBy, URIRef(c.iri)))],
                                      confidence="medium" if sc > 0.5 else "low", reason="Similar names.")
                               for sc, c in ranked], flags=["guess"], made_by=made_by(f.rule) | {"method": "lexical"})


# ---------------------------------------------------------------- manual (M): evidence, no edit
MANUAL = {
    "OB020": "Remove either the subClassOf or the disjointness axiom; which one depends on what you meant.",
    "OB021": "Remove one characteristic: in OWL 2 DL a transitive property cannot be (inverse) functional.",
    "OB027": "Informational: the term is documented as external. Nothing to edit.",
}
for _code, _how in MANUAL.items():
    FIXERS[_code] = (lambda how: lambda f, g, onto: Suggestion(
        f.rule, f.subject, "M", f.title, f"{f.message} {how}", made_by=made_by(f.rule)))(_how)


# ---------------------------------------------------------------- scans that are not built-in rules
def text_scans(g, onto) -> list[Suggestion]:
    """FX001 extra whitespace and FX002 lowercase definitions (as ROBOT's label_whitespace,
    annotation_whitespace and lowercase_definition), found directly in the graph."""
    own = {t.iri for t in onto.terms.values() if not t.imported and not t.external}
    if onto.metadata.iri:
        own.add(onto.metadata.iri)
    out = []
    for s, p, o in g:
        if str(s) not in own or p not in TEXT_PROPS or not isinstance(o, Literal) or not isinstance(o.value, str):
            continue
        text = str(o)
        clean = re.sub(r"\s+", " ", text).strip()
        if clean != text and "\n" not in text.strip():
            new = Literal(clean, lang=o.language, datatype=o.datatype)
            out.append(Suggestion("FX001", str(s), "D", "Extra spaces",
                                  f"“{text}” → “{clean}”.", options=[Option("Trim spaces", remove=[n3((s, p, o))],
                                                                         add=[n3((s, p, new))])],
                                  flags=["safe"], made_by=made_by("FX001")))
        elif p in DEF_PROPS and clean[:1].islower():
            new = Literal(clean[0].upper() + clean[1:], lang=o.language, datatype=o.datatype)
            out.append(Suggestion("FX002", str(s), "D", "Definition starts lowercase",
                                  f"“{clean[:60]}…” → capitalised.", options=[Option(
                                      "Capitalise", remove=[n3((s, p, o))], add=[n3((s, p, new))])],
                                  flags=["safe"], made_by=made_by("FX002")))
    return out


__all__ = ["FIXERS", "REQUIRED", "creator_text", "parse_creators", "license_choices", "missing_values", "ontology_node", "readable",
           "resolve_fields", "text_scans"]
