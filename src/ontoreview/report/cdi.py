"""Cross-domain interoperability results → a metrics table plus findings for the review.

The scores (CDI, Align, Gen) and the alignment with each selected reference ontology become
metric rows; entities with no correspondence and classes with very specific definitions become
``info`` findings (pointers for improving reuse, not defects). The full record (per entity, per
reference ontology, every correspondence) is kept in ``ExternalReport.provenance`` and written to
``cdi.json`` next to the docs.
"""

from __future__ import annotations

from .models import ExternalItem, ExternalReport, new_report, sort_items

GROUP_SCORES = "Cross-domain interoperability"
GROUP_REFS = "Alignment by reference ontology"
SPECIFIC_LEVEL = 4      # predicted ℓ_4 / ℓ_5: a concrete system or measurable details


def _f(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"


def _scores(s: dict, notes: list[str]) -> list[dict]:
    p = s["params"]
    theta = p["theta"]
    row = {"group": GROUP_SCORES}
    out = []
    if s["cdi"] is None:
        out.append(row | {"metric": "CDI", "title": "CDI score", "status": "skipped",
                          "value": "Not computed: needs the generality score",
                          "about": "Weighted harmonic mean of Align and Gen; low when either is low"})
    else:
        verdict = "interoperable" if s["interoperable"] else "not interoperable"
        out.append(row | {"metric": "CDI", "title": "CDI score", "status": "ok" if s["interoperable"] else "warn",
                          "value": f"{_f(s['cdi'])}, {verdict} (θ = {theta}, β = {p['beta']})",
                          "about": "Weighted harmonic mean of Align and Gen; low when either is low"})
    out.append(row | {"metric": "Align", "title": "Alignment", "status": "ok" if s["align"] >= theta else "warn",
                      "value": f"{_f(s['align'])}; {s['n_aligned_entities']} of {s['n_entities']} entities aligned",
                      "about": "Mean best correspondence strength per entity into ontologies of other domains "
                               f"(counted from τ = {p['tau']})"})
    if s["gen"] is None:
        why = next((n.split(": ", 1)[1].rstrip(".") for n in notes if n.startswith("Gen and CDI not computed")), "")
        out.append(row | {"metric": "Gen", "title": "Generality", "status": "skipped",
                          "value": f"Not computed{': ' + why if why else ''}. Definition coverage "
                                   f"{s['n_defined_classes']}/{s['n_classes']}",
                          "about": "How domain-neutral the class definitions are (zero-shot language model)"})
    else:
        out.append(row | {"metric": "Gen", "title": "Generality", "status": "ok" if s["gen"] >= theta else "warn",
                          "value": f"{_f(s['gen'])} = definition coverage {_f(s['definition_coverage'])} "
                                   f"({s['n_defined_classes']}/{s['n_classes']}) × mean generality "
                                   f"{_f(s['mean_definition_generality'])}",
                          "about": "How domain-neutral the class definitions are (zero-shot language model)"})
    return out


def _references(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["status"] != "selected":
            continue
        kind = "given" if r["given"] else "discovered"
        out.append({"group": GROUP_REFS, "metric": r["id"], "title": r["title"] or r["id"],
                    "status": "info", "value": f"Align_d {_f(r['align_d'])}, coverage {_f(r['coverage'])}, "
                                               f"{r['n_correspondences']} correspondences ({kind})",
                    "about": f"{r['id']}" + (f"; domain: {r['domain']}" if r["domain"] else "") + _release_text(r)})
    return out


def _release_text(r: dict) -> str:
    rel = r.get("release") or {}
    if not rel:
        return "; release not recorded"
    what = rel.get("version_iri") or rel.get("version")
    if what:
        return f"; release {what}"
    return f"; version not reported (identified by {rel.get('identified_by', 'retrieval time')})"


def _scope(record: dict) -> str:
    rows = record["per_ontology"]
    sel = [r for r in rows if r["status"] == "selected"]
    given = sum(1 for r in sel if r["given"])
    excluded = {k: sum(1 for r in rows if r["status"] == k)
                for k in ("excluded-self", "excluded-same-domain", "excluded-user", "below-top-N")}
    parts = [f"{len(sel)} reference ontologies ({given} given, {len(sel) - given} discovered)"]
    labels = {"excluded-self": "this ontology itself", "excluded-same-domain": "same domain",
              "excluded-user": "excluded by you", "below-top-N": "below the top N"}
    left = [f"{n} {labels[k]}" for k, n in excluded.items() if n]
    if left:
        parts.append("left out: " + ", ".join(left))
    text = "; ".join(parts) + ". Full record in cdi.json"
    text += (f", and as CDI run {record['run_id']} in the term database." if record.get("run_id") else ".")
    return " ".join([text, *record.get("notes", [])])


def _items(record: dict) -> list[ExternalItem]:
    ents = record["per_entity"]
    items = []
    unaligned = [e["entity"] for e in ents if not e["aligned"]]
    if unaligned:
        items.append(ExternalItem("CDI-A", "No correspondence in another domain", "info",
                                  "No direct, lexical or inherited correspondence of sufficient strength "
                                  "into the reference ontologies. Mapping these (e.g. SSSOM, "
                                  "owl:equivalentClass, rdfs:subClassOf) raises Align.", unaligned))
    specific = [e["entity"] for e in ents if e["is_class"] and (e.get("predicted_level") or 0) >= SPECIFIC_LEVEL]
    if specific:
        items.append(ExternalItem("CDI-G", "Very specific class definition", "info",
                                  "The definition reads as describing a concrete system or measurable details. "
                                  "A more general wording helps reuse outside this domain and raises Gen.",
                                  specific))
    return items


def cdi_report(record: dict | None, error: str | None = None) -> ExternalReport:
    """The cross-domain interoperability section of the review."""
    if error or record is None:
        return new_report("cdi", error=error or "Not run.")
    s = record["summary"]
    rep = new_report("cdi", sort_items(_items(record)), scope=_scope(record))
    rep.metrics = _scores(s, record.get("notes", [])) + _references(record["per_ontology"])
    rep.provenance = record
    if not rep.items:
        rep.note = "Every entity has a correspondence; no very specific definitions."
    return rep


__all__ = ["cdi_report"]
