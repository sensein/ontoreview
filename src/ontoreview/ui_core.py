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

Task = Literal["site", "single", "markdown", "myst", "check", "interop", "diff"]
TASKS: dict[str, str] = {
    "site": "Website",
    "single": "Single HTML file",
    "markdown": "Markdown",
    "myst": "MyST (Sphinx)",
    "check": "Quality check",
    "interop": "Interoperability check",
    "diff": "Compare versions",
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
    robot_path: str = ""            # a local `robot` command; empty = Docker
    robot_image: str = "obolibrary/robot"
    oops_timeout: int = 90
    oops_endpoint: str = ""
    reasoner: Literal["hermit", "elk", "off"] = "hermit"
    ontocheck: bool = True
    ontocheck_network: bool = True
    ontocheck_search: str = ""
    iri_checks: bool = True
    iri_network: bool = True
    iri_repositories: bool = True
    iri_resolve: bool = True
    cdi: bool = True                # cross-domain interoperability (on like every other check)
    cdi_references: str = "ols"     # one reference per line (a line may hold commas: ols:envo,chebi)
    cdi_domains: str = ""           # comma-separated
    cdi_generality: bool = True
    cdi_top_n: int = 10
    cdi_ontoaligner: Literal["off", "fuzzy", "sbert"] = "sbert"
    si: bool = True                 # scientific interoperability (same run and references as cdi)
    si_references: str = ""         # one per line; empty = the cross-domain references (same run)
    si_home_domain: str = ""        # OECD field code or name; empty = classify the ontology's title/description
    si_theta_s: float = 0.3
    si_domain_map: str = ""         # one per line: "ols:emi = 1.5; 1.6"
    cdi_bioportal_key: str = field(default="", repr=False)    # optional; never in the CLI line, TOML or history
    cdi_ontoportal_key: str = field(default="", repr=False)   # any other OntoPortal service
    hf_token: str = field(default="", repr=False)             # Hugging Face token for model downloads (optional)
    default_root: str = ""          # Settings > default output folder
    separate_runs: bool = True      # each docs run writes a new, self-contained folder (name-YYYYMMDD-HHMMSS)
    verbose: bool = False

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
        if self.default_root.strip():
            root = Path(self.default_root.strip()).expanduser()
            stem = (self.source_path.name if self.is_folder else self.source_path.stem) if self.source_path else "ontology"
            name = {"single": f"{stem}.html", "check": f"{stem}-quality.json", "interop": f"{stem}-interoperability.json",
                    "diff": f"{stem}-changes.md"}.get(self.task, stem)
            return str(root / name)
        base = self.source_path.parent if self.source_path and not self.is_folder else (self.source_path or Path.cwd())
        name = {"site": "docs", "single": "docs", "markdown": "docs-md", "myst": "docs-myst",
                "check": "quality", "interop": "interoperability", "diff": "changes"}[self.task]
        if self.task == "diff":
            return str(base / "changes.md")
        if self.task == "single" and not self.is_folder:
            stem = self.source_path.stem if self.source_path else "ontology"
            return str(base / f"{stem}.html")
        if self.task == "check":
            return str(base / "quality.json")
        if self.task == "interop":
            return str(base / "interoperability.json")
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
            "evaluation": self.evaluation(),
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

    def evaluation(self) -> dict[str, Any]:
        ev: dict[str, Any] = {"robot": self.robot, "oops": self.oops, "oops_timeout": int(self.oops_timeout or 90)}
        if self.robot_path.strip():
            ev["robot_path"] = self.robot_path.strip()
        if self.robot_image.strip() and self.robot_image.strip() != "obolibrary/robot":
            ev["robot_image"] = self.robot_image.strip()
        if self.reasoner != "hermit":
            ev["reasoner"] = self.reasoner
        if not self.ontocheck:
            ev["ontocheck"] = "off"
        if not self.ontocheck_network:
            ev["ontocheck_network"] = False
        if self.ontocheck_search.strip():
            ev["ontocheck_search"] = self.ontocheck_search.strip()
        if not self.iri_checks:
            ev["iri_checks"] = "off"
        for k in ("iri_network", "iri_repositories", "iri_resolve"):
            if not getattr(self, k):
                ev[k] = False
        if not self.cdi:
            ev["cdi"] = "off"
        if not self.si:
            ev["si"] = "off"
        else:
            if self.si_home_domain.strip():
                ev["si_home_domain"] = self.si_home_domain.strip()
            if float(self.si_theta_s or 0.3) != 0.3:
                ev["si_theta_s"] = float(self.si_theta_s)
            if self.si_domain_map_dict():
                ev["si_domain_map"] = self.si_domain_map_dict()
            if self.si_reference_list():
                ev["si_references"] = self.si_reference_list()
        if self.cdi or self.si:     # on by default: only what differs from the defaults (SI uses the same run)
            refs = self.cdi_reference_list()
            if refs != ["ols"]:
                ev["cdi_references"] = refs
            domains = [d.strip() for d in self.cdi_domains.split(",") if d.strip()]
            if domains:
                ev["cdi_domains"] = domains
            if not self.cdi_generality:
                ev["cdi_generality"] = False
            if int(self.cdi_top_n or 10) != 10:
                ev["cdi_top_n"] = int(self.cdi_top_n or 10)
            if self.cdi_ontoaligner != "sbert":
                ev["cdi_ontoaligner"] = self.cdi_ontoaligner
            keys = {"bioportal": self.cdi_bioportal_key.strip(), "ontoportal": self.cdi_ontoportal_key.strip()}
            if any(keys.values()):
                ev["cdi_api_keys"] = {k: v for k, v in keys.items() if v}
            if self.hf_token.strip():
                ev["cdi_hf_token"] = self.hf_token.strip()
        if self.task == "interop":       # only the interoperability checks
            ev.update(robot="off", oops="off", ontocheck="off", iri_checks="off", reasoner="off")
        from .quality_checks.oops import OOPS_ENDPOINT

        if self.oops_endpoint.strip() and self.oops_endpoint.strip() != OOPS_ENDPOINT:
            ev["oops_endpoint"] = self.oops_endpoint.strip()
        return ev

    def si_reference_list(self) -> list[str]:
        """SI's own references, one per line; [] = the cross-domain references."""
        return [x.strip() for x in self.si_references.splitlines() if x.strip()]

    def si_domain_map_dict(self) -> dict[str, list[str]]:
        """``ols:emi = 1.5; Biological sciences`` per line -> {"ols:emi": ["1.5", "Biological sciences"]}."""
        out: dict[str, list[str]] = {}
        for line in self.si_domain_map.splitlines():
            oid, sep, doms = line.partition("=")
            if sep and oid.strip():
                out[oid.strip()] = [d.strip() for d in doms.replace(",", ";").split(";") if d.strip()]
        return out

    def cdi_reference_list(self) -> list[str]:
        """References, one per line; local paths made absolute."""
        from .quality_checks.cdi import parse_reference

        out = []
        for line in self.cdi_references.splitlines():
            ref = line.strip()
            if not ref:
                continue
            kind = parse_reference(ref)["kind"]
            out.append(str(Path(ref).expanduser().resolve()) if kind in ("file", "sssom") else ref)
        return out

    def validate(self) -> list[str]:
        problems = []
        s = self.source.strip()
        if not s:
            problems.append("Choose an ontology file or a folder of ontologies.")
        elif not s.startswith(("http://", "https://")) and not Path(s).expanduser().exists():
            problems.append(f"Source not found: {s}")
        if self.task == "diff":
            if self.is_folder:
                problems.append("Compare versions works on one ontology file, not a folder.")
            if not self.previous_version.strip():
                problems.append("Choose the previous version to compare against.")
        for label, val in (("Competency questions", self.competency_questions),
                           ("Previous version", self.previous_version)):
            for v in [x.strip() for x in val.split(",") if x.strip()]:
                if not v.startswith(("http://", "https://")) and not Path(v).expanduser().exists():
                    problems.append(f"{label} file not found: {v}")
        if self.task == "interop" and not (self.cdi or self.si):
            problems.append("Turn on cross-domain or scientific interoperability (or both) to run this check.")
        if self.si and self.task in ("site", "single", "check", "interop"):
            from .quality_checks.cdi.si import resolve_fos

            for label, spec in [("Own scientific domain", self.si_home_domain)] + [
                    (f"Domain of {k}", d) for k, ds in self.si_domain_map_dict().items() for d in ds]:
                if spec.strip():
                    try:
                        resolve_fos(spec)
                    except ValueError as e:
                        problems.append(f"{label}: {e}")
            bad = [ln.strip() for ln in self.si_domain_map.splitlines() if ln.strip() and "=" not in ln]
            if bad:
                problems.append(f"Domain map lines need 'ontology id = field', e.g. 'ols:emi = 1.5': {bad[0]}")
        if (self.cdi or self.si) and self.task in ("site", "single", "check", "interop"):
            from .quality_checks.cdi import parse_reference

            refs = [r for r in self.cdi_references.splitlines() if r.strip()]
            refs += self.si_reference_list() if self.si else []
            if not refs:
                problems.append("Cross-domain and scientific interoperability need at least one reference (e.g. ols).")
            for r in refs:
                ref = parse_reference(r)
                if ref["kind"] in ("file", "sssom") and not Path(ref["path"]).exists():
                    problems.append(f"Reference ontology not found: {r.strip()}")
        return problems

    # -------------------------------------------------------------- CLI / TOML
    def cli(self) -> str:
        """The equivalent ``ontoreview`` command line."""
        q = shlex.quote
        cmd = {"site": ["ontoreview", "build"], "single": ["ontoreview", "build", "--single-file"],
               "markdown": ["ontoreview", "export", "--format", "markdown"],
               "myst": ["ontoreview", "export", "--format", "myst"],
               "check": ["ontoreview", "check", "--format", "json"],
               "interop": ["ontoreview", "check", "--format", "json", "--interop-only"],
               "diff": ["ontoreview", "diff"]}[self.task]
        if self.task == "diff":
            return " ".join(cmd + [q(self.previous_version.strip() or "<previous>"), q(self.source or "<source>"),
                                   "--format", "markdown", "-o", q(str(self.output_path()))])
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
        if self.task == "interop":
            self._cli_interop(args, q)
        if self.task in ("site", "single", "check"):
            if not self.is_folder:
                for c in [x.strip() for x in self.competency_questions.split(",") if x.strip()]:
                    args += ["--cq", q(c)]
            if self.robot != "auto":
                args += ["--robot", self.robot]
            if self.oops != "auto":
                args.append("--oops" if self.oops == "on" else "--no-oops")
            if self.reasoner != "hermit" and self.robot != "off":
                args += ["--reasoner", self.reasoner]
            if not self.ontocheck:
                args.append("--no-ontocheck")
            if not self.iri_checks:
                args.append("--no-iri")
            elif not self.iri_network:
                args.append("--offline")
            self._cli_interop(args, q)
        if self.task == "check" and self.fail_on != "error":
            args += ["--fail-on", self.fail_on]
        return " ".join(args)

    def _cli_interop(self, args: list[str], q) -> None:
        """Cross-domain and scientific interoperability options of the command line."""
        if not self.cdi:
            args.append("--no-cdi")
        if not self.si:
            args.append("--no-si")
        else:
            if self.si_home_domain.strip():
                args += ["--si-home-domain", q(self.si_home_domain.strip())]
            if float(self.si_theta_s or 0.3) != 0.3:
                args += ["--si-theta-s", str(float(self.si_theta_s))]
            for k, ds in self.si_domain_map_dict().items():
                args += ["--si-domain", q(f"{k}={';'.join(ds)}")]
            for r in self.si_reference_list():
                args += ["--si-ref", q(r)]
        if self.cdi or self.si:
            refs = self.cdi_reference_list()
            for r in refs if refs != ["ols"] else []:
                args += ["--cdi", q(r)]
            for d in [x.strip() for x in self.cdi_domains.split(",") if x.strip()]:
                args += ["--cdi-domain", q(d)]
            if self.cdi_ontoaligner != "sbert":
                args += ["--cdi-ontoaligner", self.cdi_ontoaligner]

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
        lines += ["", "[evaluation]", f"robot = {s(self.robot)}", f"oops = {s(self.oops)}", f"reasoner = {s(self.reasoner)}",
                  f"ontocheck = {s('on' if self.ontocheck else 'off')}",
                  f"iri_checks = {s('on' if self.iri_checks else 'off')}",
                  f"iri_network = {'true' if self.iri_network else 'false'}",
                  f"cdi = {s('on' if self.cdi else 'off')}",
                  f"si = {s('on' if self.si else 'off')}"]
        if self.si:
            if self.si_home_domain.strip():
                lines.append(f"si_home_domain = {s(self.si_home_domain.strip())}")
            lines.append(f"si_theta_s = {float(self.si_theta_s or 0.3)}")
            if self.si_reference_list():
                lines.append(f"si_references = [{', '.join(s(x) for x in self.si_reference_list())}]")
            dm = self.si_domain_map_dict()
            if dm:
                lines.append("si_domain_map = { " + ", ".join(f"{s(k)} = [{', '.join(s(d) for d in v)}]"
                                                              for k, v in dm.items()) + " }")
        if self.cdi or self.si:
            lines += [f"cdi_references = [{', '.join(s(x) for x in self.cdi_reference_list())}]",
                      f"cdi_domains = [{', '.join(s(x.strip()) for x in self.cdi_domains.split(',') if x.strip())}]",
                      f"cdi_generality = {'true' if self.cdi_generality else 'false'}",
                      f"cdi_top_n = {int(self.cdi_top_n or 10)}",
                      f"cdi_ontoaligner = {s(self.cdi_ontoaligner)}",
                      "# API keys and tokens are not saved here: set BIOPORTAL_API_KEY / ONTOPORTAL_API_KEY / HF_TOKEN"]
        lines.append("")
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
            robot=ev.get("robot", "auto"), oops=oops, reasoner=ev.get("reasoner", "hermit"),
            ontocheck=ev.get("ontocheck", "on") not in ("off", False),
            ontocheck_network=bool(ev.get("ontocheck_network", True)), ontocheck_search=ev.get("ontocheck_search") or "",
            iri_checks=ev.get("iri_checks", "on") not in ("off", False), iri_network=bool(ev.get("iri_network", True)),
            iri_repositories=bool(ev.get("iri_repositories", True)), iri_resolve=bool(ev.get("iri_resolve", True)),
            cdi=ev.get("cdi", "on") not in ("off", False),
            cdi_references="\n".join(r if r.startswith(("ols", "bioportal", "ontoportal", "http://", "https://"))
                                      else rel(r) for r in ev.get("cdi_references", ["ols"])),
            cdi_domains=", ".join(ev.get("cdi_domains", [])), cdi_generality=bool(ev.get("cdi_generality", True)),
            cdi_top_n=int(ev.get("cdi_top_n", 10)), cdi_ontoaligner=ev.get("cdi_ontoaligner", "sbert"),
            si=ev.get("si", "on") not in ("off", False), si_home_domain=str(ev.get("si_home_domain") or ""),
            si_references="\n".join(r if r.startswith(("ols", "bioportal", "ontoportal", "http://", "https://"))
                                     else rel(r) for r in ev.get("si_references", [])),
            si_theta_s=float(ev.get("si_theta_s", 0.3)),
            si_domain_map="\n".join(f"{k} = {'; '.join(v if isinstance(v, list) else [v])}"
                                     for k, v in (ev.get("si_domain_map") or {}).items()),
        )

    # -------------------------------------------------------------- persistence
    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v for k, v in asdict(self).items() if not k.endswith(("_key", "_token"))}   # secrets: Prefs only
            path.write_text(json.dumps(data, indent=2), "utf-8")
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
    issues: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # what each checker did (not) check, e.g. OOPS! scope
    metrics: list[dict] = field(default_factory=list)  # OntoCheck scorecard rows


