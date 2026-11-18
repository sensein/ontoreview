"""Rebuild the bundled IRI term snapshot (src/ontoreview/data/iri/top_terms.sqlite3).

    uv run python scripts/build_iri_bundle.py [--ids prov sosa ...]

Downloads each selected catalog vocabulary (content negotiation), indexes its typed subjects and
writes the database plus top_terms.manifest.json. The bundle is replaced only after every vocabulary
succeeds. Adapted from the ontology_quality reference implementation (build_bundle.py).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ontoreview.quality_checks.iri import load_catalog
from ontoreview.quality_checks.iri.store import TermStore
from ontoreview.quality_checks.iri.validate import download_graph

DATA = Path(__file__).resolve().parent.parent / "src" / "ontoreview" / "data" / "iri"
DEFAULT_IDS = ["prov", "sosa", "ssn", "time", "skos", "org", "dcat", "dqv", "odrl", "qb"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    parser.add_argument("--output", type=Path, default=DATA / "top_terms.sqlite3")
    args = parser.parse_args()
    by_id = {e["id"]: e for e in load_catalog()}
    if set(args.ids) - by_id.keys():
        parser.error("Unknown catalog IDs: " + ", ".join(sorted(set(args.ids) - by_id.keys())))
    staging = args.output.with_suffix(".building.sqlite3")
    staging.unlink(missing_ok=True)
    store = TermStore(staging)
    manifest = []
    try:
        for id_ in args.ids:
            entry = by_id[id_]
            print(f"Downloading {id_}…", flush=True)
            graph, url, payload = download_graph([entry["download_url"], entry["ontology_iri"]])
            count = store.save(entry["ontology_iri"], graph, url, payload)
            if not count:
                raise ValueError(f"{id_}: no typed terms in downloaded graph")
            manifest.append({**entry, "typed_subject_count": count, "snapshot": store.document(entry["ontology_iri"])})
            print(f"  {count} typed subjects", flush=True)
        # the bundle is read-only and stays at schema version 1 (no run-tracking tables needed)
        with store.db:
            store.db.execute("DROP TABLE IF EXISTS run_results")
            store.db.execute("DROP TABLE IF EXISTS runs")
            store.db.execute("PRAGMA user_version=1")
        store.db.execute("VACUUM")
    finally:
        store.close()
    os.replace(staging, args.output)
    args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Built {args.output}")


if __name__ == "__main__":
    main()
