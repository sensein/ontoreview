"""OntoCheck metrics (https://ontocheck.readthedocs.io), run in-process on the ontology.

Only runs the metrics and collects their raw results; :mod:`ontoreview.report.ontocheck` turns
them into the review (a metrics table plus findings).

OntoCheck works on Turtle files, so the loaded graph is written to a temporary ``.ttl`` file and
parsed the way OntoCheck parses it. Most of its ``main…`` functions print their results and
return nothing, so the metrics below call OntoCheck's own analysis helpers (the functions those
``main…`` functions use) to get structured results; the remaining metrics call OntoCheck's public
functions. OntoCheck's log messages are collected per metric instead of being printed.

``sparqlEndpoint`` and ``rdfDump`` contact the endpoints / dump URLs declared *in* the ontology
(nothing is uploaded); they can be turned off with ``evaluation.ontocheck_network = false``.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
import warnings
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef
from rdflib.namespace import RDFS, SKOS

from ..report.models import ExternalReport
from ..report.ontocheck import METRICS, ontocheck_report

log = logging.getLogger(__name__)

NETWORK_METRICS = {"sparqlEndpoint", "rdfDump"}
SPELL_SUGGESTIONS = 25          # corrections computed for this many words (the ones shown)
SPARQL_PREDICATES = [URIRef("http://rdfs.org/ns/void#sparqlEndpoint"), URIRef("http://www.w3.org/ns/dcat#accessURL"),
                     URIRef("http://www.w3.org/ns/sparql-service-description#endpoint")]
DUMP_PREDICATES = [URIRef("http://rdfs.org/ns/void#dataDump"), URIRef("http://www.w3.org/ns/dcat#downloadURL"),
                   URIRef("http://www.w3.org/ns/dcat#accessURL"), URIRef("http://xmlns.com/foaf/0.1/homepage")]
DUMP_EXTENSIONS = (".rdf", ".ttl", ".nt", ".n3", ".owl", ".jsonld")
# prefixes OntoCheck binds before analysing (semanticConnection matches cco: / obo:bfo / bfo:)
BINDINGS = {"mds": "https://cwrusdle.bitbucket.io/mds/", "cco": "https://www.commoncoreontologies.org/",
            "obo": "http://purl.obolibrary.org/obo/", "skos": "http://www.w3.org/2004/02/skos/core#"}


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(record.getMessage())
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def _captured():
    """Collect OntoCheck's log messages (and keep them out of OntoReview's console/log)."""
    lg = logging.getLogger("ontocheck")
    h, old_prop, old_level = _Collect(), lg.propagate, lg.level
    lg.addHandler(h)
    lg.propagate = False
    lg.setLevel(logging.INFO)
    try:
        yield h.lines
    finally:
        lg.removeHandler(h)
        lg.propagate, lg.level = old_prop, old_level


def _spell_tokens(text: str) -> list[str]:
    """Words OntoCheck's ``_spell_checker`` checks (same splitting and filtering), without computing a
    correction for every unknown word, which makes it take seconds per few hundred words."""
    text = text.replace("_", " ").replace("-", " ")
    tokens = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|$)|[a-z]+", text)
    return [t for t in tokens if len(t) > 1 and not any(c.isdigit() for c in t)]


def _iris(xs) -> list[str]:
    return sorted({str(x) for x in xs if isinstance(x, URIRef)})


def _logged_list(lines: list[str], start: str, stop: str) -> list[str]:
    """IRIs OntoCheck logged one per line between a ``start`` and a ``stop`` message."""
    out, inside = [], False
    for ln in lines:
        if ln.startswith(start):
            inside = True
            continue
        if inside and ln.startswith(stop):
            break
        if inside and ln.startswith("  ") and ln.strip():
            out.append(ln.strip().lstrip("- ").strip())
    return out


# ------------------------------------------------------------------ the metrics
def _metric_functions(oc, H, g: Graph, ttl: str, source: Path | None, search: str) -> dict[str, Callable[[list[str]], dict]]:  # noqa: N803,C901
    """One callable per OntoCheck metric; each returns a raw result dict (``value`` + ``items``)."""
    classes = H._find_all_named_classes(g)

    def coverage(analyse) -> Callable[[list[str]], dict]:
        def run(_):
            with_, without = analyse(g, classes)
            return {"value": {"total": len(classes), "with": len(with_)}, "items": _iris(without)}
        return run

    def isolated(lines):
        try:
            res = oc.check_for_isolated_elements(ttl)
            nums = {k: next(iter(v)) if isinstance(v, set) else v for k, v in res.items()}
        except ZeroDivisionError:     # OntoCheck divides by the number of classes / properties
            nums = {}
        cls = _logged_list(lines, "Isolated Atomic Classes:", "Number of isolated classes")
        props = _logged_list(lines, "Isolated Properties:", "Number of isolated properties")
        return {"value": {"classes": len(cls), "properties": len(props),
                          "class_ratio": nums.get("Proportion of isolated classes"),
                          "property_ratio": nums.get("Proportion of isolated properties")},
                "items": sorted(set(cls) | set(props))}

    def connections(_):
        return {"value": oc.count_class_connected_components(ttl), "items": []}

    def domain_range(_):
        r = oc.get_properties_missing_domain_and_range(ttl)
        return {"value": {"missing_domain": r["count_missing_domain"], "missing_range": r["count_missing_range"]},
                "items": _iris(list(r["properties_missing_domain"]) + list(r["properties_missing_range"])),
                "detail": {"missing_domain": _iris(r["properties_missing_domain"]),
                           "missing_range": _iris(r["properties_missing_range"])}}

    def leaves(_):
        return {"value": {"leaves": len(H._find_leaf_nodes(g)), "total": len(classes)}, "items": []}

    def semantic(_):
        hierarchy, children_of = H._build_class_hierarchy(g, classes)
        status, roots = H._analyze_hierarchy_connections(g, hierarchy, classes, children_of)
        connected = [r for r, ok in status.items() if ok]
        return {"value": {"roots": len(roots), "connected": len(connected)}, "items": [],
                "detail": {"unconnected_roots": _iris(r for r, ok in status.items() if not ok)}}

    def declared(predicates, keep=lambda s: True) -> list[str]:
        return sorted({str(o) for p in predicates for o in g.objects(None, p) if isinstance(o, URIRef) and keep(str(o))})

    def sparql(_):
        urls = declared(SPARQL_PREDICATES)
        ratio = oc.check_sparql_accessibility_ttl(ttl) if urls else 0
        return {"value": {"declared": len(urls), "ratio": ratio}, "items": [], "detail": {"urls": urls}}

    def dump(_):
        urls = declared(DUMP_PREDICATES, lambda u: any(e in u.lower() for e in DUMP_EXTENSIONS))
        ratio = oc.check_rdf_dump_accessibility_ttl(ttl) if urls else 0
        return {"value": {"declared": len(urls), "ratio": ratio}, "items": [], "detail": {"urls": urls}}

    def license_(_):
        return {"value": oc.check_human_readable_license_ttl(ttl), "items": []}

    def external(_):
        return {"value": oc.check_external_data_provider_links_ttl(ttl), "items": []}

    def capital(_):
        with_, without = H._analyze_capital_coverage(g, classes)
        return {"value": {"total": len(classes), "with": len(with_)}, "items": _iris(without)}

    def space(_):
        if source is None or source.suffix.lower() != ".ttl" or not source.is_file():
            return {"skipped": "needs the original Turtle (.ttl) file; it reads the file text"}
        # OntoCheck's text heuristic also flags fragments around inline blank nodes, e.g.
        # 'rdfs:label "x" ; rdfs:range [' (PROV-O); a real class name never contains these characters
        errors = [e for e in H._scan_file_for_space_errors(str(source))
                  if not any(c in e["local_name"] for c in '"\';[(')]
        return {"value": len(errors), "items": [],
                "detail": {"names": [f"line {e['line_num']}: {e['local_name']}" for e in errors]}}

    def spelling(_):
        checked = errors = 0
        words: dict[str, str] = {}
        subjects: set[str] = set()
        for s, p, o in g:
            # English text only: OntoCheck's dictionary is English, other languages would all be "errors"
            lang = (getattr(o, "language", None) or "en").lower()
            if p in (RDFS.label, SKOS.definition, RDFS.comment) and lang.split("-")[0] == "en":
                tokens = _spell_tokens(str(o))
                bad = [t for t in tokens if H.spell.unknown([t])]
                checked += len(tokens)
                errors += len(bad)
                if bad:
                    subjects.add(str(s))
                    for w in bad:
                        words.setdefault(w, "")
        for w in sorted(words)[:SPELL_SUGGESTIONS]:      # suggestions are slow: only for the words shown
            words[w] = H.spell.correction(w) or ""
        return {"value": {"checked": checked, "errors": errors, "rate": errors / checked if checked else 0.0},
                "items": sorted(x for x in subjects if x.startswith(("http://", "https://", "urn:"))),
                "detail": {"words": dict(sorted(words.items()))}}

    def duplicates(lines):
        n = oc.find_duplicate_labels_from_graph(ttl)
        groups, cur = {}, None
        for ln in lines:
            if ln.strip().startswith("Label: '"):
                cur = ln.strip()[len("Label: '"):].rsplit("' used by", 1)[0]
                groups[cur] = []
            elif cur is not None and ln.strip().startswith("- "):
                groups[cur].append(ln.strip()[2:])
        return {"value": n, "items": sorted({u for us in groups.values() for u in us}), "detail": {"labels": groups}}

    def search_(_):
        if not search:
            return {"skipped": "no search term set (evaluation.ontocheck_search)"}
        hits = oc.mainClassSearch_v_0_0_1(g, search)
        return {"value": len(hits), "items": [], "detail": {"term": search, "matches": sorted(h["uri"] for h in hits)}}

    return {
        "checkLabel": coverage(H._analyze_label_coverage),
        "altLabelCheck": coverage(H._analyze_altlabel_coverage),
        "definitionCheck": coverage(H._analyze_definition_coverage),
        "isolatedElements": isolated, "classConnections": connections, "missingDomainRange": domain_range,
        "leafNodeCheck": leaves, "semanticConnection": semantic,
        "sparqlEndpoint": sparql, "rdfDump": dump, "humanLicense": license_, "externalLinks": external,
        "classCapitalCheck": capital, "classSpaceCheck": space, "spellCheck": spelling,
        "duplicateLabels": duplicates, "searchClass": search_,
    }


def run_ontocheck(graph: Graph, source: str | Path | None = None, *, network: bool = True,
                  search: str = "", metrics: list[str] | None = None) -> ExternalReport:
    """Run OntoCheck's metrics (all of :data:`METRICS` by default) and build the report."""
    log.info("Running OntoCheck metrics")
    try:
        with warnings.catch_warnings():       # OntoCheck 0.1.3 docstrings trigger SyntaxWarnings
            warnings.simplefilter("ignore", SyntaxWarning)
            import ontocheck as oc  # imported here: it may download NLTK stopwords on first import
            from ontocheck.helpers import helpers as H  # noqa: N812
    except Exception as e:  # noqa: BLE001
        return ontocheck_report({}, error=f"OntoCheck could not start: {e}")
    src = Path(source).expanduser() if source and not str(source).startswith(("http://", "https://")) else None
    wanted = [m for m in (metrics or list(METRICS)) if m in METRICS]
    results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        ttl = str(Path(tmp) / "ontology.ttl")
        graph.serialize(destination=ttl, format="turtle")
        g = Graph()
        for prefix, ns in BINDINGS.items():
            g.bind(prefix, ns)
        g.parse(ttl, format="turtle")
        with _captured():
            funcs = _metric_functions(oc, H, g, ttl, src, search.strip())
        for name in wanted:
            if name in NETWORK_METRICS and not network:
                results[name] = {"skipped": "network checks are turned off (evaluation.ontocheck_network)"}
                continue
            t0 = time.perf_counter()
            with _captured() as lines:
                try:
                    res = funcs[name](lines)
                except Exception as e:  # noqa: BLE001 - one metric must not stop the others
                    res = {"error": f"{type(e).__name__}: {e}"}
            res["log"] = list(lines)
            res["seconds"] = round(time.perf_counter() - t0, 2)
            results[name] = res
            log.debug("OntoCheck %s: %.2fs", name, res["seconds"])
    return ontocheck_report(results)


def check_ontocheck(graph: Graph, ev, source: str | Path | None = None) -> ExternalReport | None:
    """Run OntoCheck as configured in ``[evaluation]`` (``ev``); None when turned off."""
    if ev.ontocheck == "off":
        return None
    return run_ontocheck(graph, source, network=ev.ontocheck_network, search=ev.ontocheck_search or "")


__all__ = ["NETWORK_METRICS", "check_ontocheck", "run_ontocheck"]