@dataclass
class TaskResult:
    task: str
    output: Path
    rows: list[Row] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    index: str | None = None        # landing page for folders
    seconds: float = 0.0
    changes: dict | None = None     # Compare versions: Changelog.to_dict()

    @property
    def ok(self) -> int:
        return sum(1 for r in self.rows if not r.problem)

    @property
    def issues(self) -> list[dict]:
        out = []
        for r in self.rows:
            for i in r.issues:
                out.append({**i, "ontology": r.title or r.name})
        return out

    @property
    def totals(self) -> dict[str, int]:
        return {"terms": sum(r.terms for r in self.rows), "errors": sum(r.errors for r in self.rows),
                "warnings": sum(r.warnings for r in self.rows), "suggestions": sum(r.suggestions for r in self.rows)}


def _metrics(reports) -> list[dict]:
    return [m for x in reports if not isinstance(x, dict) for m in (x.metrics or [])]


def _scope_notes(reports) -> list[str]:
    out = []
    for x in reports:
        tool, scope = (x["tool"], x.get("scope", "")) if isinstance(x, dict) else (x.tool, x.scope)
        if scope:
            out.append(f"{tool}: {scope}")
    return out


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


DOCS_TASKS = ("site", "single", "markdown", "myst")
RUN_FOLDER_TASKS = DOCS_TASKS + ("check", "interop")   # each run in its own folder (Settings.separate_runs)
FILE_SUFFIXES = (".html", ".json", ".md")


