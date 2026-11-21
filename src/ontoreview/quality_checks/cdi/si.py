"""Scientific interoperability (SI): in how many scientific domains, other than its own, an
ontology is interoperable.

Ported from the reference implementation ``scientific_interoperability.py`` (the SI bundle). It
reuses the cross-domain interoperability run as is: the reference set 𝒪, the correspondences M(e)
and Gen(O_D) come from :func:`.core.evaluate`. New here are the domain taxonomy Δ (OECD Fields of
Science and Technology), the upper-level filter (rules a and b), domain assignment and the
per-domain scores.

Correspondence with the definition (labels in brackets)
  Δ  taxonomy of scientific domains (OECD FOS)          -> OECD_FOS
  D  domain of O_D                                       -> resolve_home_domain()
  𝒰, U  upper-level ontologies / their entities          -> UPPER_ONTOLOGY_IDS, UPPER_NAMESPACES
  rule (a): dom(O_d) = ∅ for O_d ∈ 𝒰                     -> assign_domains()
  rule (b): drop correspondences with e' ∈ U -> M^{∖U}   -> remove_upper()
  dom(O_d) ⊆ Δ  (override > upper > metadata > classifier) -> assign_domains()
  𝒪_δ                                                     -> ontologies_by_domain()
  a_δ(e), Align_δ(O_D), CDI_{β,δ}(O_D)  [eq:align-domain] -> domain_scores()
  Δ_θs(O_D), SI(O_D), SI^(O_D)          [eq:si]           -> scientific_interoperability()
  Remark (generality ceiling)                              -> generality_ceiling()
  Proposition prop:cdi-si (CDI_{β,δ} ≤ CDI_β)              -> evaluate_si()
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Protocol

from . import core
from .core import Correspondence, OntologyEntities, alignment_score, alignment_strengths, cdi_score

ABSTRACT_SI = (
    "We consider an ontology scientifically interoperable across x domains if, for x distinct "
    "scientific domains other than its own, it both aligns with ontologies of that domain and defines "
    "its classes in sufficiently general, domain-neutral terms. Alignments to upper-level ontologies are "
    "ignored, so that x counts connections to scientific fields rather than shared foundational commitments."
)

DEFAULT_THETA_S = 0.3     # θ_s  threshold for a domain to count as covered   [eq:si]
DEFAULT_P_MIN = 0.15      # minimum classifier probability to assign a domain

# Δ: OECD Fields of Science and Technology (Frascati Manual 2015), level 2
OECD_FOS: dict[str, str] = {
    "1.1": "Mathematics", "1.2": "Computer and information sciences",
    "1.3": "Physical sciences", "1.4": "Chemical sciences",
    "1.5": "Earth and related environmental sciences", "1.6": "Biological sciences",
    "1.7": "Other natural sciences",
    "2.1": "Civil engineering",
    "2.2": "Electrical engineering, electronic engineering, information engineering",
    "2.3": "Mechanical engineering", "2.4": "Chemical engineering", "2.5": "Materials engineering",
    "2.6": "Medical engineering", "2.7": "Environmental engineering",
    "2.8": "Environmental biotechnology", "2.9": "Industrial biotechnology",
    "2.10": "Nano-technology", "2.11": "Other engineering and technologies",
    "3.1": "Basic medicine", "3.2": "Clinical medicine", "3.3": "Health sciences",
    "3.4": "Medical biotechnology", "3.5": "Other medical sciences",
    "4.1": "Agriculture, forestry, and fisheries", "4.2": "Animal and dairy science",
    "4.3": "Veterinary science", "4.4": "Agricultural biotechnology",
    "4.5": "Other agricultural sciences",
    "5.1": "Psychology", "5.2": "Economics and business", "5.3": "Educational sciences",
    "5.4": "Sociology", "5.5": "Law", "5.6": "Political science",
    "5.7": "Social and economic geography", "5.8": "Media and communications",
    "5.9": "Other social sciences",
    "6.1": "History and archaeology", "6.2": "Languages and literature",
    "6.3": "Philosophy, ethics and religion", "6.4": "Arts (arts, history of arts, performing arts, music)",
    "6.5": "Other humanities",
}

UPPER = "UPPER"   # marker for rule (a)

# OLS `domain` metadata (OBO Foundry domains) and BioPortal categories -> Δ.
# None = no scientific field implied (the classifier decides).
REPOSITORY_DOMAIN_TO_FOS: dict[str, str | None] = {
    "anatomy and development": "1.6",
    "biological systems": "1.6",
    "organisms": "1.6",
    "phenotype": "1.6",
    "microbiology": "1.6",
    "chemistry and biochemistry": "1.4",
    "environment": "1.5",
    "health": "3.2",
    "diet, metabolomics, and nutrition": "3.3",
    "information": "1.2",
    "information technology": "1.2",
    "simulation": "1.2",
    "agriculture": "4.1",
    "investigations": None,          # research methods, not a field
    "upper": UPPER,                  # BFO, COB, RO in OLS
}

# 𝒰: upper-level ontologies, by reference-ontology id and by IRI namespace (U)
UPPER_ONTOLOGY_IDS: frozenset[str] = frozenset({
    "ols:bfo", "ols:cob", "ols:ro", "ols:dolce", "ols:dul", "ols:gfo", "ols:sumo", "ols:gufo",
    "bioportal:BFO", "bioportal:COB", "bioportal:RO", "bioportal:DOLCE", "bioportal:DUL",
    "bioportal:GFO", "bioportal:SUMO", "bioportal:GUFO",
})
UPPER_NAMESPACES: tuple[str, ...] = (
    "http://purl.obolibrary.org/obo/BFO_",                                # BFO
    "http://purl.obolibrary.org/obo/COB_",                                # COB
    "http://purl.obolibrary.org/obo/RO_",                                 # RO (OLS domain "upper")
    "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl#",             # DOLCE+DnS Ultralite
    "http://www.loa-cnr.it/ontologies/DOLCE-Lite.owl#",                   # DOLCE-Lite
    "http://www.loa.istc.cnr.it/ontologies/DOLCE-Lite.owl#",
    "http://www.onto-med.de/ontologies/gfo.owl#",                         # GFO
    "http://www.ontologyportal.org/SUMO.owl#",                            # SUMO
    "http://www.ontologyportal.org/SUMO#",
    "http://purl.org/nemo/gufo#",                                         # gUFO
)


@dataclass
class DomainAssignment:
    """dom(O_d) ⊆ Δ for one reference ontology, with how it was decided."""
    ontology: str
    domains: list[str] = field(default_factory=list)   # FOS codes; [] = ignored
    source: str = ""        # override | upper | metadata | classifier | none
    score: float | None = None
    title: str = ""
    raw_domain: str = ""


@dataclass
class SIResult:
    home_domain: str                     # "1.2 Computer and information sciences"
    home_domain_source: str              # user | classifier (p=…)
    si: int                              # SI(O_D) = x
    si_normalised: float                 # SI^(O_D)
    covered_domains: list[str]           # Δ_θs(O_D)
    theta_s: float
    taxonomy_size: int                   # |Δ|
    generality: float                    # Gen(O_D)
    generality_ceiling: float            # max achievable CDI_{β,δ}
    cdi: float                           # CDI_β(O_D), for comparison
    align: float                         # Align(O_D)
    proposition_holds: bool              # CDI_{β,δ} ≤ CDI_β for all δ
    n_reference_ontologies: int
    n_ignored_upper: int
    n_ignored_no_domain: int
    n_correspondences_removed_upper: int
    upper_namespaces: list[str]

    @property
    def interoperable(self) -> bool:
        return self.si >= 1

    def to_dict(self) -> dict:
        return asdict(self) | {"interoperable": self.interoperable}


class Classifier(Protocol):
    def classify(self, texts: Sequence[str]) -> list[tuple[str, float]]: ...


# ---------------------------------------------------------------- domain taxonomy
def resolve_fos(spec: str) -> str:
    """A FOS code ('1.2') or a (partial, case-insensitive) field name -> the FOS code."""
    spec = str(spec).strip()
    if spec in OECD_FOS:
        return spec
    code = spec.split(" ", 1)[0]
    if code in OECD_FOS:              # "1.2 Computer and information sciences"
        return code
    hits = [c for c, n in OECD_FOS.items() if spec.lower() in n.lower()]
    if len(hits) == 1:
        return hits[0]
    exact = [c for c, n in OECD_FOS.items() if spec.lower() == n.lower()]
    if len(exact) == 1:
        return exact[0]
    raise ValueError(f"cannot resolve the domain {spec!r} to one OECD field of science "
                     f"({'matches: ' + ', '.join(hits) if hits else 'no match'})")


def fos_label(code: str) -> str:
    return f"{code} {OECD_FOS[code]}"


class DomainClassifier:
    """Zero-shot classification of an ontology's title + description into Δ. Reuses the NLI pipeline
    of the generality backend, so the model is loaded once."""

    def __init__(self, backend=None, model: str = core.DEFAULT_NLI_MODEL, include_other: bool = False):
        self.codes = [c for c, n in OECD_FOS.items() if include_other or not n.startswith("Other")]
        labels = [OECD_FOS[c] for c in self.codes]
        if backend is not None and hasattr(backend, "pipe"):
            self.clf = core.ZeroShotNLIBackend.__new__(core.ZeroShotNLIBackend)
            self.clf.pipe, self.clf.batch_size = backend.pipe, backend.batch_size
            self.clf.levels, self.clf.template = labels, "This ontology is about {}."
        else:
            self.clf = core.ZeroShotNLIBackend(model, levels=labels,
                                               hypothesis_template="This ontology is about {}.")

    def classify(self, texts: Sequence[str]) -> list[tuple[str, float]]:
        """(FOS code, probability) of the top field for each text."""
        out = []
        for p in self.clf.predict_proba(list(texts)):
            i = max(range(len(p)), key=p.__getitem__)
            out.append((self.codes[i], float(p[i])))
        return out


def _crosswalk(raw_domain: str) -> tuple[list[str], bool]:
    """Repository domain metadata -> FOS codes. Returns (codes, is_upper)."""
    codes, upper = [], False
    for part in [x.strip().lower() for x in (raw_domain or "").split(",") if x.strip()]:
        tgt = REPOSITORY_DOMAIN_TO_FOS.get(part)
        if tgt == UPPER:
            upper = True
        elif tgt:
            codes.append(tgt)
    return sorted(set(codes)), upper


def assign_domains(ontologies: Sequence[dict], overrides: dict[str, list[str]] | None = None,
                   classifier: Classifier | None = None, p_min: float = DEFAULT_P_MIN,
                   upper_ids: frozenset[str] | set[str] = UPPER_ONTOLOGY_IDS) -> dict[str, DomainAssignment]:
    """dom(O_d) ⊆ Δ for each reference ontology. Priority: user override > rule (a) upper-level >
    repository metadata (crosswalk) > zero-shot classifier on title + description > none (ignored)."""
    overrides = overrides or {}
    out: dict[str, DomainAssignment] = {}
    to_classify: list[tuple[str, str]] = []
    for o in ontologies:
        oid, raw = o["id"], o.get("domain", "") or ""
        a = DomainAssignment(oid, title=o.get("title", "") or "", raw_domain=raw)
        codes, is_upper = _crosswalk(raw)
        if oid in overrides:
            a.domains, a.source = sorted({resolve_fos(x) for x in overrides[oid]}), "override"
        elif oid in upper_ids or is_upper:
            a.domains, a.source = [], "upper"                     # rule (a)
        elif codes:
            a.domains, a.source = codes, "metadata"
        else:
            text = ". ".join(x for x in (o.get("title", ""), o.get("description", "")) if x).strip()
            if classifier is not None and text:
                to_classify.append((oid, text[:1000]))
            a.source = "none"
        out[oid] = a
    if classifier is not None and to_classify:
        for (oid, _), (code, p) in zip(to_classify, classifier.classify([t for _, t in to_classify]), strict=True):
            if p >= p_min:
                out[oid].domains, out[oid].source, out[oid].score = [code], "classifier", p
    return out


def resolve_home_domain(spec: str | None, header: dict, classifier: Classifier | None) -> tuple[str, str]:
    """D ∈ Δ: from the setting, else by classifying O_D's own title and description."""
    if spec:
        return resolve_fos(spec), "user"
    text = ". ".join(x for x in (header.get("title", ""), header.get("description", "")) if x)
    if classifier is None or not text:
        raise ValueError("the ontology's own scientific domain D is unknown: set evaluation.si_home_domain "
                         "(an OECD field code such as 1.2, or a field name)"
                         + ("" if text else "; the ontology has no title or description to classify"))
    code, p = classifier.classify([text[:1000]])[0]
    return code, f"classifier (p = {p:.2f})"


