"""Load ontologies (any RDF syntax or LinkML YAML), optionally resolving owl:imports."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.util import guess_format

from .linkml import is_linkml_file, linkml_to_graph

log = logging.getLogger(__name__)

EXTRA_FORMATS = {
    ".owl": "xml",
    ".rdf": "xml",
    ".jsonld": "json-ld",
    ".json": "json-ld",
    ".ttl": "turtle",
    ".nt": "nt",
    ".n3": "n3",
    ".trig": "trig",
    ".nq": "nquads",
    ".ofn": None,  # functional syntax not supported by rdflib
    ".omn": None,
}


@dataclass
class LoadedOntology:
    graph: Graph  # main ontology only
    full_graph: Graph  # main + imports
    source: str
    source_kind: str = "rdf"  # "rdf" | "linkml"
    imports_loaded: list[str] = field(default_factory=list)


def _parse_rdf(source: str, fmt: str | None) -> Graph:
    g = Graph()
    is_url = source.startswith(("http://", "https://"))
    if fmt is None and not is_url:
        suffix = Path(source).suffix.lower()
        if suffix in EXTRA_FORMATS and EXTRA_FORMATS[suffix] is None:
            raise ValueError(
                f"{suffix} (OWL functional/Manchester syntax) is not supported by rdflib; "
                "convert to Turtle or RDF/XML first (e.g. with ROBOT: robot convert)."
            )
        fmt = EXTRA_FORMATS.get(suffix) or guess_format(source)
    if fmt:
        g.parse(source, format=fmt)
        return g
    # Unknown: try common syntaxes in turn.
    last: Exception | None = None
    for f in ("turtle", "xml", "json-ld", "nt", "n3"):
        try:
            g = Graph()
            g.parse(source, format=f)
            return g
        except Exception as e:  # noqa: BLE001
            last = e
    raise ValueError(f"Could not parse {source!r}: {last}")


def load_source(source: str | Path, fmt: str | None = None) -> tuple[Graph, str]:
    source = str(source)
    if fmt == "linkml" or (
        not source.startswith(("http://", "https://")) and is_linkml_file(Path(source))
    ):
        return linkml_to_graph(source), "linkml"
    return _parse_rdf(source, fmt), "rdf"


def parse_catalog(path: Path) -> dict[str, str]:
    """Read a Protégé ``catalog-v001.xml`` into an IRI -> local file mapping."""
    out: dict[str, str] = {}
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as e:
        log.warning("Could not read catalog %s: %s", path, e)
        return out
    for el in tree.iter():
        if el.tag.endswith("uri") and el.get("name") and el.get("uri"):
            target = el.get("uri")
            if not target.startswith(("http://", "https://", "file:")):
                target = str((path.parent / target).resolve())
            out[el.get("name")] = target
    return out


def load_ontology(
    source: str | Path,
    fmt: str | None = None,
    load_imports: bool = False,
    direct_imports_only: bool = False,
    import_map: dict[str, str] | None = None,
    catalog: str | Path | None = None,
) -> LoadedOntology:
    graph, kind = load_source(source, fmt)
    full = Graph(bind_namespaces="none")
    for prefix, ns in graph.namespaces():
        full.bind(prefix, ns, override=True, replace=True)
    full += graph
    loaded: list[str] = []

    if load_imports:
        mapping: dict[str, str] = {}
        cat = Path(catalog) if catalog else None
        if cat is None and not str(source).startswith("http"):
            default_cat = Path(source).parent / "catalog-v001.xml"
            cat = default_cat if default_cat.is_file() else None
        if cat is not None:
            mapping.update(parse_catalog(cat))
        mapping.update(import_map or {})

        queue = [(o, 1) for o in graph.objects(None, OWL.imports)]
        seen: set[str] = set()
        while queue:
            iri, depth = queue.pop(0)
            iri_s = str(iri)
            if iri_s in seen:
                continue
            seen.add(iri_s)
            target = mapping.get(iri_s, iri_s)
            try:
                g_imp, _ = load_source(target)
            except Exception as e:  # noqa: BLE001
                log.warning("Could not load import %s (%s): %s", iri_s, target, e)
                continue
            full += g_imp
            loaded.append(iri_s)
            if not direct_imports_only:
                queue.extend((o, depth + 1) for o in g_imp.objects(None, OWL.imports))

    return LoadedOntology(
        graph=graph, full_graph=full, source=str(source), source_kind=kind, imports_loaded=loaded
    )


def ontology_iri(g: Graph) -> URIRef | None:
    nodes = [s for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)]
    if not nodes:
        return None
    return max(nodes, key=lambda n: (len(list(g.predicate_objects(n))), str(n)))