def run_folder(out: Path, now: float | None = None) -> Path:
    """A new folder for one docs run, so runs never overwrite each other: ``docs`` becomes
    ``docs-20261121-153012``; a single-file target ``pizza.html`` becomes
    ``pizza-20261121-153012/pizza.html``. A clash within the same second gets ``-2``, ``-3``…"""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
    is_file = out.suffix.lower() in FILE_SUFFIXES
    base = out.parent / f"{out.stem if is_file else out.name}-{stamp}"
    folder, n = base, 1
    while folder.exists():
        n += 1
        folder = base.with_name(f"{base.name}-{n}")
    return folder / out.name if is_file else folder


def interop_only(report) -> None:
    """Keep only the cross-domain and scientific interoperability sections of a quality report."""
    from .report.models import TOOLS

    keep = {TOOLS["cdi"].name, TOOLS["si"].name}
    report.findings, report.rules_run = [], []
    report.external = [x for x in report.external if x.tool in keep]


def run_task(settings: Settings) -> TaskResult:
    """Run the chosen task for a file or a folder. Blocking; call it off the UI thread."""
    from datetime import datetime, timezone

    from .build import build, build_single_file, check, check_records, load, resolve_config
    from .collection import build_collection, export_collection
    from .export import export_markdown
    from .model.extract import extract
    from .report.issues import report_issues

    problems = settings.validate()
    if problems:
        raise ValueError(" ".join(problems))
    t0 = time.perf_counter()
    s = settings
    out = s.output_path()
    separate = s.separate_runs and s.task in RUN_FOLDER_TASKS
    if separate:
        out = run_folder(out if s.task not in ("check", "interop") or out.suffix.lower() == ".json"
                         else out / ("interoperability.json" if s.task == "interop" else "quality.json"))
    src = s.source.strip()
    src = src if src.startswith(("http://", "https://")) else str(Path(src).expanduser().resolve())
    ov = s.overrides()
    res = TaskResult(s.task, out)

    if s.task == "diff":
        from .diff import compare_files

        old = s.previous_version.strip()
        old = old if old.startswith(("http://", "https://")) else str(Path(old).expanduser().resolve())
        log.info("Parsing ontology %s and previous version %s", src, old)
        changelog = compare_files(old, src)
        md = out if out.suffix.lower() == ".md" else out / "changes.md"
        log.info("Rendering changes → %s", md)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(changelog.to_markdown(), "utf-8")
        md.with_suffix(".json").write_text(changelog.to_json(), "utf-8")
        md.with_suffix(".html").write_text(changelog.to_html(
            title=f"Changes in {Path(src).name}", old_label=Path(old).name, new_label=Path(src).name), "utf-8")
        res.output, res.index, res.changes = md, str(md.with_suffix(".html")), changelog.to_dict()
        res.rows = [Row(Path(src).name, Path(src).stem, sum(change_counts(res.changes).values()), output=str(md))]
        res.seconds = time.perf_counter() - t0
        return res
    if s.is_folder and s.task in ("site", "single"):
        coll = build_collection(src, out, single_file=s.task == "single", **ov)
        res.rows = [_row_from_entry(e, out, "index.html") for e in coll.entries]
        res.skipped, res.index = coll.skipped, str(out / "index.html")
    elif s.is_folder and s.task in ("markdown", "myst"):
        coll = export_collection(src, out, myst=s.task == "myst")
        res.rows = [_row_from_entry(e, out, "index.md") for e in coll.entries]
        res.skipped, res.index = coll.skipped, str(out / "index.md")
    elif s.task in ("check", "interop"):
        files = [Path(src)] if not s.is_folder else find_ontologies(src)[0]
        report_json: dict[str, Any] = {}
        if out.suffix.lower() != ".json":
            out = out / ("interoperability.json" if s.task == "interop" else "quality.json")
        # records (cdi.json, si.json, iri-checks.json, provenance.ttl) go with the report: in the run's
        # own folder, or in <report>-records/ next to a report written to a shared folder
        records = out.parent if separate else out.parent / f"{out.stem}-records"
        for f in files:
            name = f.name if not s.is_folder else f.relative_to(Path(src)).as_posix()
            try:
                started = datetime.now(timezone.utc)
                onto, rep = check(f, **{k: v for k, v in ov.items()
                                        if k in ("evaluation", "competency_questions", "load_imports",
                                                 "include_individuals", "reason")})
                if s.task == "interop":
                    interop_only(rep)
                check_records(records / (f.relative_to(Path(src)).with_suffix("").as_posix() if s.is_folder else ""),
                              f, onto, rep, started)
                sm = rep.totals
                res.rows.append(Row(name, onto.metadata.title or f.stem, len(onto.terms), sm["error"],
                                    sm["warning"], sm["info"], _external_text(rep.external),
                                    issues=report_issues(rep), notes=_scope_notes(rep.external),
                                    metrics=_metrics(rep.external)))
                report_json[name] = json.loads(rep.to_json())
            except Exception as e:  # noqa: BLE001
                res.rows.append(Row(name, problem=str(e)))
                report_json[name] = {"error": str(e)}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report_json, indent=2, ensure_ascii=False), "utf-8")
        for r in res.rows:
            r.output = str(out)
        res.output, res.index = (out.parent if separate else out), str(out)
    elif s.task in ("markdown", "myst"):
        log.info("Exporting %s → %s", "MyST" if s.task == "myst" else "Markdown", out)
        cfg = resolve_config(src)
        onto = extract(load(cfg), cfg)
        from .fixes import check_required
        check_required(onto, cfg, src)
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
        sm = b.report.totals if b.report else {"error": 0, "warning": 0, "info": 0}
        res.rows = [Row(Path(src).name, b.ontology.metadata.title or Path(src).stem, len(b.ontology.terms),
                        sm["error"], sm["warning"], sm["info"],
                        _external_text(b.report.external if b.report else []), str(page),
                        issues=report_issues(b.report) if b.report else [],
                        notes=_scope_notes(b.report.external) if b.report else [],
                        metrics=_metrics(b.report.external) if b.report else [])]
        res.index = str(page)
    res.seconds = time.perf_counter() - t0
    return res