# ---------------------------------------------------------------- rule (b)
def is_upper_entity(iri: str, namespaces: Sequence[str] = UPPER_NAMESPACES) -> bool:
    return iri.startswith(tuple(namespaces))


def remove_upper(M: Sequence[Correspondence], upper_ontologies: set[str],
                 namespaces: Sequence[str] = UPPER_NAMESPACES) -> list[Correspondence]:
    """M^{∖U}: drop m with e' ∈ U (by namespace, incl. via imports and traversal) or with e' in an
    upper-level ontology O_d ∈ 𝒰."""
    return [m for m in M
            if not is_upper_entity(m.target, namespaces) and m.target_ontology not in upper_ontologies]


# ---------------------------------------------------------------- per-domain scores
def ontologies_by_domain(assignments: dict[str, DomainAssignment]) -> dict[str, set[str]]:
    """𝒪_δ = {O_d | δ ∈ dom(O_d)}."""
    by: dict[str, set[str]] = defaultdict(set)
    for oid, a in assignments.items():
        for d in a.domains:
            by[d].add(oid)
    return by


def domain_scores(onto: OntologyEntities, M_noU: Sequence[Correspondence], O_delta: dict[str, set[str]],
                  home: str, gen: float, tau: float = core.DEFAULT_TAU, rho_sub: float = core.DEFAULT_RHO_SUB,
                  gamma: float = core.DEFAULT_GAMMA, beta: float = core.DEFAULT_BETA) -> dict[str, dict]:
    """For each δ ∈ Δ ∖ {D}: a_δ(e) [eq:ae on M^{∖U} ∩ 𝒪_δ], Align_δ, CDI_{β,δ}."""
    out = {}
    for delta in OECD_FOS:
        if delta == home:
            continue
        refs = O_delta.get(delta, set())
        Md = [m for m in M_noU if m.target_ontology in refs]
        strengths = alignment_strengths(onto.entities, Md, tau, rho_sub, gamma)   # a_δ(e)
        align_d = alignment_score(strengths)                                       # Align_δ
        out[delta] = {"domain": delta, "name": OECD_FOS[delta], "reference_ontologies": sorted(refs),
                      "n_aligned_entities": sum(a > 0 for a, _ in strengths.values()),
                      "align_delta": align_d, "cdi_delta": cdi_score(align_d, gen, beta)}  # CDI_{β,δ}
    return out


