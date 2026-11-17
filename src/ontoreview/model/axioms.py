"""Render OWL class/data-range expressions as Manchester-syntax token lists."""

from __future__ import annotations

from collections.abc import Callable

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, XSD

from .entities import Expr, Ref

FACET_SYMBOLS = {
    XSD.minInclusive: ">=",
    XSD.maxInclusive: "<=",
    XSD.minExclusive: ">",
    XSD.maxExclusive: "<",
    XSD.length: "length",
    XSD.minLength: "minLength",
    XSD.maxLength: "maxLength",
    XSD.pattern: "pattern",
}

CARDINALITIES = [
    (OWL.cardinality, "exactly", False),
    (OWL.minCardinality, "min", False),
    (OWL.maxCardinality, "max", False),
    (OWL.qualifiedCardinality, "exactly", True),
    (OWL.minQualifiedCardinality, "min", True),
    (OWL.maxQualifiedCardinality, "max", True),
]


def literal_text(lit: Literal, short: Callable[[str], str] | None = None) -> str:
    text = str(lit)
    if lit.language:
        return f'"{text}"@{lit.language}'
    if lit.datatype and lit.datatype not in (XSD.string,):
        dt = short(str(lit.datatype)) if short else str(lit.datatype)
        if lit.datatype in (XSD.integer, XSD.nonNegativeInteger, XSD.decimal, XSD.boolean,
                            XSD.double, XSD.float, XSD.int):
            return text
        return f'"{text}"^^{dt}'
    return f'"{text}"'


class ExpressionRenderer:
    def __init__(self, graph: Graph, ref: Callable[[URIRef], Ref], short: Callable[[str], str]):
        self.g = graph
        self.ref = ref
        self.short = short

    def _list(self, node) -> list:
        try:
            return list(Collection(self.g, node))
        except Exception:  # noqa: BLE001
            return []

    def render(self, node, depth: int = 0) -> Expr:
        if depth > 25:
            return [("punct", "…")]
        if isinstance(node, URIRef):
            return [("ref", self.ref(node))]
        if isinstance(node, Literal):
            return [("lit", literal_text(node, self.short))]
        if not isinstance(node, BNode):
            return [("lit", str(node))]
        g = self.g
        out: Expr = []

        # Boolean class constructors
        for pred, kw in ((OWL.intersectionOf, "and"), (OWL.unionOf, "or")):
            lst = g.value(node, pred)
            if lst is not None:
                return self._join(self._list(lst), kw, depth)
        comp = g.value(node, OWL.complementOf) or g.value(node, OWL.datatypeComplementOf)
        if comp is not None:
            return [("kw", "not"), ("punct", " ")] + self._wrap(comp, depth)
        one_of = g.value(node, OWL.oneOf)
        if one_of is not None:
            out.append(("punct", "{"))
            for i, item in enumerate(self._list(one_of)):
                if i:
                    out.append(("punct", ", "))
                out.extend(self.render(item, depth + 1))
            out.append(("punct", "}"))
            return out

        # Datatype restriction: xsd:int[>= 0, <= 10]
        on_dt = g.value(node, OWL.onDatatype)
        if on_dt is not None:
            out.extend(self.render(on_dt, depth + 1))
            out.append(("punct", "["))
            facets = self._list(g.value(node, OWL.withRestrictions))
            for i, f in enumerate(facets):
                if i:
                    out.append(("punct", ", "))
                for p, o in g.predicate_objects(f):
                    sym = FACET_SYMBOLS.get(p, self.short(str(p)))
                    out.append(("kw", sym))
                    out.append(("punct", " "))
                    out.append(("lit", literal_text(o, self.short) if isinstance(o, Literal) else str(o)))
            out.append(("punct", "]"))
            return out

        # Inverse property expression
        inv = g.value(node, OWL.inverseOf)
        if inv is not None and (node, RDF.type, OWL.Restriction) not in g:
            return [("kw", "inverse"), ("punct", " (")] + self.render(inv, depth + 1) + [("punct", ")")]

        # Restrictions
        prop = g.value(node, OWL.onProperty)
        if prop is None:
            props = g.value(node, OWL.onProperties)
            if props is not None:
                plist = self._list(props)
                prop = plist[0] if plist else None
        if prop is not None:
            p_expr = self.render(prop, depth + 1)
            for pred, kw in ((OWL.someValuesFrom, "some"), (OWL.allValuesFrom, "only")):
                filler = g.value(node, pred)
                if filler is not None:
                    return p_expr + [("punct", " "), ("kw", kw), ("punct", " ")] + self._wrap(filler, depth)
            hv = g.value(node, OWL.hasValue)
            if hv is not None:
                return p_expr + [("punct", " "), ("kw", "value"), ("punct", " ")] + self.render(hv, depth + 1)
            if g.value(node, OWL.hasSelf) is not None:
                return p_expr + [("punct", " "), ("kw", "Self")]
            for pred, kw, qualified in CARDINALITIES:
                n = g.value(node, pred)
                if n is not None:
                    expr = p_expr + [("punct", " "), ("kw", kw), ("punct", " "), ("lit", str(n))]
                    if qualified:
                        filler = g.value(node, OWL.onClass) or g.value(node, OWL.onDataRange)
                        if filler is not None:
                            expr += [("punct", " ")] + self._wrap(filler, depth)
                    return expr
            return p_expr + [("punct", " "), ("kw", "(restriction)")]

        # Unknown blank node: show its label-ish content
        return [("lit", "[anonymous]")]

    def _wrap(self, node, depth: int) -> Expr:
        inner = self.render(node, depth + 1)
        if isinstance(node, BNode) and any(t == ("kw", "and") or t == ("kw", "or") or t == ("kw", "some")
                                            or t == ("kw", "only") for t in inner):
            return [("punct", "(")] + inner + [("punct", ")")]
        return inner

    def _join(self, items: list, kw: str, depth: int) -> Expr:
        out: Expr = []
        for i, item in enumerate(items):
            if i:
                out += [("punct", " "), ("kw", kw), ("punct", " ")]
            out += self._wrap(item, depth)
        return out

    def chain(self, node) -> Expr:
        out: Expr = []
        for i, p in enumerate(self._list(node)):
            if i:
                out += [("punct", " "), ("kw", "o"), ("punct", " ")]
            out += self.render(p, 1)
        return out


def expr_text(expr: Expr) -> str:
    """Plain-text rendering (used for diffs, search and Markdown export)."""
    parts = []
    for kind, val in expr:
        if kind == "ref":
            parts.append(val.curie or val.label)
        else:
            parts.append(str(val))
    return "".join(parts)


def expr_refs(expr: Expr) -> list[Ref]:
    return [v for k, v in expr if k == "ref"]
