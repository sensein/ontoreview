"""Logic behind ``ontoreview-ui``: settings, running a task, TOML import/export, file browsing.

Kept free of NiceGUI so it can be tested and reused; ``ontoreview.ui`` is only the page.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import sys
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Literal

from .collection import RDF_SUFFIXES, UNSUPPORTED, find_ontologies
from .linkml import is_linkml_file

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

log = logging.getLogger(__name__)

Task = Literal["site", "single", "markdown", "myst", "check"]
TASKS: dict[str, str] = {
    "site": "Website",
    "single": "Single HTML file",
    "markdown": "Markdown",
    "myst": "MyST (Sphinx)",
    "check": "Quality check",
}
SETTINGS_FILE = Path(os.environ.get("ONTOREVIEW_UI_SETTINGS",
                                    Path.home() / ".config" / "ontoreview" / "ui.json"))


@dataclass
class Settings:
    source: str = ""
    output: str = ""
    task: Task = "site"
    layout: Literal["single", "multi"] = "single"
    languages: str = "en"
    base_url: str = ""
    reason: bool = False
    load_imports: bool = True
    include_individuals: bool = True
    competency_questions: str = ""
    previous_version: str = ""
    robot: Literal["auto", "on", "off"] = "auto"
    oops: Literal["auto", "on", "off"] = "auto"
    fail_on: Literal["error", "warning", "info", "never"] = "error"

    # -------------------------------------------------------------- derived
    @property
    def source_path(self) -> Path | None:
        s = self.source.strip()
        if not s or s.startswith(("http://", "https://")):
            return None
        return Path(s).expanduser()

    @property
    def is_folder(self) -> bool:
        p = self.source_path
        return bool(p and p.is_dir())

    def default_output(self) -> str:
        base = self.source_path.parent if self.source_path and not self.is_folder else (self.source_path or Path.cwd())
        name = {"site": "docs", "single": "docs", "markdown": "docs-md", "myst": "docs-myst",
                "check": "quality"}[self.task]
        if self.task == "single" and not self.is_folder:
            stem = self.source_path.stem if self.source_path else "ontology"
            return str(base / f"{stem}.html")
        if self.task == "check":
            return str(base / "quality.json")
        return str(base / name)

    def output_path(self) -> Path:
        return Path((self.output or self.default_output()).strip()).expanduser()

    def overrides(self) -> dict[str, Any]:
        """Keyword overrides for ``ontoreview.build`` and friends."""
        ov: dict[str, Any] = {
            "layout": self.layout,
            "reason": self.reason,
            "load_imports": self.load_imports,
            "include_individuals": self.include_individuals,
            "evaluation": {"robot": self.robot, "oops": self.oops},
        }
        langs = [x.strip() for x in self.languages.split(",") if x.strip()]
        if langs and langs != ["en"]:
            ov["languages"] = langs
        if self.base_url.strip():
            ov["base_url"] = self.base_url.strip()
        if not self.is_folder:
            if self.competency_questions.strip():
                ov["competency_questions"] = [str(Path(c.strip()).expanduser().resolve())
                                              for c in self.competency_questions.split(",") if c.strip()]
            if self.previous_version.strip():
                ov["previous_version"] = self.previous_version.strip()
        return ov

    def validate(self) -> list[str]:
        problems = []
        s = self.source.strip()
        if not s:
            problems.append("Choose an ontology file or a folder of ontologies.")
        elif not s.startswith(("http://", "https://")) and not Path(s).expanduser().exists():
            problems.append(f"Source not found: {s}")
        for label, val in (("Competency questions", self.competency_questions),
                           ("Previous version", self.previous_version)):
            for v in [x.strip() for x in val.split(",") if x.strip()]:
                if not v.startswith(("http://", "https://")) and not Path(v).expanduser().exists():
                    problems.append(f"{label} file not found: {v}")
        return problems

    # -------------------------------------------------------------- CLI / TOML
    def cli(self) -> str:
        """The equivalent ``ontoreview`` command line."""
        q = shlex.quote
        cmd = {"site": ["ontoreview", "build"], "single": ["ontoreview", "build", "--single-file"],
               "markdown": ["ontoreview", "export", "--format", "markdown"],
               "myst": ["ontoreview", "export", "--format", "myst"],
               "check": ["ontoreview", "check", "--format", "json"]}[self.task]
        args = cmd + [q(self.source or "<source>"), "-o", q(str(self.output_path()))]
        if self.task in ("site", "single"):
            if self.layout != "single":
                args += ["--layout", self.layout]
            if self.languages.strip() and self.languages.strip() != "en":
                args += ["--lang", q(self.languages.replace(" ", ""))]
            if self.base_url.strip():
                args += ["--base-url", q(self.base_url.strip())]
            if self.reason:
                args.append("--reason")
            if not self.load_imports:
                args.append("--no-imports")
            if not self.include_individuals:
                args.append("--no-individuals")
            if not self.is_folder and self.previous_version.strip():
                args += ["--previous", q(self.previous_version.strip())]
        if self.task in ("site", "single", "check"):
            if not self.is_folder:
                for c in [x.strip() for x in self.competency_questions.split(",") if x.strip()]:
                    args += ["--cq", q(c)]
            if self.robot != "auto":
                args += ["--robot", self.robot]
            if self.oops != "auto":
                args.append("--oops" if self.oops == "on" else "--no-oops")
        if self.task == "check" and self.fail_on != "error":
            args += ["--fail-on", self.fail_on]
        return " ".join(args)

    def to_toml(self) -> str:
        """An ``ontoreview.toml`` with these settings (paths relative to where it is saved)."""
        def s(v: str) -> str:
            return json.dumps(v, ensure_ascii=False)  # TOML basic strings share JSON escaping

        langs = [x.strip() for x in self.languages.split(",") if x.strip()] or ["en"]
        lines = ["# ontoreview configuration, saved by ontoreview-ui",
                 f"source = {s(self.source)}", f"output = {s(str(self.output_path()))}",
                 f"layout = {s(self.layout)}", f"languages = [{', '.join(s(x) for x in langs)}]",
                 f"reason = {str(self.reason).lower()}", f"load_imports = {str(self.load_imports).lower()}",
                 f"include_individuals = {str(self.include_individuals).lower()}"]
        if self.base_url.strip():
            lines.append(f"base_url = {s(self.base_url.strip())}")
        if self.previous_version.strip():
            lines.append(f"previous_version = {s(self.previous_version.strip())}")
        cqs = [x.strip() for x in self.competency_questions.split(",") if x.strip()]
        if cqs:
            lines.append(f"competency_questions = [{', '.join(s(x) for x in cqs)}]")
        lines += ["", "[evaluation]", f"robot = {s(self.robot)}", f"oops = {s(self.oops)}", ""]
        return "\n".join(lines)

    @classmethod
    def from_toml(cls, path: str | Path) -> Settings:
        p = Path(path).expanduser()
        raw = tomllib.loads(p.read_text("utf-8"))
        if p.name == "pyproject.toml":
            raw = raw.get("tool", {}).get("ontoreview", {})
        base = p.parent.resolve()

        def rel(v: str) -> str:
            return v if not v or v.startswith(("http://", "https://")) or Path(v).is_absolute() else str(base / v)

        ev = raw.get("evaluation", {})
        oops = ev.get("oops", "auto")
        oops = {True: "on", False: "off"}.get(oops, oops) if isinstance(oops, bool) else oops
        return cls(
            source=rel(raw.get("source", "")), output=rel(raw.get("output", "")),
            layout=raw.get("layout", "single"), languages=", ".join(raw.get("languages", ["en"])),
            base_url=raw.get("base_url", "") or "", reason=bool(raw.get("reason", False)),
            load_imports=bool(raw.get("load_imports", True)),
            include_individuals=bool(raw.get("include_individuals", True)),
            competency_questions=", ".join(rel(c) for c in raw.get("competency_questions", [])),
            previous_version=rel(raw.get("previous_version", "") or ""),
            robot=ev.get("robot", "auto"), oops=oops,
        )

    # -------------------------------------------------------------- persistence
    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2), "utf-8")
        except OSError as e:  # settings are a convenience; never fail a run over them
            log.debug("could not save UI settings: %s", e)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or SETTINGS_FILE
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        try:
            return cls(**{k: v for k, v in data.items() if k in known})
        except TypeError:
            return cls()


# ------------------------------------------------------------------ running
@dataclass
class Row:
    name: str                       # source file, relative to the folder
    title: str = ""
    terms: int = 0
    errors: int = 0
    warnings: int = 0
    suggestions: int = 0
    external: str = ""              # "ROBOT: 4 errors" / "OOPS!: failed (…)"
    output: str = ""                # file to open (index.html / index.md / report)
    problem: str | None = None


@dataclass
class TaskResult:
    task: str
    output: Path
    rows: list[Row] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    index: str | None = None        # landing page for folders
    seconds: float = 0.0

    @property
    def ok(self) -> int:
        return sum(1 for r in self.rows if not r.problem)


def _external_text(reports) -> str:
    parts = []
    for x in reports:
        if isinstance(x, dict):
            tool, problem, summ = x["tool"], x.get("problem"), x.get("summary", {})
        else:
            tool, problem, summ = x.tool, x.error, x.summary
        parts.append(f"{tool}: failed ({problem})" if problem else
                     f"{tool}: {summ.get('error', 0)} errors, {summ.get('warning', 0)} warnings")
    return "; ".join(parts)


def run_task(settings: Settings) -> TaskResult:
    """Run the chosen task for a file or a folder. Blocking; call it off the UI thread."""
    from .build import build, build_single_file, check, load, resolve_config
    from .collection import build_collection, export_collection
    from .export import export_markdown
    from .model.extract import extract

    problems = settings.validate()
    if problems:
        raise ValueError(" ".join(problems))
    t0 = time.perf_counter()
    s = settings
    out = s.output_path()
    src = s.source.strip()
    src = src if src.startswith(("http://", "https://")) else str(Path(src).expanduser().resolve())
    ov = s.overrides()
    res = TaskResult(s.task, out)

    if s.is_folder and s.task in ("site", "single"):
        coll = build_collection(src, out, single_file=s.task == "single", **ov)
        res.rows = [_row_from_entry(e, out, "index.html") for e in coll.entries]
        res.skipped, res.index = coll.skipped, str(out / "index.html")
    elif s.is_folder and s.task in ("markdown", "myst"):
        coll = export_collection(src, out, myst=s.task == "myst")
        res.rows = [_row_from_entry(e, out, "index.md") for e in coll.entries]
        res.skipped, res.index = coll.skipped, str(out / "index.md")
    elif s.task == "check":
        files = [Path(src)] if not s.is_folder else find_ontologies(src)[0]
        report_json: dict[str, Any] = {}
        for f in files:
            name = f.name if not s.is_folder else f.relative_to(Path(src)).as_posix()
            try:
                onto, rep = check(f, **{k: v for k, v in ov.items()
                                        if k in ("evaluation", "competency_questions", "load_imports",
                                                 "include_individuals", "reason")})
                sm = rep.summary
                res.rows.append(Row(name, onto.metadata.title or f.stem, len(onto.terms), sm["error"],
                                    sm["warning"], sm["info"], _external_text(rep.external)))
                report_json[name] = json.loads(rep.to_json())
            except Exception as e:  # noqa: BLE001
                res.rows.append(Row(name, problem=str(e)))
                report_json[name] = {"error": str(e)}
        if out.suffix.lower() != ".json":
            out = out / "quality.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report_json, indent=2, ensure_ascii=False), "utf-8")
        for r in res.rows:
            r.output = str(out)
        res.output = out
    elif s.task in ("markdown", "myst"):
        cfg = resolve_config(src)
        onto = extract(load(cfg), cfg)
        written = export_markdown(onto, out, myst=s.task == "myst")
        res.rows = [Row(Path(src).name, onto.metadata.title or Path(src).stem, len(onto.terms),
                        output=str(out / "index.md"))]
        res.index = str(out / "index.md") if (out / "index.md").exists() else (str(written[0]) if written else None)
    else:
        if s.task == "single":
            target = out if out.suffix.lower() == ".html" else out / "index.html"
            b = build_single_file(src, target, **ov)
            page = target
        else:
            b = build(src, out=out, **ov)
            page = out / "index.html"
        sm = b.report.summary if b.report else {"error": 0, "warning": 0, "info": 0}
        res.rows = [Row(Path(src).name, b.ontology.metadata.title or Path(src).stem, len(b.ontology.terms),
                        sm["error"], sm["warning"], sm["info"],
                        _external_text(b.report.external if b.report else []), str(page))]
        res.index = str(page)
    res.seconds = time.perf_counter() - t0
    return res


def _row_from_entry(e, out: Path, page: str) -> Row:
    q = e.quality or {}
    return Row(e.source, e.title, e.terms, q.get("error", 0), q.get("warning", 0), q.get("info", 0),
               _external_text(e.external), str(out / e.slug / page) if not e.error else "", e.error)


# ------------------------------------------------------------------ browsing
@dataclass
class Listing:
    path: str
    parent: str | None
    dirs: list[str]
    files: list[str]


def is_ontology_file(p: Path) -> bool:
    suf = p.suffix.lower()
    return suf in RDF_SUFFIXES or suf == ".json" or suf in UNSUPPORTED or is_linkml_file(p)


def browse(path: str | Path | None, kinds: Literal["ontology", "cq", "toml", "any"] = "ontology",
           show_hidden: bool = False) -> Listing:
    """Directory listing for the server-side file picker (the UI runs on this machine)."""
    p = Path(path).expanduser() if path else Path.cwd()
    if p.is_file():
        p = p.parent
    if not p.is_dir():
        p = Path.cwd()
    p = p.resolve()
    dirs, files = [], []
    try:
        entries = sorted(p.iterdir(), key=lambda x: x.name.lower())
    except OSError:
        entries = []
    for e in entries:
        if not show_hidden and e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                dirs.append(e.name)
            elif kinds == "any" or (
                kinds == "ontology" and is_ontology_file(e)) or (
                kinds == "cq" and e.suffix.lower() in {".yaml", ".yml", ".json", ".csv", ".tsv", ".xlsx"}) or (
                kinds == "toml" and e.suffix.lower() == ".toml"):
                files.append(e.name)
        except OSError:
            continue
    return Listing(str(p), str(p.parent) if p.parent != p else None, dirs, files)


def describe_source(source: str) -> str:
    """One line for the UI: what was picked and what will be documented."""
    s = source.strip()
    if not s:
        return "No source chosen yet."
    if s.startswith(("http://", "https://")):
        return "Ontology URL."
    p = Path(s).expanduser()
    if p.is_dir():
        found, skipped = find_ontologies(p)
        msg = f"Folder with {len(found)} ontolog{'y' if len(found) == 1 else 'ies'}"
        return msg + (f" ({len(skipped)} unsupported file{'s' if len(skipped) != 1 else ''} will be skipped)." if skipped else ".")
    if p.is_file():
        return f"Single ontology: {p.name}." if is_ontology_file(p) else f"{p.name} does not look like an ontology file."
    return "Not found."


# ------------------------------------------------------------------ run history
HISTORY_FILE = SETTINGS_FILE.with_name("history.json")
HISTORY_LIMIT = 200


@dataclass
class HistoryEntry:
    id: str
    when: float                    # unix time
    task: str
    source: str
    output: str
    index: str | None
    ok: int
    total: int
    errors: int
    warnings: int
    seconds: float
    settings: dict[str, Any]
    failed: str | None = None      # the run raised before producing anything

    @property
    def exists(self) -> bool:
        return Path(self.output).exists()

    def matches(self, text: str = "", task: str = "all") -> bool:
        if task != "all" and self.task != task:
            return False
        t = text.strip().lower()
        return not t or any(t in str(v).lower() for v in (self.source, self.output, TASKS.get(self.task, self.task)))


def load_history(path: Path | None = None) -> list[HistoryEntry]:
    path = path or HISTORY_FILE
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    known = {f.name for f in fields(HistoryEntry)}
    out = []
    for d in data if isinstance(data, list) else []:
        try:
            out.append(HistoryEntry(**{k: v for k, v in d.items() if k in known}))
        except TypeError:
            continue
    return sorted(out, key=lambda e: e.when, reverse=True)


def record_run(settings: Settings, result: TaskResult | None, error: str | None = None,
               path: Path | None = None) -> HistoryEntry:
    """Append a run to the history file (newest first, capped)."""
    import uuid

    path = path or HISTORY_FILE
    r = result
    entry = HistoryEntry(
        id=uuid.uuid4().hex[:12], when=time.time(), task=settings.task, source=settings.source,
        output=str(r.output if r else settings.output_path()), index=r.index if r else None,
        ok=r.ok if r else 0, total=len(r.rows) if r else 0,
        errors=sum(x.errors for x in r.rows) if r else 0, warnings=sum(x.warnings for x in r.rows) if r else 0,
        seconds=round(r.seconds, 2) if r else 0.0, settings=asdict(settings), failed=error)
    entries = [entry] + load_history(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(e) for e in entries[:HISTORY_LIMIT]], indent=1), "utf-8")
    except OSError as e:
        log.debug("could not save run history: %s", e)
    return entry


def forget_run(entry_id: str, path: Path | None = None) -> None:
    path = path or HISTORY_FILE
    entries = [e for e in load_history(path) if e.id != entry_id]
    try:
        path.write_text(json.dumps([asdict(e) for e in entries], indent=1), "utf-8")
    except OSError:
        pass


def open_in_file_manager(path: str | Path) -> None:
    """Show a folder (or the folder containing a file) in Finder / Explorer / the file manager."""
    import subprocess

    p = Path(path).expanduser()
    target = p if p.is_dir() else p.parent
    if not target.exists():
        raise FileNotFoundError(f"{target} no longer exists")
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    elif sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(target)])


def existing_output(path: str | Path) -> dict[str, Any] | None:
    """Describe OntoReview output already at ``path`` (from the UI or the CLI), if any."""
    p = Path(path).expanduser()
    if not p.exists():
        return None
    if p.is_file():
        return {"kind": "file", "index": str(p), "when": p.stat().st_mtime, "count": 1}
    manifest = p / "collection.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text("utf-8"))
            n = sum(1 for o in data.get("ontologies", []) if not o.get("error"))
        except (OSError, ValueError):
            n = 0
        index = p / "index.html" if (p / "index.html").exists() else p / "index.md"
        return {"kind": "folder", "index": str(index), "when": manifest.stat().st_mtime, "count": n}
    for name in ("index.html", "index.md", "quality.json"):
        f = p / name
        if f.is_file():
            if name == "index.html" and "OntoReview" not in f.read_text("utf-8", "replace")[:4000] \
                    and "ontoreview" not in f.read_text("utf-8", "replace")[:4000]:
                continue
            return {"kind": "single", "index": str(f), "when": f.stat().st_mtime, "count": 1}
    return None