def _row_from_entry(e, out: Path, page: str) -> Row:
    q = e.quality or {}
    return Row(e.source, e.title, e.terms, q.get("error", 0), q.get("warning", 0), q.get("info", 0),
               _external_text(e.external), str(out / e.slug / page) if not e.error else "", e.error,
               issues=list(e.issues), notes=_scope_notes(e.external))


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


def reviews_file() -> Path:
    """Reviews waiting on the Quality issues page (kept across restarts)."""
    return SETTINGS_FILE.with_name("reviews.json")


def load_reviews() -> list[dict]:
    try:
        data = json.loads(reviews_file().read_text("utf-8"))
        return [r for r in data if isinstance(r, dict) and r.get("key") and r.get("job")]
    except (OSError, ValueError):
        return []


def save_reviews(rows: list[dict]) -> None:
    f = reviews_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=1, default=str), "utf-8")
        tmp.replace(f)
    except OSError:
        pass
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
    summary: str = ""              # e.g. "+3 added · 1 removed · 2 modified" for comparisons
    deploys: list[dict] = field(default_factory=list)   # GitHub Pages deploys of this run's website
    derived_from: str = ""         # a fixed version (a-v1.ttl): the original it was made from
    fixes_applied: int = 0
    fixes_total: int = 0

    @property
    def fixed_note(self) -> str:
        if not self.derived_from:
            return ""
        return f"Fixed version of {self.derived_from} · {self.fixes_applied} of {self.fixes_total} fixes applied"

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
               path: Path | None = None, limit: int = HISTORY_LIMIT) -> HistoryEntry:
    """Append a run to the history file (newest first, capped)."""
    import uuid

    path = path or HISTORY_FILE
    r = result
    entry = HistoryEntry(
        id=uuid.uuid4().hex[:12], when=time.time(), task=settings.task, source=settings.source,
        output=str(r.output if r else settings.output_path()), index=r.index if r else None,
        ok=r.ok if r else 0, total=len(r.rows) if r else 0,
        errors=sum(x.errors for x in r.rows) if r else 0, warnings=sum(x.warnings for x in r.rows) if r else 0,
        seconds=round(r.seconds, 2) if r else 0.0, settings={k: v for k, v in asdict(settings).items() if not k.endswith(("_key", "_token"))}, failed=error,
        summary="{added} added · {removed} removed · {modified} modified".format(**change_counts(r.changes))
        if r and r.changes else "")
    if settings.source and not settings.source.startswith(("http://", "https://")):
        from .fixes import fixes_record
        rec = fixes_record(settings.source)
        if rec:
            entry.derived_from = rec.get("source", {}).get("name", "")
            entry.fixes_applied = len(rec.get("applied", []))
            entry.fixes_total = entry.fixes_applied + len(rec.get("not_applied", []))
    entries = [entry] + load_history(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([asdict(e) for e in entries[:max(1, limit)]], indent=1), "utf-8")
    except OSError as e:
        log.debug("could not save run history: %s", e)
    return entry


