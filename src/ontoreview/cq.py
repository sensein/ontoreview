"""Competency questions: load them from YAML / JSON / CSV / TSV / Excel, run their SPARQL
queries against the ontology (plus optional example data) and report which ones are answerable.

YAML example::

    prefixes: {ex: "https://example.org/data/"}     # optional; ontology prefixes are added automatically
    example_data: [examples/data.ttl]                # optional; loaded for every question
    questions:
      - id: CQ1
        question: Which pizzas have a meat topping?
        sparql: |
          SELECT ?pizza WHERE { ?pizza pizza:hasTopping/a pizza:MeatTopping }
        answer: Pepperoni                            # optional expected answer (shown, not enforced)
        terms: [pizza:Pizza, pizza:hasTopping]       # optional; terms used in the query are found anyway
        notes: Derived from the user study.

Spreadsheets (CSV/TSV/XLSX) use one row per question with the columns
``id, question, sparql, answer, terms, notes, example_data`` (header names are matched loosely).
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rdflib import Graph, Literal, URIRef

from .model.entities import Ontology, Ref

COLUMN_ALIASES = {
    "id": {"id", "cq", "cq id", "cqid", "identifier", "no", "number", "#"},
    "question": {"question", "competency question", "cq text", "text", "competency_question"},
    "sparql": {"sparql", "query", "sparql query", "sparql_query"},
    "answer": {"answer", "expected answer", "expected", "expected_answer", "expected result"},
    "terms": {"terms", "related terms", "concepts", "entities", "ontology terms", "related_terms"},
    "notes": {"notes", "note", "comment", "comments", "description", "rationale", "source"},
    "example_data": {"example data", "example_data", "data", "examples", "test data"},
    "status": {"status", "priority"},
}
TEMPLATE_COLUMNS = ["id", "question", "sparql", "answer", "terms", "notes", "example_data"]


@dataclass
class CompetencyQuestion:
    id: str
    question: str
    sparql: str | None = None
    answer: str | None = None
    terms: list[str] = field(default_factory=list)
    notes: str | None = None
    example_data: list[str] = field(default_factory=list)
    priority: str | None = None
    anchor: str = ""
    # filled by evaluate()
    status: str = "untested"  # passed | failed | error | untested
    error: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    total_rows: int = 0
    term_refs: list[Ref] = field(default_factory=list)


@dataclass
class CQSet:
    questions: list[CompetencyQuestion] = field(default_factory=list)
    prefixes: dict[str, str] = field(default_factory=dict)
    example_data: list[str] = field(default_factory=list)
    base_dir: Path = field(default_factory=Path.cwd)

    @property
    def summary(self) -> dict[str, int]:
        out = {"passed": 0, "failed": 0, "error": 0, "untested": 0}
        for q in self.questions:
            out[q.status] += 1
        return out


# ------------------------------------------------------------------ loading
def _split_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[;,\n]", str(v)) if x.strip()]


def _norm_header(h) -> str | None:
    key = re.sub(r"\s+", " ", str(h or "").strip().lower().replace("_", " "))
    for field_name, aliases in COLUMN_ALIASES.items():
        if key in aliases or key.replace(" ", "_") in aliases:
            return field_name
    return None


def _from_records(records: list[dict]) -> list[CompetencyQuestion]:
    out = []
    for i, rec in enumerate(records, 1):
        norm: dict = {}
        for k, v in rec.items():
            f = _norm_header(k) if k not in TEMPLATE_COLUMNS else k
            if f and v not in (None, ""):
                norm[f] = v
        question = str(norm.get("question", "")).strip()
        if not question and not norm.get("sparql"):
            continue
        qid = str(norm.get("id") or f"CQ{i}").strip()
        if re.fullmatch(r"\d+(\.0)?", qid):
            qid = f"CQ{int(float(qid))}"
        out.append(CompetencyQuestion(
            id=qid,
            question=question or qid,
            sparql=str(norm["sparql"]).strip() if norm.get("sparql") else None,
            answer=str(norm["answer"]).strip() if norm.get("answer") is not None else None,
            terms=_split_list(norm.get("terms")),
            notes=str(norm["notes"]).strip() if norm.get("notes") else None,
            example_data=_split_list(norm.get("example_data")),
            priority=str(norm["status"]).strip() if norm.get("status") else None,
        ))
    return out


def _read_rows_xlsx(path: Path) -> list[dict]:
    try:
        import openpyxl
    except ImportError as e:  # pragma: no cover
        raise ImportError("Reading Excel competency questions needs openpyxl: pip install 'ontoreview[excel]'") from e
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["questions"] if "questions" in wb.sheetnames else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(h or "") for h in rows[0]]
    return [dict(zip(header, r, strict=False)) for r in rows[1:] if any(c not in (None, "") for c in r)]


def load_cqs(path: str | Path) -> CQSet:
    path = Path(path)
    suffix = path.suffix.lower()
    cqset = CQSet(base_dir=path.parent)
    if suffix in (".yaml", ".yml", ".json"):
        data = yaml.safe_load(path.read_text("utf-8")) if suffix != ".json" else json.loads(path.read_text("utf-8"))
        if isinstance(data, list):
            records = data
        else:
            data = data or {}
            records = data.get("questions") or data.get("competency_questions") or []
            cqset.prefixes = {str(k): str(v) for k, v in (data.get("prefixes") or {}).items()}
            cqset.example_data = _split_list(data.get("example_data"))
        cqset.questions = _from_records([r if isinstance(r, dict) else {"question": r} for r in records])
    elif suffix in (".csv", ".tsv"):
        text = path.read_text("utf-8-sig")
        delim = "\t" if suffix == ".tsv" else (csv.Sniffer().sniff(text[:4096], ",;\t").delimiter
                                               if text.strip() else ",")
        cqset.questions = _from_records(list(csv.DictReader(text.splitlines(), delimiter=delim)))
    elif suffix in (".xlsx", ".xlsm"):
        cqset.questions = _from_records(_read_rows_xlsx(path))
    else:
        raise ValueError(f"Unsupported competency question file: {path.name} "
                         "(use .yaml, .json, .csv, .tsv or .xlsx)")
    seen: dict[str, int] = {}
    for q in cqset.questions:
        base = re.sub(r"[^A-Za-z0-9_-]", "", q.id) or "cq"
        n = seen.get(base, 0)
        seen[base] = n + 1
        q.anchor = f"cq-{base}" + (f"-{n + 1}" if n else "")
    return cqset


def load_many(paths: list[str | Path]) -> CQSet:
    merged = CQSet()
    for p in paths:
        s = load_cqs(p)
        merged.questions += s.questions
        merged.prefixes.update(s.prefixes)
        merged.example_data += [str(s.base_dir / d) if not Path(d).is_absolute() else d
                                for d in s.example_data]
        for q in s.questions:
            q.example_data = [str(s.base_dir / d) if not Path(d).is_absolute() and not d.startswith("http") else d
                              for d in q.example_data]
        merged.base_dir = s.base_dir
    return merged


# ------------------------------------------------------------------ evaluation
def _short(value, onto: Ontology, prefixes: list[tuple[str, str]]) -> str:
    if isinstance(value, URIRef):
        s = str(value)
        t = onto.terms.get(s)
        if t is not None:
            return t.curie or t.label
        for p, ns in prefixes:
            if s.startswith(ns) and len(s) > len(ns):
                return f"{p}:{s[len(ns):]}"
        return s
    if isinstance(value, Literal):
        return str(value)
    return "" if value is None else str(value)


def evaluate(cqset: CQSet, graph: Graph, onto: Ontology, max_rows: int = 10) -> CQSet:
    ns = dict(onto.prefixes)
    ns.update(cqset.prefixes)
    prefixes = sorted(ns.items(), key=lambda x: -len(x[1]))
    cache: dict[tuple[str, ...], Graph] = {}

    def data_graph(extra: list[str]) -> Graph:
        key = tuple(cqset.example_data + extra)
        if key not in cache:
            g = Graph()
            g += graph
            for src in key:
                fmt = "turtle" if src.endswith(".ttl") else None
                g.parse(src, format=fmt)
            cache[key] = g
        return cache[key]

    iri_by_curie = {}
    for t in onto.terms.values():
        if t.curie:
            iri_by_curie[t.curie] = t.iri

    for q in cqset.questions:
        # terms: declared + detected in the query
        found: list[str] = []
        for term in q.terms:
            iri = iri_by_curie.get(term) or (term if term in onto.terms else None)
            if iri is None and ":" in term:
                p, _, local = term.partition(":")
                if p in ns:
                    iri = ns[p] + local
            if iri:
                found.append(iri)
        if q.sparql:
            for m in re.finditer(r"<([^>\s]+)>|\b([A-Za-z][\w-]*):([A-Za-z_][\w.-]*)", q.sparql):
                if m.group(1):
                    iri = m.group(1)
                elif m.group(2) in ns:
                    iri = ns[m.group(2)] + m.group(3)
                else:
                    continue
                if iri in onto.terms:
                    found.append(iri)
        seen: set[str] = set()
        q.term_refs = []
        for iri in found:
            if iri in seen:
                continue
            seen.add(iri)
            t = onto.terms.get(iri)
            q.term_refs.append(t.ref() if t is not None else Ref(iri, _short(URIRef(iri), onto, prefixes)))

        if not q.sparql:
            q.status = "untested"
            continue
        try:
            g = data_graph(q.example_data)
            res = g.query(q.sparql, initNs=ns)
        except Exception as e:  # noqa: BLE001
            q.status, q.error = "error", " ".join(str(e).split())[:400]
            continue
        if res.type == "ASK":
            q.columns, q.rows, q.total_rows = ["answer"], [[str(bool(res.askAnswer)).lower()]], 1
            q.status = "passed" if res.askAnswer else "failed"
        elif res.type in ("CONSTRUCT", "DESCRIBE"):
            triples = list(res.graph) if res.graph is not None else []
            q.columns = ["subject", "predicate", "object"]
            q.rows = [[_short(x, onto, prefixes) for x in tr] for tr in triples[:max_rows]]
            q.total_rows = len(triples)
            q.status = "passed" if triples else "failed"
        else:
            rows = list(res)
            q.columns = [str(v) for v in (res.vars or [])]
            q.rows = [[_short(v, onto, prefixes) for v in r] for r in rows[:max_rows]]
            q.total_rows = len(rows)
            q.status = "passed" if rows else "failed"
    return cqset


def attach_backlinks(cqset: CQSet, onto: Ontology) -> None:
    for q in cqset.questions:
        for r in q.term_refs:
            t = onto.terms.get(r.iri)
            if t is not None and (q.id, q.anchor) not in t.competency_questions:
                t.competency_questions.append((q.id, q.anchor))


# ------------------------------------------------------------------ templates
TEMPLATE_ROWS = [
    {"id": "CQ1", "question": "Which classes does the ontology define?",
     "sparql": "SELECT ?class WHERE { ?class a owl:Class . FILTER(isIRI(?class)) }",
     "answer": "", "terms": "", "notes": "Replace with your own questions.", "example_data": ""},
]


def write_template(path: str | Path) -> Path:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        path.write_text(
            "# Competency questions for ontoreview. Every query runs against the ontology\n"
            "# (plus example_data); questions with no results are flagged.\n"
            "example_data: []\n"
            "questions:\n"
            "  - id: CQ1\n"
            "    question: Which classes does the ontology define?\n"
            "    sparql: |\n"
            "      SELECT ?class WHERE { ?class a owl:Class . FILTER(isIRI(?class)) }\n"
            "    answer: \n"
            "    terms: []\n"
            "    notes: Replace with your own questions.\n", "utf-8")
    elif suffix in (".csv", ".tsv"):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, TEMPLATE_COLUMNS, delimiter="\t" if suffix == ".tsv" else ",")
            w.writeheader()
            w.writerows(TEMPLATE_ROWS)
    elif suffix == ".xlsx":
        import openpyxl
        from openpyxl.styles import Alignment, Font

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "questions"
        ws.append(TEMPLATE_COLUMNS)
        for r in TEMPLATE_ROWS:
            ws.append([r[c] for c in TEMPLATE_COLUMNS])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        widths = {"A": 8, "B": 48, "C": 60, "D": 24, "E": 28, "F": 32, "G": 24}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        wb.save(path)
    else:
        raise ValueError("Template must be .yaml, .csv, .tsv or .xlsx")
    return path
