"""Scientific interoperability results → a metrics table plus pointers for the review.

The degree SI (covered domains), the home domain D, the generality ceiling and the upper-level
filter become metric rows; every domain with any alignment gets a row with Align_δ and CDI_{β,δ};
every reference ontology shows the domain it was assigned and how (your map, repository metadata,
the classifier, upper-level, none). Reference ontologies left without a domain become an ``info``
finding, with the setting that fixes it. The full record goes to ``si.json``.
"""

from __future__ import annotations

from .models import ExternalItem, ExternalReport, new_report, sort_items

GROUP_SCORES = "Scientific interoperability"
GROUP_DOMAINS = "Interoperability per scientific domain"
GROUP_ASSIGN = "Domain of each reference ontology"
SOURCE_TEXT = {"override": "your domain map", "metadata": "repository metadata", "classifier": "classifier",
               "upper": "upper-level, ignored", "none": "no domain, ignored"}


def _f(x) -> str:
    return "–" if x is None else f"{x:.2f}"


def _scores(s: dict) -> list[dict]:
    row = {"group": GROUP_SCORES}
    others = s["taxonomy_size"] - 1
    covered = ", ".join(s["covered_domains"]) or "none"
    out = [row | {"metric": "SI", "title": "Scientific interoperability", "status": "ok" if s["si"] else "warn",
                  "value": f"{s['si']} of {others} domains covered ({covered}); θ_s = {s['theta_s']}",
                  "about": "Scientific domains other than the ontology's own whose CDI reaches θ_s"},
           row | {"metric": "SI^", "title": "Share of domains", "status": "info",
                  "value": f"{s['si_normalised']:.3f}",
                  "about": f"SI divided by the {others} possible domains (OECD fields of science)"},
           row | {"metric": "D", "title": "Own domain", "status": "info",
                  "value": f"{s['home_domain']} ({s['home_domain_source']})",
                  "about": "Not counted; set evaluation.si_home_domain to fix it"},
           row | {"metric": "Ceiling", "title": "Generality ceiling",
                  "status": "warn" if s["generality_ceiling"] < s["theta_s"] else "info",
                  "value": f"{_f(s['generality_ceiling'])}, from Gen = {_f(s['generality'])}",
                  "about": "The highest CDI any one domain can reach, even fully aligned; more general class "
                           "definitions raise it"},
           row | {"metric": "Upper", "title": "Upper-level ontologies ignored", "status": "info",
                  "value": f"{s['n_correspondences_removed_upper']} correspondences removed; "
                           f"{s['n_ignored_upper']} upper-level and {s['n_ignored_no_domain']} reference ontologies "
                           f"without a domain ignored, of {s['n_reference_ontologies']}",
                  "about": "BFO, COB, RO, DOLCE/DUL, GFO, SUMO, gUFO (by ontology and IRI namespace)"},
           row | {"metric": "CDI ≥ CDI_δ", "title": "Consistency with CDI",
                  "status": "ok" if s["proposition_holds"] else "error",
                  "value": f"{'holds' if s['proposition_holds'] else 'violated'}: every CDI_δ ≤ CDI = {_f(s['cdi'])}",
                  "about": "A domain's CDI can never exceed the cross-domain score"}]
    return out


def _domains(rows: list[dict], theta_s: float) -> list[dict]:
    out = []
    for r in rows:
        if not r["align_delta"]:
            continue
        refs = r["reference_ontologies"]
        refs = refs if isinstance(refs, str) else ", ".join(refs)
        out.append({"group": GROUP_DOMAINS, "metric": r["domain"], "title": r["name"],
                    "status": "ok" if r["covered"] else "warn",
                    "value": f"CDI_δ {_f(r['cdi_delta'])} ({'covered' if r['covered'] else f'below θ_s = {theta_s}'}); "
                             f"Align_δ {_f(r['align_delta'])}, {r['n_aligned_entities']} entities aligned",
                    "about": f"via {refs}"})
    return out


def _assignments(rows: list[dict]) -> list[dict]:
    from ..quality_checks.cdi.si import fos_label

    out = []
    for a in sorted(rows, key=lambda r: (not r["domains"], r["ontology"])):
        doms = ", ".join(fos_label(d) for d in a["domains"]) or "–"
        how = SOURCE_TEXT.get(a["source"], a["source"])
        if a["source"] == "classifier" and a.get("score") is not None:
            how += f", p = {a['score']:.2f}"
        out.append({"group": GROUP_ASSIGN, "metric": a["ontology"], "title": a["title"] or a["ontology"],
                    "status": "info", "value": doms,
                    "about": how + (f"; repository domain: {a['raw_domain']}" if a.get("raw_domain") else "")})
    return out


def _items(record: dict) -> list[ExternalItem]:
    items = []
    none = [a["ontology"] for a in record["domain_assignments"] if a["source"] == "none"]
    if none:
        items.append(ExternalItem(
            "SI-D", "Reference ontology without a scientific domain", "info",
            "Its correspondences count for CDI but not for any domain. Give it one in "
            "evaluation.si_domain_map (ontology id → OECD field), e.g. si_domain_map = {\"" + none[0]
            + "\" = [\"1.5\"]}.", note=", ".join(none)))
    s = record["summary"]
    if s["home_domain_source"].startswith("classifier"):
        items.append(ExternalItem(
            "SI-H", "Own domain guessed by the classifier", "info",
            f"D = {s['home_domain']} was inferred from the ontology's title and description "
            f"({s['home_domain_source']}). Set evaluation.si_home_domain if it is wrong: "
            "that domain is never counted.", note=s["home_domain"]))
    return items


def _scope(record: dict) -> str:
    s = record["summary"]
    return (f"Δ = OECD fields of science ({s['taxonomy_size']} fields; the ontology's own is not counted); "
            f"θ_s = {s['theta_s']}; the same reference ontologies and correspondences as the cross-domain "
            "score, without upper-level ontologies. Full record in si.json.")


def si_report(record: dict | None, error: str | None = None) -> ExternalReport:
    """The scientific interoperability section of the review."""
    if error or record is None:
        return new_report("si", error=error or "Not run.")
    s = record["summary"]
    rep = new_report("si", sort_items(_items(record)), scope=_scope(record))
    rep.metrics = _scores(s) + _domains(record["per_domain"], s["theta_s"]) + _assignments(record["domain_assignments"])
    rep.provenance = record
    if not rep.items:
        rep.note = "Every reference ontology has a scientific domain."
    return rep


__all__ = ["si_report"]
