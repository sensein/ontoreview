"""Data embedded into the generated site: search index, graph and JSON-LD."""

from __future__ import annotations

import json
import re

from ..model.axioms import expr_refs
from ..model.entities import Ontology

_TAG = re.compile(r"<[^>]+>")


def search_index(onto: Ontology, href) -> list[dict]:
    docs = []
    for t in onto.terms.values():
        docs.append({
            "id": t.iri,
            "label": t.label,
            "curie": t.curie or "",
            "alt": " ".join(t.alt_labels),
            "def": _TAG.sub("", (t.definition or ""))[:300],
            "kind": t.kind_label,
            "badge": t.badge,
            "href": href(t.ref()),
            "dep": t.deprecated,
        })
    docs.sort(key=lambda d: d["label"].lower())
    return docs


def graph_data(onto: Ontology, href, max_nodes: int = 600) -> dict:
    """Cytoscape elements.

    Nodes are classes (and SKOS concepts). Edges:
    * ``sub``  superclass -> subclass (asserted rdfs:subClassOf / skos:broader)
    * ``eq``   named class in an equivalence definition -> defined class (dotted)
    * ``prop`` object property from domain to range, taken from rdfs:domain/rdfs:range and from
      restrictions such as ``hasBase some PizzaBase``
    Datatype properties are attached to their domain class as ``attrs`` (shown inside the box).
    """
    from ..model.axioms import expr_text

    classes = [t for t in onto.terms.values() if t.kind in ("class", "concept")][:max_nodes]
    ids = {t.iri for t in classes}
    nodes, edges = [], []
    seen: set[str] = set()
    external: dict[str, dict] = {}
    attrs: dict[str, list[str]] = {i: [] for i in ids}
    dprops: dict[str, list[dict]] = {i: [] for i in ids}

    def add_edge(eid: str, data: dict) -> None:
        if eid in seen:
            return
        seen.add(eid)
        edges.append({"data": {"id": eid, **data}})

    for t in classes:
        for sup in t.superclasses + t.broader:
            if sup.iri not in ids:
                if len(external) >= 100:
                    continue
                external.setdefault(sup.iri, {"data": {"id": sup.iri, "label": sup.label, "href": sup.iri,
                                                       "kind": "external", "ext": True}})
            add_edge(f"s|{t.iri}|{sup.iri}", {"source": sup.iri, "target": t.iri, "type": "sub"})
        for e in t.equivalent:
            for r in _top_level_classes(e):
                if r.iri in ids and r.iri != t.iri and onto.terms[r.iri].kind == "class":
                    add_edge(f"e|{t.iri}|{r.iri}", {"source": r.iri, "target": t.iri, "type": "eq"})
        # superclass restrictions: <property> <quantifier> <filler>
        for e in t.restrictions:
            if any(k == "kw" and v == "not" for k, v in e):
                continue
            refs = expr_refs(e)
            if len(refs) < 2:
                continue
            prop, filler = refs[0], refs[-1]
            pt = onto.terms.get(prop.iri)
            if pt is None or pt.kind not in ("object_property", "datatype_property", "property"):
                continue
            if filler.iri in ids:
                add_edge(f"p|{prop.iri}|{t.iri}|{filler.iri}",
                         {"source": t.iri, "target": filler.iri, "type": "prop", "label": prop.label,
                          "href": href(prop), "prop": prop.iri, "inv": _inverse(pt)})
            elif pt.kind == "datatype_property":
                line = f"{prop.label} : {filler.label}"
                if line not in attrs[t.iri]:
                    attrs[t.iri].append(line)
                    dprops[t.iri].append({"l": prop.label, "r": filler.label, "h": href(prop)})

    for p in onto.terms.values():
        if p.kind not in ("object_property", "datatype_property", "property"):
            continue
        doms = [r.iri for e in p.domain for r in expr_refs(e) if r.iri in ids]
        if p.kind == "datatype_property":
            rng = ", ".join(expr_text(e) for e in p.range) or "literal"
            for d in doms:
                line = f"{p.label} : {rng.replace('xsd:', '')}"
                if not any(a.startswith(p.label + " :") for a in attrs[d]):
                    attrs[d].append(line)
                    dprops[d].append({"l": p.label, "r": rng.replace("xsd:", "") if p.range else "Literal",
                                      "h": href(p.ref())})
            continue
        rngs = [r.iri for e in p.range for r in expr_refs(e) if r.iri in ids]
        for d in doms:
            for r in rngs:
                add_edge(f"p|{p.iri}|{d}|{r}", {"source": d, "target": r, "type": "prop",
                                                "label": p.label, "href": href(p.ref()),
                                                "prop": p.iri, "inv": _inverse(p)})

    for t in classes:
        a = sorted(attrs[t.iri])[:8]
        nodes.append({"data": {"id": t.iri, "label": t.label, "href": href(t.ref()), "kind": t.kind,
                               "dep": t.deprecated, "ext": t.external, "attrs": "\n".join(a),
                               "dprops": dprops[t.iri][:12], "defined": bool(t.equivalent),
                               "inst": len(t.instances)}})
    total = len([t for t in onto.terms.values() if t.kind == "class"])
    return {"nodes": nodes + list(external.values()), "edges": edges, "truncated": total > max_nodes}


def _inverse(p) -> str | None:
    for e in p.inverse_of:
        refs = expr_refs(e)
        if refs:
            return refs[0].iri
    return None


def _top_level_classes(expr) -> list:
    """Named classes that are direct operands of an equivalence (not inside restrictions/negations)."""
    out, depth, prev_kw = [], 0, None
    tokens = [tok for tok in expr if not (tok[0] == "punct" and tok[1].strip() == "")]
    for i, (kind, val) in enumerate(tokens):
        if kind == "punct":
            depth += val.count("(") + val.count("{") - val.count(")") - val.count("}")
            continue
        if kind == "kw":
            prev_kw = val
            continue
        if kind == "ref" and depth == 0:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            is_property = nxt is not None and nxt[0] == "kw" and nxt[1] not in ("and", "or")
            if not is_property and prev_kw in (None, "and", "or"):
                out.append(val)
        prev_kw = None if kind == "ref" else prev_kw
    return out


def jsonld(onto: Ontology, url: str | None) -> str:
    m = onto.metadata
    doc: dict = {
        "@context": "https://schema.org/",
        "@type": "DefinedTermSet",
        "@id": m.iri or url,
        "name": m.title,
        "description": m.abstract or m.description,
        "url": url or m.iri,
        "version": m.version_info,
        "license": m.license,
        "dateModified": m.modified,
        "dateCreated": m.created,
        "datePublished": m.issued,
        "keywords": m.keywords or None,
        "creator": [_person(a) for a in m.creators] or None,
        "contributor": [_person(a) for a in m.contributors] or None,
        "publisher": [_person(a) for a in m.publishers] or None,
        "identifier": m.doi,
        "hasDefinedTerm": [
            {"@type": "DefinedTerm", "@id": t.iri, "name": t.label,
             **({"description": t.definition[:500]} if t.definition else {}),
             **({"termCode": t.curie} if t.curie else {})}
            for t in list(onto.terms.values())[:1000] if not t.imported
        ],
    }
    doc = {k: v for k, v in doc.items() if v not in (None, [], "")}
    return json.dumps(doc, ensure_ascii=False, indent=1).replace("<", "\\u003c")


def _person(a) -> dict:
    d = {"@type": "Person", "name": a.name}
    if a.iri:
        d["@id"] = a.iri
    if a.affiliation:
        d["affiliation"] = {"@type": "Organization", "name": a.affiliation}
    return d
