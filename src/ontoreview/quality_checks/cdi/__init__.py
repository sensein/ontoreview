"""Cross-domain interoperability (CDI) evaluation: runs :mod:`.core` as configured and reports it.

An ontology is cross-domain interoperable when it aligns with ontologies from other domains
(Align) and defines its classes in general, domain-neutral terms (Gen); CDI is their weighted
harmonic mean. See :mod:`.core` for the scoring and :mod:`ontoreview.report.cdi` for the report.

Reference specs (``evaluation.cdi_references``), mixable:

* a local or uploaded file: an ontology in any RDF syntax, or SSSOM mappings (``.tsv``);
* an ``http(s)://`` URL of such a file, downloaded for the run;
* ``ols`` / ``bioportal``: discover candidate ontologies in the repository (top N by coverage);
* ``ols:envo,chebi`` / ``bioportal:NCIT,SNOMEDCT``: named repository ontologies;
* another OLS or OntoPortal service (TIB Terminology Service, AgroPortal, EcoPortal, …):
  ``ols@https://service.tib.eu/ts4tib/api`` or ``ontoportal:AGROVOC@https://data.agroportal.lirmm.fr``.

API keys are optional in OntoReview but OntoPortal services (BioPortal, AgroPortal, …) answer only
with one; your own key also avoids shared rate limits. Keys come from ``evaluation.cdi_api_keys``
(``bioportal``, ``ontoportal`` for any other service, or ``bioportal@host``), else
``BIOPORTAL_API_KEY`` / ``ONTOPORTAL_API_KEY``. OLS has no API keys. Keys are sent as headers only
and never reported, saved to TOML or shown in the command line. Repository lookups send
the ontology's labels, synonyms and IRIs, never the ontology file; offline mode
(``evaluation.iri_network = false``) skips repositories and URLs.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ...report.models import ExternalReport
from . import core, termdb

log = logging.getLogger(__name__)

REPO_SPEC = re.compile(r"^(ols|bioportal|ontoportal)(?::([^@\s]*))?(?:@(https?://\S+))?$", re.IGNORECASE)
CONTENT_SUFFIX = {"turtle": ".ttl", "rdf+xml": ".owl", "n-triples": ".nt", "ld+json": ".jsonld",
                  "n3": ".n3", "trig": ".trig", "tab-separated": ".tsv"}
RDF_SUFFIXES = (".ttl", ".owl", ".rdf", ".xml", ".nt", ".n3", ".jsonld", ".trig", ".nq", ".ofn", ".omn")

_backend_lock = threading.Lock()
_env_lock = threading.RLock()
_backends: dict[str, object] = {}        # model name -> loaded classifier (kept for the app's later runs)


def parse_reference(spec: str) -> dict:
    """What a reference spec names: {kind: file|sssom|url|ols|bioportal, names, base, prefix}."""
    spec = spec.strip()
    m = REPO_SPEC.match(spec)
    if m and not Path(spec).expanduser().exists():
        kind = "ols" if m.group(1).lower() == "ols" else "bioportal"
        names = [x.strip() for x in (m.group(2) or "").split(",") if x.strip()] or None
        base = m.group(3)
        prefix = kind if not base else f"{kind}@{(urlsplit(base).hostname or 'custom').lower()}"
        return {"kind": kind, "names": names, "base": base, "prefix": prefix, "spec": spec}
    if spec.startswith(("http://", "https://")):
        return {"kind": "url", "url": spec, "spec": spec}
    if spec.lower().endswith(".tsv"):
        return {"kind": "sssom", "path": str(Path(spec).expanduser()), "spec": spec}
    return {"kind": "file", "path": str(Path(spec).expanduser()), "spec": spec}


def _download(url: str, folder: Path, timeout: float) -> Path:
    from ..iri.http import fetch

    meta, body = fetch(url, timeout, 200 * 1024 * 1024)
    if body is None:
        raise ValueError(meta.get("error") or "download failed")
    path_suffix = Path(urlsplit(meta.get("final_url") or url).path).suffix.lower()
    ctype = (meta.get("content_type") or "").lower()
    suffix = path_suffix if path_suffix in (*RDF_SUFFIXES, ".tsv") else \
        next((v for k, v in CONTENT_SUFFIX.items() if k in ctype), ".owl")
    target = folder / f"reference-{len(list(folder.iterdir()))}{suffix}"
    target.write_bytes(body)
    return target


def api_key(ev, ref: dict) -> str:
    """The optional API key for an OntoPortal reference: configured keys first (exact service,
    then ``ontoportal`` for any other service, or ``bioportal``), then the environment."""
    keys = {k.strip().lower(): v.strip() for k, v in (getattr(ev, "cdi_api_keys", None) or {}).items() if v and v.strip()}
    if ref["base"]:
        return (keys.get(ref["prefix"].lower()) or keys.get("ontoportal") or os.environ.get("ONTOPORTAL_API_KEY")
                or os.environ.get("BIOPORTAL_API_KEY", ""))
    return keys.get("bioportal") or os.environ.get("BIOPORTAL_API_KEY", "")


class _SafeAligner(core.OntoAlignerSource):
    """OntoAligner as an extra matcher: a failure is noted and leaves the other correspondences."""

    def __init__(self, *a, notes: list[str], **kw):
        super().__init__(*a, **kw)
        self.notes = notes

    def correspondences(self, onto):
        try:
            return super().correspondences(onto)
        except Exception as e:  # noqa: BLE001
            self.notes.append(f"OntoAligner ({self.matcher}) failed on {self.id}: {type(e).__name__}: {e}")
            return []


@contextmanager
def hf_token(ev):
    """Make the optional Hugging Face token visible to transformers / sentence-transformers downloads
    (they read ``HF_TOKEN``); without one, HF_TOKEN from the environment or anonymous access is used."""
    token = (getattr(ev, "cdi_hf_token", None) or "").strip()
    if not token:
        yield
        return
    with _env_lock:
        old = os.environ.get("HF_TOKEN")
        os.environ["HF_TOKEN"] = token
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("HF_TOKEN", None)
            else:
                os.environ["HF_TOKEN"] = old


def build_sources(specs: list[str], ev, workdir: Path, deadline: float, store=None,
                  info_cache=None) -> tuple[list, list[str]]:
    """Reference sources for ``specs``, plus notes on the ones that could not be used.

    With a writable term ``store``, user-provided reference ontologies are indexed into it (the
    database grows) and each source carries ``releases`` (what it was checked against); repository
    sources ask ``info_cache`` (the database) for ontology details before the repository.
    """
    sources, notes = [], []
    network = getattr(ev, "iri_network", True)
    for spec in [s for s in specs if s.strip()]:
        ref = parse_reference(spec)
        try:
            if ref["kind"] in ("ols", "bioportal", "url") and not network:
                notes.append(f"{spec}: skipped, network lookups are off")
                continue
            if ref["kind"] == "ols":
                sources.append(core.OLSSource(ref["names"], c_lex=ev.cdi_c_lex, base=ref["base"] or core.OLS_BASE,
                                              prefix=ref["prefix"], timeout=ev.cdi_timeout, deadline=deadline))
                sources[-1].info_cache = info_cache
            elif ref["kind"] == "bioportal":
                key = api_key(ev, ref)
                if not key:
                    notes.append(f"{spec}: skipped, this OntoPortal service needs an API key (Settings, "
                                 f"evaluation.cdi_api_keys or {'ONTOPORTAL' if ref['base'] else 'BIOPORTAL'}_API_KEY)")
                    continue
                sources.append(core.BioPortalSource(key, ref["names"], c_lex=ev.cdi_c_lex,
                                                    base=ref["base"] or core.BIOPORTAL_BASE, prefix=ref["prefix"],
                                                    timeout=ev.cdi_timeout, deadline=deadline))
                sources[-1].info_cache = info_cache
            else:
                path = Path(ref["path"]) if ref["kind"] != "url" else _download(ref["url"], workdir, ev.cdi_timeout)
                if not path.is_file():
                    notes.append(f"{spec}: file not found")
                    continue
                name = ref["url"] if ref["kind"] == "url" else path.name
                origin = ref["url"] if ref["kind"] == "url" else path.resolve().as_uri()
                kind = "url" if ref["kind"] == "url" else "file"
                if path.suffix.lower() == ".tsv":
                    src = core.SSSOMSource(path)
                    src.id = "sssom:" + name
                    src.releases = {src.id: termdb.file_release(path, origin, kind)}
                    sources.append(src)
                    continue
                src = core.LocalFileSource(path, c_lex=ev.cdi_c_lex)
                src.id = ("url:" if ref["kind"] == "url" else "file:") + name
                rel = None
                if store is not None:
                    try:
                        rel = termdb.save_reference(store, path, origin, kind)
                    except Exception as e:  # noqa: BLE001 - scoring does not depend on the database
                        notes.append(f"{spec}: not saved to the term database ({type(e).__name__}: {e})")
                src.db_key = rel.get("document") if rel else None
                src.releases = {src.id: rel or termdb.file_release(path, origin, kind)}
                sources.append(src)
                if ev.cdi_ontoaligner != "off":
                    if importlib.util.find_spec("ontoaligner") is None:
                        if not any(n.startswith("OntoAligner") for n in notes):
                            notes.append("OntoAligner matching skipped: pip install 'ontoreview[cdi]'")
                    else:
                        sources.append(_SafeAligner(path, matcher=ev.cdi_ontoaligner, notes=notes,
                                                    sbert_model=ev.cdi_sbert_model,
                                                    threshold=ev.cdi_ontoaligner_threshold, ontology_id=src.id))
        except Exception as e:  # noqa: BLE001 - one bad reference must not stop the others
            notes.append(f"{spec}: could not be used ({type(e).__name__}: {e})")
    return sources, notes


def generality_backend(ev) -> tuple[object | None, str]:
    """The zero-shot NLI classifier for Gen, or (None, why not)."""
    if not ev.cdi_generality:
        return None, "definition generality is turned off (evaluation.cdi_generality)"
    with _backend_lock:
        if ev.cdi_model in _backends:
            return _backends[ev.cdi_model], ""
        try:
            import transformers  # noqa: F401
        except ImportError:
            return None, "definition generality needs a language model: pip install 'ontoreview[cdi]'"
        try:
            log.info("Loading the generality model %s (downloaded on first use)", ev.cdi_model)
            backend = core.ZeroShotNLIBackend(ev.cdi_model)
        except Exception as e:  # noqa: BLE001
            return None, f"the generality model {ev.cdi_model} could not be loaded ({type(e).__name__}: {e})"
        _backends[ev.cdi_model] = backend
        return backend, ""


def run_cdi(graph: Graph, ev, source: str | None = None, namespace: str | None = None,
            backend=None) -> ExternalReport:
    """Score ``graph`` against the configured references and build the cross-domain section.

    ``backend`` replaces the language model (anything with ``predict_proba(texts)``), e.g. in tests.
    """
    return run_interoperability(graph, ev, source, namespace, backend, with_si=False)[0]


def run_interoperability(graph: Graph, ev, source: str | None = None, namespace: str | None = None,
                         backend=None, classifier=None, with_si: bool = True) -> list[ExternalReport]:
    """Cross-domain and (``with_si``) scientific interoperability from one run: SI reuses the
    reference set, the correspondences and Gen of the cross-domain score, so repositories are
    queried and the language model is loaded once. Returns [CDI report, SI report].

    ``classifier`` replaces the zero-shot domain classifier (anything with ``classify(texts)``)."""
    from ...report.cdi import cdi_report
    from ...report.si import si_report

    def failed(why: str) -> list[ExternalReport]:
        return [cdi_report(None, error=why)] + ([si_report(None, error=f"Not computed: {why}")] if with_si else [])

    log.info("Scoring cross-domain%s interoperability", " and scientific" if with_si else "")
    checked_at = datetime.now(timezone.utc).isoformat()
    deadline = time.time() + float(ev.cdi_budget)
    with tempfile.TemporaryDirectory(prefix="ontoreview-cdi-") as tmp:
        work = Path(tmp)
        src_path = Path(source).expanduser() if source and not str(source).startswith(("http://", "https://")) \
            else None
        if src_path is None or not src_path.is_file() or src_path.suffix.lower() not in RDF_SUFFIXES:
            src_path = work / "ontology.ttl"
            graph.serialize(destination=str(src_path), format="turtle")
        ns = ev.cdi_namespace or ([namespace] if namespace else "auto")
        try:
            onto = core.load_ontology(src_path, ns, include_properties=not ev.cdi_classes_only)
        except Exception as e:  # noqa: BLE001
            return failed(f"Could not read the ontology: {type(e).__name__}: {e}")
        if not onto.entities:
            return failed("No classes or properties in the ontology's namespace to score.")
        stores = _open_stores(ev)
        try:
            reports, ctx = _score(graph, ev, source, onto, work, deadline, stores, backend, checked_at)
            if with_si:
                reports.append(_scientific(ev, src_path, onto, ctx, classifier, checked_at) if ctx
                               else si_report(None, error=f"Not computed: {reports[0].error}"))
            return reports
        finally:
            for _, st in stores:
                st.close()


SECRET_SETTINGS = ("cdi_api_keys", "cdi_hf_token")


def _open_stores(ev) -> list[tuple[str, object]]:
    """[("bundled", read-only), ("cache", writable)] term databases; [] if they cannot be opened."""
    from ..iri import cache_path, open_stores

    try:
        bundle, cache = open_stores(cache_path(ev))
        return [("bundled", bundle), ("cache", cache)]
    except Exception as e:  # noqa: BLE001 - CDI still runs on repositories and files
        log.warning("CDI: term database unavailable (%s)", e)
        return []


def _score(graph, ev, source, onto, work: Path, deadline: float, stores, backend, checked_at: str):
    from ...report.cdi import cdi_report

    cache = dict(stores).get("cache")
    info_cache = termdb.InfoCache(cache, ev.iri_cache_days) if cache else None
    sources, notes = build_sources(ev.cdi_references, ev, work, deadline, cache, info_cache)
    if stores and ev.cdi_term_db:          # the term database first: offline, no key
        headers = [str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)]
        provided = {k for k in (getattr(x, "db_key", None) for x in sources) if k}
        sources.insert(0, termdb.TermDBSource(stores, headers, provided, c_lex=ev.cdi_c_lex))
    if not sources:
        return [cdi_report(None, error="No usable reference ontologies. " + " ".join(notes))], None
    settings = ev.model_dump(include={k for k in type(ev).model_fields if k.startswith(("cdi", "si"))},
                             exclude=set(SECRET_SETTINGS))
    run_id = None
    if cache is not None:
        ontology_iri = next((str(s) for s in graph.subjects(RDF.type, OWL.Ontology)), None)
        run_id = cache.start_cdi_run(source, ontology_iri, settings)
    why_no_gen = ""
    try:
        with hf_token(ev):          # model downloads: generality model and the SBERT matcher
            if backend is None:
                backend, why_no_gen = generality_backend(ev)
            result, entity_rows, onto_rows, corr = core.evaluate(
                onto, sources, backend, ev.cdi_domains, ev.cdi_top_n, ev.cdi_exclude, ev.cdi_tau,
                ev.cdi_rho_sub, ev.cdi_gamma, ev.cdi_k_max, ev.cdi_beta, ev.cdi_theta)
    except Exception as e:  # noqa: BLE001
        return [cdi_report(None, error=f"Scoring failed: {type(e).__name__}: {e}")], None
    if any(getattr(getattr(s, "http", None), "out_of_time", False) for s in sources):
        notes.append(f"Repository lookups stopped after {ev.cdi_budget:.0f} s (evaluation.cdi_budget); "
                     "alignment may be underestimated.")
    if why_no_gen:
        notes.append(f"Gen and CDI not computed: {why_no_gen}.")
    if info_cache is not None and info_cache.hits:
        notes.append(f"Details of {len(info_cache.hits)} repository ontologies came from the term database.")
    result.params["c_lex"] = ev.cdi_c_lex
    releases: dict[str, dict] = {}
    for src in sources:
        releases.update(getattr(src, "releases", {}) or {})
    for row in onto_rows:
        row["release"] = releases.get(row["id"])
    corr_rows = [asdict(m) for m in corr]
    record = {"checked_at": checked_at, "references": list(ev.cdi_references), "notes": notes,
              "run_id": run_id, "database": str(cache.path) if cache is not None else None, "settings": settings,
              "summary": result.to_dict(), "per_ontology": onto_rows, "per_entity": entity_rows,
              "correspondences": corr_rows, "releases": checked_against(onto_rows),
              "record_file": "cdi.json", "label": "Checked against"}
    if cache is not None:
        try:
            cache.finish_cdi_run(run_id, onto_rows, corr_rows, result.to_dict())
        except Exception as e:  # noqa: BLE001
            log.warning("CDI: run not recorded in the term database (%s)", e)
    ctx = {"result": result, "onto_rows": onto_rows, "corr": corr, "backend": backend, "why_no_gen": why_no_gen,
           "run_id": run_id, "references": list(ev.cdi_references)}
    return [cdi_report(record)], ctx


def _scientific(ev, src_path: Path, onto, ctx: dict, classifier, checked_at: str) -> ExternalReport:
    """SI on the cross-domain run in ``ctx`` (Definition "Scientific interoperability")."""
    from ...report.si import si_report
    from . import si

    result = ctx["result"]
    if result.gen is None:
        return si_report(None, error="Not computed: needs the generality score Gen"
                         + (f" ({ctx['why_no_gen']})" if ctx["why_no_gen"] else "") + ".")
    backend = ctx["backend"]
    if classifier is None and ev.si_classifier and hasattr(backend, "pipe"):
        classifier = si.DomainClassifier(backend)      # the generality model's pipeline, loaded once
    try:
        header = core.read_ontology_header(src_path)
        home, home_src = si.resolve_home_domain(ev.si_home_domain, header, classifier)
        res, domain_rows, assign_rows, m_no_u = si.evaluate_si(
            onto, result, ctx["onto_rows"], ctx["corr"], home, home_src, ev.si_domain_map, classifier,
            ev.si_p_min, ev.si_theta_s, si.UPPER_ONTOLOGY_IDS | set(ev.si_upper_ontologies),
            si.UPPER_NAMESPACES + tuple(ev.si_upper_namespaces))
    except Exception as e:  # noqa: BLE001
        return si_report(None, error=f"Not computed: {e}")
    others = res.taxonomy_size - 1
    summary = res.to_dict() | {"display": str(res.si), "params": {"theta": res.theta_s},
                               "display_note": f"of {others} domains (θ_s = {res.theta_s})"}
    for r in domain_rows:
        r["reference_ontologies"] = sorted(r["reference_ontologies"])
    record = {"checked_at": checked_at, "references": ctx["references"], "cdi_run_id": ctx["run_id"],
              "settings": ev.model_dump(include={k for k in type(ev).model_fields if k.startswith("si")}),
              "summary": summary, "per_domain": domain_rows, "domain_assignments": assign_rows,
              "n_correspondences_without_upper": len(m_no_u), "taxonomy": "OECD Fields of Science and "
              "Technology (Frascati Manual 2015), level 2", "record_file": "si.json"}
    return si_report(record)


def checked_against(onto_rows: list[dict]) -> list[dict]:
    """The releases of the selected reference ontologies, frozen into the record. A release without
    a version IRI or version is kept and said to be so, identified by date or fingerprint."""
    out = []
    for r in onto_rows:
        if r["status"] != "selected":
            continue
        rel = r.get("release") or {}
        entry = {"title": rel.get("title") or r.get("title") or r["id"], "id": r["id"],
                 "source": rel.get("source") or r.get("source"), "ontology": rel.get("ontology"),
                 "ontology_iri": rel.get("ontology_iri"), "version_iri": rel.get("version_iri"),
                 "version": rel.get("version"), "released": rel.get("released"),
                 "retrieved": rel.get("retrieved") or rel.get("cached"), "sha256": rel.get("sha256"),
                 "metadata_sha256": rel.get("metadata_sha256"), "source_url": rel.get("source_url"),
                 "identified_by": rel.get("identified_by") or "not recorded", "terms": r["n_correspondences"]}
        if not (entry["version_iri"] or entry["version"]):
            entry["note"] = ("version not reported by the source; identified by "
                             + (entry["identified_by"] if rel else "nothing (no details could be retrieved)"))
            entry["release_recorded"] = bool(rel)
        out.append({k: v for k, v in entry.items() if v not in (None, "")})
    return out


def check_cdi(graph: Graph, ev, source: str | None = None, namespace: str | None = None) -> list[ExternalReport]:
    """Cross-domain and scientific interoperability as configured in ``[evaluation]`` (both on by
    default; SI needs the cross-domain run, which then runs even when only SI is wanted)."""
    if ev.cdi == "off" and ev.si == "off":
        return []
    reports = run_interoperability(graph, ev, source, namespace, with_si=ev.si != "off")
    return reports if ev.cdi != "off" else reports[1:]


__all__ = ["api_key", "build_sources", "checked_against", "hf_token", "check_cdi", "generality_backend", "parse_reference",
           "run_cdi", "run_interoperability"]