EXPORT_DIR = SETTINGS_FILE.with_name("exports")


def export_output(output: str | Path, dest_dir: Path | None = None) -> Path:
    """A run's output as one file to download: a folder becomes ``<name>.zip`` (its files under
    ``<name>/``), a single file is returned as it is."""
    import zipfile

    src = Path(output).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"{src} no longer exists")
    if src.is_file():
        return src
    dest_dir = dest_dir or EXPORT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{src.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                zf.write(f, Path(src.name) / f.relative_to(src))
    return target


def run_config_rows(settings: dict[str, Any]) -> list[tuple[str, str]]:
    """A recorded run's settings as readable (label, value) rows for the Run history dialog."""
    g = settings.get
    on = lambda v: "on" if v else "off"  # noqa: E731
    rows = [("Task", TASKS.get(g("task", ""), g("task", ""))), ("Ontology", g("source", "")),
            ("Save to", g("output") or "default, next to the ontology")]
    if g("task") in DOCS_TASKS:
        rows += [("Layout", "one page" if g("layout") == "single" else "one page per section"),
                 ("Languages", g("languages", "en")),
                 ("Each run in its own folder", on(g("separate_runs", True)))]
        if g("base_url"):
            rows.append(("Base URL", g("base_url")))
    if g("previous_version"):
        rows.append(("Previous version", g("previous_version")))
    if g("competency_questions"):
        rows.append(("Competency questions", g("competency_questions")))
    if g("task") != "diff":
        rows += [("Load imports", on(g("load_imports", True))), ("Individuals", on(g("include_individuals", True))),
                 ("Reasoning", on(g("reason"))),
                 ("ROBOT", g("robot", "auto")), ("Reasoner", g("reasoner", "hermit")), ("OOPS!", g("oops", "auto")),
                 ("OntoCheck", on(g("ontocheck", True))), ("IRI checks", on(g("iri_checks", True)))]
        cdi = g("cdi", True)
        rows.append(("Cross-domain interoperability",
                     f"on · references: {', '.join(x.strip() for x in str(g('cdi_references', '')).splitlines() if x.strip()) or '–'}"
                     + (f" · domains: {g('cdi_domains')}" if g("cdi_domains") else "")
                     + f" · OntoAligner: {g('cdi_ontoaligner', 'sbert')}" if cdi else "off"))
        rows.append(("Scientific interoperability",
                     ("on · references: " + (", ".join(x.strip() for x in str(g("si_references", "")).splitlines()
                                                         if x.strip()) or "same as cross-domain")
                      + " · own domain: " + (g("si_home_domain") or "classified") + f" · θ_s = {g('si_theta_s', 0.3)}"
                      + (" · domain map: " + "; ".join(x.strip() for x in str(g("si_domain_map", "")).splitlines()
                                                         if x.strip()) if g("si_domain_map") else ""))
                     if g("si", True) else "off"))
        rows.append(("Fail on", g("fail_on", "error")))
    return rows


def add_deploy(output: str, info: dict, path: Path | None = None) -> None:
    """Record a deploy on the newest history entry whose output is ``output``."""
    path = path or HISTORY_FILE
    entries = load_history(path)
    for e in entries:
        if e.output == str(output):
            e.deploys = [info, *e.deploys][:20]
            break
    else:
        return
    try:
        path.write_text(json.dumps([asdict(e) for e in entries], indent=1), "utf-8")
    except OSError as e:
        log.debug("could not save the deploy in the run history: %s", e)


def deploys_for(output: str, path: Path | None = None) -> list[dict]:
    return next((e.deploys for e in load_history(path) if e.output == str(output)), [])


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


# ------------------------------------------------------------------ drag and drop
# Browsers never reveal the local path of a dropped file, so dropped files and folders are
# copied into a workspace and documented from there (folder structure is kept).
UPLOAD_SUFFIXES = RDF_SUFFIXES | UNSUPPORTED | {".json", ".yaml", ".yml", ".csv", ".tsv", ".xlsx",
                                                ".toml", ".md", ".css", ".html"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def uploads_dir() -> Path:
    return SETTINGS_FILE.parent / "uploads"


def safe_relpath(name: str) -> Path | None:
    """A dropped file's relative path, or None if it is unsafe or not a file type we use."""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or p.startswith(".") or "\x00" in p or ":" in p for p in parts):
        return None
    rel = Path(*parts)
    return rel if rel.suffix.lower() in UPLOAD_SUFFIXES else None


def valid_batch(batch: str) -> bool:
    return 8 <= len(batch) <= 64 and all(c in "0123456789abcdef" for c in batch)


def upload_target(batch: str, name: str) -> Path | None:
    """Where a dropped file is stored, or None if the batch id or name is not acceptable."""
    rel = safe_relpath(name)
    if rel is None or not valid_batch(batch):
        return None
    root = (uploads_dir() / batch).resolve()
    target = (root / rel).resolve()
    return target if target.is_relative_to(root) else None


def upload_files(batch: str) -> list[str]:
    """Every ontology or mapping (.tsv) file in a drop, e.g. several reference ontologies."""
    if not valid_batch(batch):
        return []
    root = uploads_dir() / batch
    if not root.is_dir():
        return []
    return sorted(str(p) for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")
                  and (is_ontology_file(p) or p.suffix.lower() == ".tsv"))


def upload_source(batch: str) -> str | None:
    """What to document from a drop: the single ontology file, the single dropped folder, or
    the whole batch when several things were dropped."""
    if not valid_batch(batch):
        return None
    root = uploads_dir() / batch
    if not root.is_dir():
        return None
    top = [p for p in root.iterdir() if not p.name.startswith(".")]
    if len(top) == 1 and top[0].is_dir():
        return str(top[0])
    onto = [p for p in top if p.is_file() and is_ontology_file(p)]
    if len(top) == len(onto) == 1:
        return str(onto[0])
    return str(root)



def change_counts(changes: dict) -> dict[str, int]:
    """Added / removed / modified, where modified includes changes to the ontology's own metadata."""
    return {"added": len(changes["added"]), "removed": len(changes["removed"]),
            "modified": len(changes["modified"]) + len(changes.get("metadata_changes", []))}


def clear_history(path: Path | None = None) -> None:
    path = path or HISTORY_FILE
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ------------------------------------------------------------------ display helpers
def when_text(ts: float, now: float | None = None) -> str:
    """"Today, 23:41" / "Yesterday, 18:02" / "12 Nov, 09:47" / "12 Nov 2025"."""
    import datetime as dt

    t = dt.datetime.fromtimestamp(ts)
    today = dt.datetime.fromtimestamp(now or time.time()).date()
    if t.date() == today:
        return f"Today, {t:%H:%M}"
    if t.date() == today - dt.timedelta(days=1):
        return f"Yesterday, {t:%H:%M}"
    return f"{t.day} {t:%b}, {t:%H:%M}" if t.year == today.year else f"{t.day} {t:%b %Y}"


def run_name(entry: HistoryEntry) -> str:
    p = Path(entry.source)
    if entry.source.startswith(("http://", "https://")):
        return entry.source.rsplit("/", 1)[-1] or entry.source
    if p.is_dir() or (entry.total > 1):
        return f"{p.name}/ ({entry.total} file{'s' if entry.total != 1 else ''})"
    return p.name or entry.source


def issues_text(entry: HistoryEntry) -> str:
    if entry.failed:
        return entry.failed.splitlines()[0][:80]
    if entry.summary:
        return entry.summary
    return f"{entry.errors} error{'s' if entry.errors != 1 else ''} · {entry.warnings} warning{'s' if entry.warnings != 1 else ''}"


def task_kind(task: str) -> str:
    return {"check": "check", "interop": "check", "diff": "diff"}.get(task, "docs")


# ------------------------------------------------------------------ preferences
PREFS_NAME = "prefs.json"


@dataclass
class Prefs:
    """Defaults for new builds (Settings page). A project's ontoreview.toml overrides these."""
    default_output: str = ""
    default_task: Task = "site"
    open_when_done: bool = True
    keep_history: bool = True
    history_limit: int = 50
    robot_enabled: bool = True
    robot_mode: Literal["docker", "local"] = "docker"
    robot_path: str = ""
    robot_image: str = "obolibrary/robot"
    oops: Literal["auto", "on", "off"] = "auto"
    oops_endpoint: str = "https://oops.linkeddata.es/rest"
    oops_timeout: int = 90
    reasoner: Literal["hermit", "elk", "off"] = "hermit"
    ontocheck: bool = True
    ontocheck_network: bool = True
    ontocheck_search: str = ""
    iri_checks: bool = True
    iri_network: bool = True
    iri_repositories: bool = True
    iri_resolve: bool = True
    cdi: bool = True
    cdi_references: str = "ols"
    cdi_domains: str = ""
    cdi_generality: bool = True
    cdi_top_n: int = 10
    cdi_ontoaligner: Literal["off", "fuzzy", "sbert"] = "sbert"
    si: bool = True
    si_home_domain: str = ""
    si_theta_s: float = 0.3
    si_domain_map: str = ""
    si_references: str = ""
    deploy_remote: str = ""         # GitHub repository for "Deploy to GitHub Pages"
    deploy_branch: str = "main"
    deploy_enable_pages: bool = True
    deploy_token: str = field(default="", repr=False)   # optional GitHub token; kept like the API keys
    deploy_create: bool = True      # create the repository when it does not exist (needs the token)
    deploy_private: bool = False
    fix_review: bool = True         # review suggested fixes before docs are generated
    fix_ignored: str = ""           # suggestion ids ignored in future builds (space-separated, stable across builds)
    ai_enabled: bool = True         # AI drafts (definitions, refinements, description); applied only when accepted
    ai_priority: str = "ollama,hf,api"
    ai_hf_model: str = "Qwen/Qwen3.5-4B"
    ai_ollama_model: str = "qwen3.5:4b"
    ai_ollama_url: str = "http://localhost:11434"
    ai_api_provider: str = "openai"
    ai_api_base_url: str = ""
    ai_api_model: str = ""
    ai_api_key: str = field(default="", repr=False)     # kept like the other keys
    cdi_bioportal_key: str = field(default="", repr=False)
    cdi_ontoportal_key: str = field(default="", repr=False)
    hf_token: str = field(default="", repr=False)
    theme: Literal["light", "dark", "system"] = "system"
    compact: bool = False
    # documentation options (Settings > Documentation)
    layout: Literal["single", "multi"] = "single"
    languages: str = "en"
    base_url: str = ""
    load_imports: bool = True
    include_individuals: bool = True
    reason: bool = False
    verbose: bool = False
    competency_questions: str = ""
    previous_version: str = ""
    fail_on: Literal["error", "warning", "info", "never"] = "error"

    @staticmethod
    def path() -> Path:
        return SETTINGS_FILE.with_name(PREFS_NAME)

    def ai_config(self):
        """The AI settings as the fixes package uses them."""
        from .config import AIConfig
        order = [x.strip() for x in self.ai_priority.split(",") if x.strip() in ("hf", "ollama", "api")]
        return AIConfig(enabled=self.ai_enabled, priority=order or ["ollama", "hf", "api"], hf_model=self.ai_hf_model,
                        ollama_model=self.ai_ollama_model, ollama_url=self.ai_ollama_url,
                        api_provider=self.ai_api_provider if self.ai_api_provider in (
                            "openai", "anthropic", "openrouter", "gemini", "mistral", "groq", "custom") else "custom",
                        api_base_url=self.ai_api_base_url, api_model=self.ai_api_model,
                        api_key=self.ai_api_key or None)

    def save(self) -> None:
        try:
            self.path().parent.mkdir(parents=True, exist_ok=True)
            path = self.path()
            path.touch(mode=0o600, exist_ok=True)
            if self.cdi_bioportal_key or self.cdi_ontoportal_key or self.hf_token or self.deploy_token \
                    or self.ai_api_key:
                path.chmod(0o600)                       # optional API keys: readable by this user only
            path.write_text(json.dumps(asdict(self), indent=2), "utf-8")
        except OSError as e:
            log.debug("could not save preferences: %s", e)

    @classmethod
    def load(cls) -> Prefs:
        try:
            data = json.loads(cls.path().read_text("utf-8"))
            known = {f.name for f in fields(cls)}
            prefs = cls(**{k: v for k, v in data.items() if k in known})
            if not (prefs.oops_endpoint or "").strip():   # an emptied field means "the standard service"
                prefs.oops_endpoint = cls.oops_endpoint
            if prefs.ai_priority == "hf,ollama,api":       # the old default: a local Ollama now comes first
                prefs.ai_priority = "ollama,hf,api"
            return prefs
        except (OSError, ValueError, TypeError):
            return cls()

    def apply(self, s: Settings, *, new: bool = False) -> None:
        """Copy the defaults that shape every run onto the form; ``new`` also resets the task."""
        s.default_root = self.default_output
        s.robot = "auto" if self.robot_enabled else "off"
        s.robot_path = self.robot_path if self.robot_mode == "local" else ""
        s.robot_image = self.robot_image or "obolibrary/robot"
        s.oops, s.oops_endpoint, s.oops_timeout = self.oops, self.oops_endpoint, self.oops_timeout
        s.reasoner = self.reasoner
        s.ontocheck, s.ontocheck_network, s.ontocheck_search = self.ontocheck, self.ontocheck_network, self.ontocheck_search
        for k in ("iri_checks", "iri_network", "iri_repositories", "iri_resolve",
                  "cdi", "cdi_references", "cdi_domains", "cdi_generality", "cdi_top_n", "cdi_ontoaligner",
                  "si", "si_home_domain", "si_theta_s", "si_domain_map", "si_references",
                  "cdi_bioportal_key", "cdi_ontoportal_key", "hf_token"):
            setattr(s, k, getattr(self, k))
        for k in ("layout", "languages", "base_url", "load_imports", "include_individuals", "reason", "verbose",
                  "competency_questions", "previous_version", "fail_on"):
            setattr(s, k, getattr(self, k))
        if new:
            s.task = self.default_task


# ------------------------------------------------------------------ environment
_oops_cache: dict[str, tuple[float, bool]] = {}


def robot_status(prefs: Prefs) -> dict[str, str]:
    """{state: ok | warn | off | missing, label, detail} for the sidebar and Settings."""
    import shutil

    from .quality_checks.robot import _docker, _image_present

    if not prefs.robot_enabled:
        return {"state": "off", "label": "ROBOT · off", "detail": "Turned off in Settings"}
    if prefs.robot_mode == "local":
        exe = shutil.which(str(Path(prefs.robot_path or "robot").expanduser()))
        return ({"state": "ok", "label": "ROBOT · local", "detail": exe} if exe else
                {"state": "missing", "label": "ROBOT · not found", "detail": f"`{prefs.robot_path or 'robot'}` is not on PATH"})
    docker = _docker()
    if not docker:
        return {"state": "missing", "label": "ROBOT · Docker not running",
                "detail": "Start Docker, or OOPS! is used instead (if allowed)"}
    image = prefs.robot_image or "obolibrary/robot"
    if _image_present(docker, image):
        return {"state": "ok", "label": "ROBOT · Docker ready", "detail": image}
    return {"state": "warn", "label": "ROBOT · Docker (pulls image)", "detail": f"{image} is downloaded on the first run"}


def oops_status(prefs: Prefs, check: bool = True) -> dict[str, str]:
    """Reachability of the OOPS! service (a HEAD request; the ontology is not sent). Cached 10 min."""
    if prefs.oops == "off":
        return {"state": "off", "label": "OOPS! · off", "detail": "Never uploads"}
    from .quality_checks.oops import OOPS_ENDPOINT

    url = prefs.oops_endpoint or OOPS_ENDPOINT
    hit = _oops_cache.get(url)
    if hit and time.time() - hit[0] < 600:
        ok = hit[1]
    elif not check:
        return {"state": "warn", "label": "OOPS! · not checked", "detail": url}
    else:
        import urllib.request

        try:
            req = urllib.request.Request(url.rsplit("/rest", 1)[0] or url, method="HEAD",
                                         headers={"User-Agent": "ontoreview"})
            with urllib.request.urlopen(req, timeout=5) as r:  # noqa: S310 - fixed https endpoint
                ok = r.status < 500
        except Exception:  # noqa: BLE001
            ok = False
        _oops_cache[url] = (time.time(), ok)
    mode = "fallback" if prefs.oops == "auto" else "always"
    return ({"state": "ok", "label": "OOPS! · reachable", "detail": f"{url} ({mode})"} if ok else
            {"state": "missing", "label": "OOPS! · unreachable", "detail": url})


def system_info() -> dict[str, str]:
    import platform

    from . import __version__

    try:
        import nicegui
        ng = nicegui.__version__
    except ImportError:
        ng = "not installed"
    from .quality_checks.robot import _docker

    docker = _docker()
    if docker:
        import subprocess
        try:
            dv = subprocess.run([docker, "version", "--format", "{{.Server.Version}}"], capture_output=True,
                                text=True, timeout=10).stdout.strip()
        except Exception:  # noqa: BLE001
            dv = "?"
        dock = f"Docker {dv} · {robot_status(Prefs.load())['detail']}"
    else:
        dock = "Docker not running"
    return {"OntoReview": __version__, "Python": platform.python_version(), "NiceGUI": ng,
            "Platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "Docker / ROBOT": dock, "Config file": str(SETTINGS_FILE.parent)}
