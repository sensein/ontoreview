"""Regenerate the example documentation sites in ./examples from the test fixtures.

    python scripts/build_examples.py
    python -m http.server 8000 -d examples     # then open http://127.0.0.1:8000/
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

import ontoreview
from ontoreview.build import load, resolve_config
from ontoreview.collection import build_collection, export_collection
from ontoreview.export import export_markdown
from ontoreview.model.extract import extract

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "examples"

CQ = [str(FIX / "cq" / "pizza-cq.yaml"), str(FIX / "cq" / "pizza-cq.csv")]

SITES = [
    ("pizza", FIX / "pizza-v2.ttl", {"previous_version": str(FIX / "pizza.ttl"), "languages": ["en", "es"],
                                     "competency_questions": CQ, "evaluation": {"oops": "on"}},
     "OWL ontology: competency questions, OOPS! evaluation, changelog, English/Spanish"),
    ("pizza-index", FIX / "pizza-v2.ttl", {"competency_questions": CQ,
                                           "ui": {"term_index": "both", "font": "sans", "sidebar_expanded": True}},
     "Same ontology with ui.term_index = both, sans-serif text, expanded sidebar"),
    ("pizza-multi", FIX / "pizza-v2.ttl", {"layout": "multi", "previous_version": str(FIX / "pizza.ttl")},
     "Same ontology, multi-page layout"),
    ("linkml-personinfo", FIX / "linkml" / "personinfo.yaml", {}, "LinkML schema (with an imported module)"),
    ("skos-colors", FIX / "colors-skos.ttl", {}, "SKOS concept scheme"),
    ("prov-o", FIX / "real" / "prov-o.ttl", {"evaluation": {"oops": "on"}}, "W3C PROV-O, with OOPS! evaluation"),
    ("foaf", FIX / "real" / "foaf.rdf", {}, "FOAF (RDF/XML)"),
    ("org", FIX / "real" / "org.ttl", {}, "W3C Organization ontology"),
    ("skos", FIX / "real" / "skos.rdf", {}, "W3C SKOS core"),
    ("dcat", FIX / "real" / "dcat.ttl", {}, "W3C DCAT 3"),
    # cross-domain interoperability (queries OLS and runs language models; slow on the first run)
    ("cdi-prov-o", FIX / "real" / "prov-o.ttl",
     {"evaluation": {"cdi": "on", "cdi_references": ["ols"], "cdi_domains": ["provenance"]}},
     "W3C PROV-O with the cross-domain interoperability score (OLS)"),
    ("cdi-sosa", FIX / "cdi" / "sosa.ttl",
     {"evaluation": {"cdi": "on", "cdi_references": ["ols", str(FIX / "real" / "prov-o.ttl")],
                     "cdi_domains": ["sensor"]}},
     "SOSA with the CDI score against OLS and a local reference ontology (PROV-O)"),
    ("cdi-soil", FIX / "cdi" / "toy_onto.ttl",
     {"evaluation": {"cdi": "on", "cdi_references": ["ols", str(FIX / "cdi" / "toy_ref.ttl"),
                                                     str(FIX / "cdi" / "toy_to_bfo.sssom.tsv")],
                     "cdi_domains": ["agriculture"]}},
     "Small soil-sensing ontology with the CDI score against OLS, a local ontology and an SSSOM mapping"),
]


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    rows = []
    for name, src, opts, desc in SITES:
        res = ontoreview.build(src, out=OUT / name, **opts)
        s = res.report.summary if res.report else {}
        rows.append((name, res.ontology.metadata.title or name, desc, len(res.ontology.terms), s))
        print(f"✓ {name:20} {len(res.ontology.terms):4} terms  {res.seconds:.2f}s")
    ontoreview.build_single_file(FIX / "pizza-v2.ttl", OUT / "pizza-single-file.html", competency_questions=CQ)
    print("✓ pizza-single-file.html")
    coll = build_collection(FIX / "real", OUT / "collection")
    print(f"✓ collection             {len(coll.ok)} ontologies  {coll.seconds:.2f}s")
    export_collection(FIX / "real", OUT / "collection-markdown")
    print("✓ collection-markdown")
    for fmt, myst in (("markdown", False), ("myst", True)):
        cfg = resolve_config(FIX / "pizza.ttl")
        export_markdown(extract(load(cfg), cfg), OUT / f"export-{fmt}" , myst=myst)
        print(f"✓ export-{fmt}")
    items = "\n".join(
        f'<li><a href="{n}/index.html"><b>{html.escape(t)}</b></a> <span>{html.escape(d)} · {c} terms · '
        f'{s.get("error", 0)} errors / {s.get("warning", 0)} warnings</span></li>'
        for n, t, d, c, s in rows
    )
    (OUT / "index.html").write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>OntoReview examples</title>
<style>body{{font:17px/1.6 "Iowan Old Style",Palatino,Georgia,serif;max-width:46rem;margin:56px auto;padding:0 16px;color:#1c1b18;background:#fbfaf7}}
h1{{font-weight:600}} ul{{list-style:none;padding:0;border-top:1px solid #d9d4c7}} li{{padding:.6rem 0;border-bottom:1px solid #d9d4c7}}
span{{color:#6e6a60;font:14px -apple-system,Segoe UI,Arial,sans-serif;display:block}} a{{color:#1d4f91;text-decoration:none}}</style>
</head><body><h1>OntoReview examples</h1><ul>{items}
<li><a href="collection/index.html"><b>Folder of ontologies</b></a><span>ontoreview build tests/fixtures/real: PROV-O, FOAF, ORG, SKOS and DCAT, one sub-site each plus an index page</span></li>
<li><a href="collection-markdown/index.md"><b>Folder export (Markdown)</b></a><span>ontoreview export on the same folder: one sub-folder per ontology plus index.md</span></li>
<li><a href="pizza-single-file.html"><b>Single-file export</b></a><span>One self-contained HTML file (what Export HTML in the studio produces)</span></li>
<li><a href="pizza/llms.txt"><b>llms.txt</b></a><span>Index for LLMs and agents; see also pizza/ontology.json and pizza/llms-full.txt</span></li>
<li><a href="export-markdown/index.md"><b>Markdown export</b></a><span>For MkDocs / Docusaurus</span></li>
<li><a href="export-myst/index.md"><b>MyST export</b></a><span>For Sphinx</span></li></ul></body></html>""", "utf-8")


if __name__ == "__main__":
    main()