def generality_ceiling(gen: float, beta: float = core.DEFAULT_BETA) -> float:
    """Remark: the largest CDI_{β,δ}, reached when Align_δ = 1: (1+β²)G / (1+β²G)."""
    return cdi_score(1.0, gen, beta)


def scientific_interoperability(per_domain: dict[str, dict], theta_s: float = DEFAULT_THETA_S
                                ) -> tuple[list[str], int, float]:
    """Δ_θs(O_D), SI(O_D) = |Δ_θs|, SI^ = SI / (|Δ| − 1)                         [eq:si]"""
    covered = sorted(d for d, r in per_domain.items() if r["cdi_delta"] >= theta_s)
    for d, r in per_domain.items():
        r["covered"] = d in covered
    return covered, len(covered), len(covered) / (len(OECD_FOS) - 1)


def evaluate_si(onto: OntologyEntities, cdi_result, onto_rows: Sequence[dict], M: Sequence[Correspondence],
                home_domain: str, home_source: str = "user", overrides: dict[str, list[str]] | None = None,
                classifier: Classifier | None = None, p_min: float = DEFAULT_P_MIN,
                theta_s: float = DEFAULT_THETA_S, upper_ids: frozenset[str] | set[str] = UPPER_ONTOLOGY_IDS,
                upper_namespaces: Sequence[str] = UPPER_NAMESPACES):
    """SI on the cross-domain run's 𝒪, M(e) and Gen(O_D) (``cdi_result`` from :func:`.core.evaluate`,
    which must include Gen). Returns (result, per-domain rows, domain-assignment rows, M^{∖U})."""
    p = cdi_result.params
    selected = [r for r in onto_rows if r["status"] == "selected"]
    assignments = assign_domains(selected, overrides, classifier, p_min, upper_ids)
    upper_onts = {o for o, a in assignments.items() if a.source == "upper"} | set(upper_ids)
    M_noU = remove_upper(M, upper_onts, upper_namespaces)                       # rule (b)
    O_delta = ontologies_by_domain(assignments)
    per_domain = domain_scores(onto, M_noU, O_delta, home_domain, cdi_result.gen,
                               p["tau"], p["rho_sub"], p["gamma"], p["beta"])
    covered, si, si_hat = scientific_interoperability(per_domain, theta_s)
    prop = all(r["cdi_delta"] <= cdi_result.cdi + 1e-12 for r in per_domain.values())
    result = SIResult(
        home_domain=fos_label(home_domain), home_domain_source=home_source, si=si, si_normalised=si_hat,
        covered_domains=[fos_label(d) for d in covered], theta_s=theta_s, taxonomy_size=len(OECD_FOS),
        generality=cdi_result.gen, generality_ceiling=generality_ceiling(cdi_result.gen, p["beta"]),
        cdi=cdi_result.cdi, align=cdi_result.align, proposition_holds=prop,
        n_reference_ontologies=len(selected),
        n_ignored_upper=sum(a.source == "upper" for a in assignments.values()),
        n_ignored_no_domain=sum(a.source == "none" for a in assignments.values()),
        n_correspondences_removed_upper=len(M) - len(M_noU), upper_namespaces=list(upper_namespaces))
    domain_rows = sorted(per_domain.values(), key=lambda r: (-r["cdi_delta"], r["domain"]))
    assign_rows = [asdict(a) for a in assignments.values()]
    return result, domain_rows, assign_rows, M_noU


__all__ = ["ABSTRACT_SI", "DEFAULT_P_MIN", "DEFAULT_THETA_S", "DomainAssignment", "DomainClassifier", "OECD_FOS",
           "SIResult", "UPPER_NAMESPACES", "UPPER_ONTOLOGY_IDS", "assign_domains", "domain_scores", "evaluate_si",
           "fos_label", "generality_ceiling", "remove_upper", "resolve_fos", "resolve_home_domain",
           "scientific_interoperability"]
