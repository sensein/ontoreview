"""SQLite term snapshots and run tracking.

Adapted from the ``ontology_quality`` reference implementation (``term_store.py``).

* The **bundled** database (``ontoreview/data/iri/top_terms.sqlite3``) is opened read-only.
* The **writable** database (the user cache, :func:`default_cache_path`) holds downloaded
  snapshots, positive repository (OLS/BioPortal) results and, since schema version 2, a record of
  every IRI-check run (``runs`` / ``run_results``).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

SCHEMA_VERSION = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 key TEXT PRIMARY KEY, source_url TEXT NOT NULL, fetched_at TEXT NOT NULL,
 sha256 TEXT NOT NULL, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terms (
 document_key TEXT NOT NULL REFERENCES documents(key) ON DELETE CASCADE,
 iri TEXT NOT NULL, types TEXT NOT NULL, labels TEXT NOT NULL, deprecated INTEGER NOT NULL,
 PRIMARY KEY(document_key, iri));
CREATE INDEX IF NOT EXISTS term_iri ON terms(iri);
CREATE TABLE IF NOT EXISTS repository_terms (
 iri TEXT NOT NULL, roles TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(iri, roles));
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, finished_at TEXT,
 source TEXT, ontology_iri TEXT, settings TEXT NOT NULL, summary TEXT);
CREATE TABLE IF NOT EXISTS run_results (
 run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 iri TEXT NOT NULL, roles TEXT NOT NULL, status TEXT NOT NULL, source TEXT,
 detail TEXT, attempts TEXT, PRIMARY KEY(run_id, iri));
CREATE INDEX IF NOT EXISTS run_results_iri ON run_results(iri);
"""
KEEP_RUNS = 500


def default_cache_path() -> Path:
    """Writable database: the platform cache folder, or ``$ONTOREVIEW_IRI_DB``."""
    if os.environ.get("ONTOREVIEW_IRI_DB"):
        return Path(os.environ["ONTOREVIEW_IRI_DB"]).expanduser()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "ontoreview" / "iri.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TermStore:
    def __init__(self, path, readonly: bool = False):
        path = Path(path)
        self.path = path
        if readonly:
            self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, SCHEMA_VERSION) or (readonly and version not in (1, SCHEMA_VERSION)):
            raise ValueError(f"Unsupported term database schema: {version}")
        if not readonly:
            self.db.executescript(SCHEMA)
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------ term cache
    def repository_term(self, iri, roles):
        row = self.db.execute("SELECT payload FROM repository_terms WHERE iri=? AND roles=?",
                              (iri, json.dumps(sorted(roles)))).fetchone()
        return json.loads(row[0]) if row else None

    def save_repository_term(self, iri, roles, result) -> None:
        # Positive records only, scoped to the exact term and checked roles.
        if result.get("status") not in ("valid", "deprecated") or result.get("iri") != iri:
            raise ValueError("Only exact positive repository results can be cached")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO repository_terms VALUES (?,?,?)",
                            (iri, json.dumps(sorted(roles)), json.dumps(result)))

    def document(self, key):
        row = self.db.execute("SELECT * FROM documents WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None

    def lookup(self, key, iri):
        row = self.db.execute("SELECT * FROM terms WHERE document_key=? AND iri=?", (key, iri)).fetchone()
        if not row:
            return None
        result = dict(row)
        for f in ("types", "labels"):
            result[f] = json.loads(result[f])
        result["deprecated"] = bool(result["deprecated"])
        return result

    def save(self, key, graph, source_url, payload) -> int:
        metadata = {
            "ontology_iris": sorted(str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)),
            "version_iris": sorted(str(o) for o in graph.objects(None, OWL.versionIRI)),
            "imports_not_loaded": sorted(str(o) for o in graph.objects(None, OWL.imports)),
            "licenses": sorted({str(o) for p in ("http://purl.org/dc/terms/license", "http://creativecommons.org/ns#license")
                                for o in graph.objects(None, URIRef(p))}),
            "rights": sorted({str(o) for p in ("http://purl.org/dc/terms/rights", "http://purl.org/dc/elements/1.1/rights")
                              for o in graph.objects(None, URIRef(p))}),
        }
        rows = []
        # Typed subjects only: a mere mention as an object is not a declaration.
        for subject in set(graph.subjects(RDF.type, None)):
            if not isinstance(subject, URIRef):
                continue
            types = sorted({str(t) for t in graph.objects(subject, RDF.type) if isinstance(t, URIRef)})
            labels = sorted({str(v) for p in (RDFS.label, SKOS.prefLabel) for v in graph.objects(subject, p)})
            deprecated = any(str(v).lower() in ("true", "1") for v in graph.objects(subject, OWL.deprecated))
            rows.append((key, str(subject), json.dumps(types), json.dumps(labels), int(deprecated)))
        with self.db:
            self.db.execute("DELETE FROM documents WHERE key=?", (key,))
            self.db.execute("INSERT INTO documents VALUES (?,?,?,?,?)",
                            (key, source_url, _now(), hashlib.sha256(payload).hexdigest(), json.dumps(metadata)))
            self.db.executemany("INSERT INTO terms VALUES (?,?,?,?,?)", rows)
        return len(rows)

    def stats(self) -> dict[str, int]:
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {"documents": q("SELECT count(*) FROM documents"), "terms": q("SELECT count(*) FROM terms"),
                "repository_terms": q("SELECT count(*) FROM repository_terms"),
                "runs": q("SELECT count(*) FROM runs")}

    # ------------------------------------------------------------ run tracking
    def start_run(self, source: str | None, ontology_iri: str | None, settings: dict) -> int:
        with self.db:
            cur = self.db.execute("INSERT INTO runs(started_at, source, ontology_iri, settings) VALUES (?,?,?,?)",
                                  (_now(), source, ontology_iri, json.dumps(settings, sort_keys=True)))
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, results: list[dict], summary: dict, keep: int = KEEP_RUNS) -> None:
        rows = [(run_id, r["iri"], json.dumps(r.get("roles", [])), r["status"], r.get("snapshot") or r.get("provider"),
                 r.get("detail"), json.dumps(r.get("attempts", []))) for r in results]
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO run_results VALUES (?,?,?,?,?,?,?)", rows)
            self.db.execute("UPDATE runs SET finished_at=?, summary=? WHERE id=?",
                            (_now(), json.dumps(summary, sort_keys=True), run_id))
            self.db.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT ?)", (keep,))

    def recent_runs(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for f in ("settings", "summary"):
                d[f] = json.loads(d[f]) if d[f] else None
            out.append(d)
        return out

    def run_results(self, run_id: int) -> list[dict]:
        rows = self.db.execute("SELECT * FROM run_results WHERE run_id=? ORDER BY iri", (run_id,)).fetchall()
        return [dict(r) | {"roles": json.loads(r["roles"]), "attempts": json.loads(r["attempts"] or "[]")} for r in rows]
