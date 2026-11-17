"""LinkML schema support.

A LinkML YAML schema is translated into an OWL/RDFS graph, which then goes through the
normal ontoreview pipeline (extraction, checks, diff, serializations, theming). The
documentation is ontoreview's own; this module does not reproduce ``linkml gen-doc``.

Mapping summary
---------------
* schema            -> owl:Ontology (id, title, description, version, license, creators, ...)
* class             -> owl:Class; ``is_a``/``mixins`` -> rdfs:subClassOf; slot usage -> restrictions
* slot / attribute  -> owl:ObjectProperty (class/enum range) or owl:DatatypeProperty (type range)
* enum              -> owl:Class equivalent to ``{pv1, pv2, ...}``; values -> owl:NamedIndividual
* type              -> rdfs:Datatype (built-in LinkML types map to XSD)
* mappings          -> skos:exactMatch / closeMatch / relatedMatch / narrowMatch / broadMatch
* LinkML-only facets (required, multivalued, identifier, abstract, mixin, pattern, ...) are kept
  as annotations in the ``linkml:`` namespace, so nothing is lost in the documentation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from .vocab import BIBO, SCHEMA, VANN

log = logging.getLogger(__name__)

LINKML = Namespace("https://w3id.org/linkml/")

BUILTIN_TYPES: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "boolean": XSD.boolean,
    "float": XSD.float,
    "double": XSD.double,
    "decimal": XSD.decimal,
    "time": XSD.time,
    "date": XSD.date,
    "datetime": XSD.dateTime,
    "date_or_datetime": XSD.string,
    "uriorcurie": XSD.anyURI,
    "uri": XSD.anyURI,
    "curie": XSD.string,
    "ncname": XSD.string,
    "objectidentifier": XSD.anyURI,
    "nodeidentifier": XSD.anyURI,
    "jsonpointer": XSD.string,
    "jsonpath": XSD.string,
    "sparqlpath": XSD.string,
}

LICENSE_SHORTCUTS = {
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "cc by 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "mit": "https://opensource.org/licenses/MIT",
    "apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0",
    "bsd-3-clause": "https://opensource.org/licenses/BSD-3-Clause",
}

MAPPING_PROPS = {
    "exact_mappings": SKOS.exactMatch,
    "close_mappings": SKOS.closeMatch,
    "related_mappings": SKOS.relatedMatch,
    "narrow_mappings": SKOS.narrowMatch,
    "broad_mappings": SKOS.broadMatch,
}

CHARACTERISTIC_FLAGS = {
    "symmetric": OWL.SymmetricProperty,
    "asymmetric": OWL.AsymmetricProperty,
    "transitive": OWL.TransitiveProperty,
    "reflexive": OWL.ReflexiveProperty,
    "irreflexive": OWL.IrreflexiveProperty,
    "locally_reflexive": OWL.ReflexiveProperty,
}


def is_linkml_file(path: Path) -> bool:
    if path.suffix.lower() not in {".yaml", ".yml"}:
        return False
    try:
        head = path.read_text("utf-8")[:20000]
    except OSError:
        return False
    return bool(re.search(r"^(classes|slots|enums|types|default_prefix)\s*:", head, re.M)) and bool(
        re.search(r"^id\s*:", head, re.M)
    )


def _camel(name: str) -> str:
    parts = re.split(r"[\s_\-]+", name.strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _underscore(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", name.strip())


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


class _Converter:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.g = Graph(bind_namespaces="core")
        self.prefixes: dict[str, str] = {
            "linkml": str(LINKML),
            "xsd": str(XSD),
            "rdf": str(RDF),
            "rdfs": str(RDFS),
            "owl": str(OWL),
            "skos": str(SKOS),
            "schema": "http://schema.org/",
            "dcterms": str(DCTERMS),
        }
        self.classes: dict[str, dict] = {}
        self.slots: dict[str, dict] = {}
        self.enums: dict[str, dict] = {}
        self.types: dict[str, dict] = {}
        self.element_schema: dict[str, str] = {}  # element name -> defining schema id
        self.default_prefix_uri = ""
        self.default_range = "string"
        self.seen: set[Path] = set()

    # -- loading ---------------------------------------------------------------
    def load(self, path: Path, top: bool) -> dict:
        path = path.resolve()
        if path in self.seen:
            return {}
        self.seen.add(path)
        schema = yaml.safe_load(path.read_text("utf-8")) or {}
        for p, v in (schema.get("prefixes") or {}).items():
            uri = v.get("prefix_reference") if isinstance(v, dict) else v
            if uri:
                self.prefixes.setdefault(p, str(uri))
        sid = str(schema.get("id", path.stem))
        if top:
            dp = schema.get("default_prefix")
            if dp and dp in self.prefixes:
                self.default_prefix_uri = self.prefixes[dp]
            elif dp and ("://" in str(dp)):
                self.default_prefix_uri = str(dp)
            else:
                self.default_prefix_uri = sid.rstrip("/#") + "/"
            self.default_range = schema.get("default_range", "string")
        for imp in _as_list(schema.get("imports")):
            imp = str(imp)
            if imp.startswith("linkml:"):
                continue
            candidate = None
            for ext in ("", ".yaml", ".yml"):
                p = (path.parent / f"{imp}{ext}")
                if p.is_file():
                    candidate = p
                    break
            if candidate is None:
                log.warning("LinkML import %r could not be resolved locally; skipped", imp)
                continue
            self.load(candidate, top=False)
        for kind, store in (
            ("classes", self.classes),
            ("slots", self.slots),
            ("enums", self.enums),
            ("types", self.types),
        ):
            for name, body in (schema.get(kind) or {}).items():
                body = dict(body or {})
                body.setdefault("_schema", sid)
                if name in store:
                    store[name].update({k: v for k, v in body.items() if v is not None})
                else:
                    store[name] = body
                self.element_schema[name] = sid
        # attributes are class-scoped slots
        for cname, cbody in (schema.get("classes") or {}).items():
            for aname, abody in ((cbody or {}).get("attributes") or {}).items():
                abody = dict(abody or {})
                abody.setdefault("_schema", sid)
                abody.setdefault("_owner", cname)
                if aname not in self.slots:
                    self.slots[aname] = abody
                else:
                    for k, v in abody.items():
                        self.slots[aname].setdefault(k, v)
        return schema

    # -- IRIs --------------------------------------------------------------------
    def expand(self, curie_or_uri: str) -> URIRef:
        s = str(curie_or_uri)
        if "://" in s or s.startswith("urn:"):
            return URIRef(s)
        if ":" in s:
            p, local = s.split(":", 1)
            if p in self.prefixes:
                return URIRef(self.prefixes[p] + local)
        return URIRef(self.default_prefix_uri + s)

    def class_iri(self, name: str) -> URIRef:
        body = self.classes.get(name, {})
        if body.get("class_uri"):
            return self.expand(body["class_uri"])
        return URIRef(self.default_prefix_uri + _camel(name))

    def slot_iri(self, name: str) -> URIRef:
        body = self.slots.get(name, {})
        if body.get("slot_uri"):
            return self.expand(body["slot_uri"])
        return URIRef(self.default_prefix_uri + _underscore(name))

    def enum_iri(self, name: str) -> URIRef:
        body = self.enums.get(name, {})
        if body.get("enum_uri"):
            return self.expand(body["enum_uri"])
        return URIRef(self.default_prefix_uri + _camel(name))

    def type_iri(self, name: str) -> URIRef:
        if name in BUILTIN_TYPES:
            return BUILTIN_TYPES[name]
        body = self.types.get(name, {})
        if body.get("uri") and not body.get("typeof"):
            return self.expand(body["uri"])
        return URIRef(self.default_prefix_uri + _camel(name))

    def range_iri(self, rng: str | None) -> tuple[URIRef, str]:
        rng = rng or self.default_range
        if rng in self.classes:
            return self.class_iri(rng), "class"
        if rng in self.enums:
            return self.enum_iri(rng), "enum"
        if rng in self.types or rng in BUILTIN_TYPES:
            return self.type_iri(rng), "type"
        if rng in ("Any", "linkml:Any"):
            return OWL.Thing, "class"
        return self.expand(rng), "class"

    # -- common element metadata -------------------------------------------------
    def common(self, iri: URIRef, name: str, body: dict) -> None:
        g = self.g
        g.add((iri, RDFS.label, Literal(body.get("title") or name)))
        if body.get("description"):
            g.add((iri, SKOS.definition, Literal(str(body["description"]).strip())))
        for c in _as_list(body.get("comments")):
            g.add((iri, RDFS.comment, Literal(str(c))))
        for a in _as_list(body.get("aliases")):
            g.add((iri, SKOS.altLabel, Literal(str(a))))
        for n in _as_list(body.get("notes")):
            g.add((iri, SKOS.note, Literal(str(n))))
        for t in _as_list(body.get("todos")):
            g.add((iri, SKOS.editorialNote, Literal(f"TODO: {t}")))
        for ex in _as_list(body.get("examples")):
            if isinstance(ex, dict):
                val = ex.get("value") or ex.get("object")
                desc = ex.get("description")
                text = f"{val} — {desc}" if val and desc else (val or desc)
                if text:
                    g.add((iri, SKOS.example, Literal(str(text))))
            else:
                g.add((iri, SKOS.example, Literal(str(ex))))
        for s in _as_list(body.get("see_also")):
            g.add((iri, RDFS.seeAlso, self.expand(str(s)) if ":" in str(s) else Literal(str(s))))
        for key, pred in MAPPING_PROPS.items():
            for m in _as_list(body.get(key)):
                g.add((iri, pred, self.expand(str(m))))
        if body.get("deprecated"):
            g.add((iri, OWL.deprecated, Literal(True)))
            if isinstance(body["deprecated"], str):
                g.add((iri, SKOS.historyNote, Literal(body["deprecated"])))
        repl = body.get("deprecated_element_has_exact_replacement")
        if repl:
            g.add((iri, DCTERMS.isReplacedBy, self.expand(str(repl))))
        if body.get("status"):
            g.add((iri, BIBO.status, Literal(str(body["status"]))))
        if body.get("_schema"):
            g.add((iri, RDFS.isDefinedBy, URIRef(body["_schema"])))
        for key in ("rank",):
            if body.get(key) is not None:
                g.add((iri, LINKML[key], Literal(body[key])))

    # -- emit ----------------------------------------------------------------------
    def emit(self, schema: dict) -> Graph:
        g = self.g
        for p, uri in self.prefixes.items():
            try:
                g.bind(p, uri, override=True, replace=True)
            except Exception:  # pragma: no cover - invalid prefix
                pass
        onto = URIRef(str(schema.get("id", self.default_prefix_uri)))
        self.emit_schema(onto, schema)
        for name, body in self.types.items():
            self.emit_type(name, body)
        for name, body in self.enums.items():
            self.emit_enum(name, body)
        for name, body in self.slots.items():
            self.emit_slot(name, body)
        for name, body in self.classes.items():
            self.emit_class(name, body)
        return g

    def emit_schema(self, onto: URIRef, s: dict) -> None:
        g = self.g
        g.add((onto, RDF.type, OWL.Ontology))
        g.add((onto, DCTERMS.title, Literal(s.get("title") or s.get("name") or str(onto))))
        if s.get("description"):
            g.add((onto, DCTERMS.description, Literal(str(s["description"]).strip())))
        if s.get("version"):
            g.add((onto, OWL.versionInfo, Literal(str(s["version"]))))
        lic = s.get("license")
        if lic:
            lic_s = str(lic)
            url = LICENSE_SHORTCUTS.get(lic_s.lower(), lic_s)
            g.add((onto, DCTERMS.license, URIRef(url) if "://" in url else Literal(url)))
        for key, pred in (("created_by", DCTERMS.creator), ("contributors", DCTERMS.contributor)):
            for who in _as_list(s.get(key)):
                who = str(who)
                if ":" in who and not who.startswith("http") and who.split(":", 1)[0] in self.prefixes:
                    g.add((onto, pred, self.expand(who)))
                elif who.startswith("http"):
                    g.add((onto, pred, URIRef(who)))
                else:
                    g.add((onto, pred, Literal(who)))
        if s.get("created_on"):
            g.add((onto, DCTERMS.created, Literal(str(s["created_on"]))))
        if s.get("last_updated_on"):
            g.add((onto, DCTERMS.modified, Literal(str(s["last_updated_on"]))))
        for kw in _as_list(s.get("keywords")):
            g.add((onto, SCHEMA.keywords, Literal(str(kw))))
        for sa in _as_list(s.get("see_also")):
            g.add((onto, RDFS.seeAlso, URIRef(self.expand(str(sa)))))
        if s.get("source"):
            g.add((onto, DCTERMS.source, URIRef(self.expand(str(s["source"])))))
        if s.get("status"):
            g.add((onto, BIBO.status, Literal(str(s["status"]))))
        dp = s.get("default_prefix")
        if dp and dp in self.prefixes:
            g.add((onto, VANN.preferredNamespacePrefix, Literal(dp)))
        g.add((onto, VANN.preferredNamespaceUri, Literal(self.default_prefix_uri)))
        g.add((onto, LINKML.generation_source, Literal("LinkML schema")))

    def emit_type(self, name: str, body: dict) -> None:
        if name in BUILTIN_TYPES:
            return
        iri = self.type_iri(name)
        if str(iri).startswith(str(XSD)):
            return
        g = self.g
        g.add((iri, RDF.type, RDFS.Datatype))
        self.common(iri, name, body)
        base = body.get("typeof")
        if base:
            base_iri = self.type_iri(base)
            facets = self._facets(body)
            if facets:
                g.add((iri, OWL.equivalentClass, self._restricted_datatype(base_iri, facets)))
            else:
                g.add((iri, OWL.equivalentClass, base_iri))
        elif body.get("uri"):
            g.add((iri, OWL.equivalentClass, self.expand(body["uri"])))
        if body.get("base"):
            g.add((iri, LINKML.base, Literal(str(body["base"]))))

    def emit_enum(self, name: str, body: dict) -> None:
        g = self.g
        iri = self.enum_iri(name)
        g.add((iri, RDF.type, OWL.Class))
        g.add((iri, LINKML.kind, Literal("enum")))
        self.common(iri, name, body)
        members: list[URIRef] = []
        for text, pv in (body.get("permissible_values") or {}).items():
            pv = pv or {}
            if pv.get("meaning"):
                piri = self.expand(str(pv["meaning"]))
            else:
                piri = URIRef(f"{iri}#{quote(str(text), safe='')}")
            members.append(piri)
            g.add((piri, RDF.type, OWL.NamedIndividual))
            g.add((piri, RDF.type, iri))
            g.add((piri, RDFS.label, Literal(pv.get("title") or str(text))))
            g.add((piri, LINKML.permissible_value, Literal(str(text))))
            if pv.get("description"):
                g.add((piri, SKOS.definition, Literal(str(pv["description"]))))
            for key, pred in MAPPING_PROPS.items():
                for m in _as_list(pv.get(key)):
                    g.add((piri, pred, self.expand(str(m))))
        if members:
            lst = BNode()
            Collection(g, lst, members)
            eq = BNode()
            g.add((eq, RDF.type, OWL.Class))
            g.add((eq, OWL.oneOf, lst))
            g.add((iri, OWL.equivalentClass, eq))

    def _facets(self, body: dict) -> list[tuple[URIRef, Literal]]:
        out = []
        if body.get("pattern"):
            out.append((XSD.pattern, Literal(str(body["pattern"]))))
        if body.get("minimum_value") is not None:
            out.append((XSD.minInclusive, Literal(body["minimum_value"])))
        if body.get("maximum_value") is not None:
            out.append((XSD.maxInclusive, Literal(body["maximum_value"])))
        return out

    def _restricted_datatype(self, base: URIRef, facets: list[tuple[URIRef, Literal]]) -> BNode:
        g = self.g
        dt = BNode()
        g.add((dt, RDF.type, RDFS.Datatype))
        g.add((dt, OWL.onDatatype, base))
        items = []
        for pred, val in facets:
            f = BNode()
            g.add((f, pred, val))
            items.append(f)
        lst = BNode()
        Collection(g, lst, items)
        g.add((dt, OWL.withRestrictions, lst))
        return dt

    def _slot_range_node(self, body: dict):
        rng_name = body.get("range")
        any_of = [a.get("range") for a in _as_list(body.get("any_of")) if isinstance(a, dict)]
        if any_of and not rng_name:
            iris = [self.range_iri(r) for r in any_of if r]
            kinds = {k for _, k in iris}
            u = BNode()
            members = [i for i, _ in iris]
            lst = BNode()
            Collection(self.g, lst, members)
            if kinds == {"type"}:
                self.g.add((u, RDF.type, RDFS.Datatype))
            else:
                self.g.add((u, RDF.type, OWL.Class))
            self.g.add((u, OWL.unionOf, lst))
            return u, ("type" if kinds == {"type"} else "class")
        rng, kind = self.range_iri(rng_name)
        if kind == "type":
            facets = self._facets(body)
            if facets:
                return self._restricted_datatype(rng, facets), kind
        return rng, kind

    def emit_slot(self, name: str, body: dict) -> None:
        g = self.g
        iri = self.slot_iri(name)
        rng, kind = self._slot_range_node(body)
        g.add((iri, RDF.type, OWL.DatatypeProperty if kind == "type" else OWL.ObjectProperty))
        self.common(iri, name, body)
        g.add((iri, RDFS.range, rng))
        if body.get("domain"):
            g.add((iri, RDFS.domain, self.class_iri(body["domain"])))
        for parent in _as_list(body.get("is_a")) + _as_list(body.get("mixins")):
            if parent in self.slots:
                g.add((iri, RDFS.subPropertyOf, self.slot_iri(parent)))
        if body.get("subproperty_of"):
            g.add((iri, RDFS.subPropertyOf, self.expand(str(body["subproperty_of"]))))
        if body.get("inverse") and kind != "type":
            inv = body["inverse"]
            g.add((iri, OWL.inverseOf, self.slot_iri(inv) if inv in self.slots else self.expand(inv)))
        for flag, cls in CHARACTERISTIC_FLAGS.items():
            if body.get(flag) and kind != "type":
                g.add((iri, RDF.type, cls))
        if body.get("identifier"):
            g.add((iri, RDF.type, OWL.FunctionalProperty))
            if kind != "type":
                g.add((iri, RDF.type, OWL.InverseFunctionalProperty))
        for flag in ("required", "recommended", "multivalued", "identifier", "key", "inlined",
                     "inlined_as_list", "designates_type", "ifabsent", "pattern",
                     "minimum_value", "maximum_value", "unit"):
            v = body.get(flag)
            if v is not None and v is not False:
                if isinstance(v, dict):
                    v = ", ".join(f"{k}={val}" for k, val in v.items())
                g.add((iri, LINKML[flag], Literal(v)))
        if body.get("_owner"):
            g.add((iri, LINKML.attribute_of, self.class_iri(body["_owner"])))

    def emit_class(self, name: str, body: dict) -> None:
        g = self.g
        iri = self.class_iri(name)
        g.add((iri, RDF.type, OWL.Class))
        self.common(iri, name, body)
        if body.get("is_a"):
            g.add((iri, RDFS.subClassOf, self.class_iri(body["is_a"])))
        for m in _as_list(body.get("mixins")):
            g.add((iri, RDFS.subClassOf, self.class_iri(m)))
            g.add((iri, LINKML.mixins, self.class_iri(m)))
        for flag in ("abstract", "mixin", "tree_root"):
            if body.get(flag):
                g.add((iri, LINKML[flag], Literal(True)))
        union = [self.class_iri(u) for u in _as_list(body.get("union_of"))]
        if union:
            lst = BNode()
            Collection(g, lst, union)
            u = BNode()
            g.add((u, RDF.type, OWL.Class))
            g.add((u, OWL.unionOf, lst))
            g.add((iri, OWL.equivalentClass, u))
        for d in _as_list(body.get("disjoint_with")):
            g.add((iri, OWL.disjointWith, self.class_iri(d)))

        slot_names = list(_as_list(body.get("slots")))
        slot_names += [a for a in (body.get("attributes") or {}) if a not in slot_names]
        usage = body.get("slot_usage") or {}
        slot_names += [s for s in usage if s not in slot_names]
        for sname in slot_names:
            base = dict(self.slots.get(sname, {}))
            base.update({k: v for k, v in (usage.get(sname) or {}).items() if v is not None})
            if (body.get("attributes") or {}).get(sname):
                base.update({k: v for k, v in body["attributes"][sname].items() if v is not None})
            self._restrict(iri, sname, base)

    def _restrict(self, cls: URIRef, sname: str, body: dict) -> None:
        g = self.g
        prop = self.slot_iri(sname)
        rng, kind = self._slot_range_node(body)
        required = bool(body.get("required") or body.get("identifier"))
        multivalued = bool(body.get("multivalued"))
        on_key = OWL.onDataRange if kind == "type" else OWL.onClass

        def restriction(**pairs) -> BNode:
            r = BNode()
            g.add((r, RDF.type, OWL.Restriction))
            g.add((r, OWL.onProperty, prop))
            for p, o in pairs.items():
                g.add((r, getattr(OWL, p) if p != "on" else on_key, o))
            return r

        if required and not multivalued:
            r = restriction(qualifiedCardinality=Literal(1, datatype=XSD.nonNegativeInteger), on=rng)
            g.add((cls, RDFS.subClassOf, r))
        else:
            if required:
                g.add((cls, RDFS.subClassOf, restriction(someValuesFrom=rng)))
            if not multivalued:
                g.add((cls, RDFS.subClassOf,
                       restriction(maxQualifiedCardinality=Literal(1, datatype=XSD.nonNegativeInteger), on=rng)))
            else:
                g.add((cls, RDFS.subClassOf, restriction(allValuesFrom=rng)))
        g.add((prop, LINKML.domain_of, cls))


def linkml_to_graph(path: str | Path) -> Graph:
    """Convert a LinkML YAML schema (with local imports) into an OWL graph."""
    path = Path(path)
    conv = _Converter(path.parent)
    schema = conv.load(path, top=True)
    return conv.emit(schema)
