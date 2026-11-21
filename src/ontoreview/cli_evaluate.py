"""``ontoreview evaluate``: every evaluation and every evaluation setting on the command line, with a
stable JSON result for other tools and sites to consume.

    ontoreview evaluate onto.ttl --format json                       # all evaluations, JSON to stdout
    ontoreview evaluate onto.ttl --only rules,iri,ontocheck -f json  # just these
    ontoreview evaluate onto.ttl --cdi-tau 0.6 --iri-timeout 10      # any [evaluation] setting
    ontoreview evaluate --list-options --format json                 # the options, as JSON (build forms from it)

The options are generated from :class:`ontoreview.config.EvaluationConfig`, so a new setting there is a
new CLI option without further code. Options left out keep the value from ontoreview.toml (or the
default).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import typing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import enum

import typer

from .config import ChecksConfig, EvaluationConfig

SCHEMA = "ontoreview.evaluation/1"
FORMAT = enum.Enum("EvalFormat", {"console": "console", "json": "json", "html": "html"}, type=str)
FAIL_ON = enum.Enum("EvalFailOn", {k: k for k in ("error", "warning", "info", "never")}, type=str)

# --only names → the [evaluation] switch that turns each one on or off ("rules" = built-in rules)
CHECKS: dict[str, str | None] = {"rules": None, "robot": "robot", "reasoner": "reasoner", "iri": "iri_checks",
                                 "ontocheck": "ontocheck", "oops": "oops", "cdi": "cdi", "si": "si"}
ON = {"robot": "auto", "oops": "auto", "reasoner": "hermit", "iri_checks": "on", "ontocheck": "on", "cdi": "on",
      "si": "on"}
CHECK_TITLES = {"rules": "Built-in rules", "robot": "ROBOT report", "reasoner": "Logical consistency",
                "iri": "IRI checks", "ontocheck": "OntoCheck", "oops": "OOPS!",
                "cdi": "Cross-domain interoperability", "si": "Scientific interoperability"}
TOOL_OF = {"robot": "ROBOT", "reasoner": "Logical consistency", "iri": "IRI checks", "ontocheck": "OntoCheck",
           "oops": "OOPS!", "cdi": "Cross-domain interoperability", "si": "Scientific interoperability"}
PANELS = (("robot", "ROBOT"), ("reasoner", "Logical consistency (reasoner)"), ("iri_", "IRI checks"),
          ("ontocheck", "OntoCheck"), ("oops", "OOPS!"), ("cdi", "Cross-domain interoperability"),
          ("si", "Scientific interoperability"))
SECRETS = {"cdi_hf_token", "cdi_api_keys"}          # never echoed in results
ENV_HINT = {"cdi_hf_token": "HF_TOKEN", "cdi_api_keys": "BIOPORTAL_API_KEY / ONTOPORTAL_API_KEY"}


# ------------------------------------------------------------------ options from the settings model
def _panel(name: str) -> str:
    return next((title for prefix, title in PANELS if name == prefix.rstrip("_") or name.startswith(prefix)),
                "Other evaluation settings")


def _kind(annotation) -> tuple[str, tuple]:
    """(kind, choices) of a settings field: bool, int, float, str, choice, list, dict, dict_list."""
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    origin = typing.get_origin(annotation)
    if origin is typing.Union or (origin is not None and str(origin) == "<class 'types.UnionType'>"):
        if len(args) == 1:
            return _kind(args[0])
        lits = [a for a in args if typing.get_origin(a) is Literal]
        if bool in args and lits:                     # e.g. bool | Literal["auto"]
            return "choice", ("true", "false", *typing.get_args(lits[0]))
        return "str", ()
    if origin is Literal:
        return "choice", tuple(str(x) for x in typing.get_args(annotation))
    if origin is list:
        return "list", ()
    if origin is dict:
        val = typing.get_args(annotation)[1] if typing.get_args(annotation) else str
        return ("dict_list" if typing.get_origin(val) is list else "dict"), ()
    if annotation is bool:
        return "bool", ()
    if annotation is int:
        return "int", ()
    if annotation is float:
        return "float", ()
    return "str", ()


def option_specs() -> list[dict]:
    """One entry per [evaluation] setting: name, CLI flag, kind, choices, default, help, group."""
    out = []
    for name, f in EvaluationConfig.model_fields.items():
        kind, choices = _kind(f.annotation)
        default = f.get_default(call_default_factory=True)
        desc = (f.description or "").strip()
        if name in ENV_HINT:
            desc = desc.rstrip(". ") + f". Prefer the {ENV_HINT[name]} environment variable (keeps it out of shell history)."
        out.append({"name": name, "flag": "--" + name.replace("_", "-"), "kind": kind, "choices": list(choices),
                    "default": None if name in SECRETS else default, "help": desc, "group": _panel(name),
                    "secret": name in SECRETS})
    return out


def _typer_param(spec: dict) -> inspect.Parameter:
    kind, flag, help_ = spec["kind"], spec["flag"], spec["help"] or spec["name"]
    if spec["default"] not in (None, [], {}) and not spec["secret"]:
        help_ += f" [default: {spec['default']}]"
    panel = spec["group"]
    if kind == "bool":
        ann, opt = Optional[bool], typer.Option(None, f"{flag}/--no-{flag[2:]}", help=help_, rich_help_panel=panel,
                                                show_default=False)
    elif kind in ("int", "float"):
        ann = Optional[int] if kind == "int" else Optional[float]
        opt = typer.Option(None, flag, help=help_, rich_help_panel=panel, show_default=False)
    elif kind == "choice":
        ann, opt = Optional[_choices(spec["name"], spec["choices"])], \
            typer.Option(None, flag, help=help_, rich_help_panel=panel, show_default=False)
    elif kind == "list":
        ann, opt = Optional[list[str]], typer.Option(None, flag, help=help_ + " Repeatable.", rich_help_panel=panel,
                                                     show_default=False)
    elif kind in ("dict", "dict_list"):
        form = "KEY=V1;V2" if kind == "dict_list" else "KEY=VALUE"
        ann, opt = Optional[list[str]], typer.Option(None, flag, help=f"{help_} As {form}; repeatable.",
                                                     rich_help_panel=panel, show_default=False, metavar=form)
    else:
        ann, opt = Optional[str], typer.Option(None, flag, help=help_, rich_help_panel=panel, show_default=False)
    return inspect.Parameter(spec["name"], inspect.Parameter.KEYWORD_ONLY, default=opt, annotation=ann)


def _choices(name: str, values) -> type[enum.Enum]:
    """An Enum for a fixed set of values (how Typer shows and validates choices)."""
    return enum.Enum("".join(w.title() for w in name.split("_")), {str(v): str(v) for v in values}, type=str)


def _coerce(spec: dict, value):
    """A CLI value → the settings value (dict options parsed from KEY=VALUE items)."""
    if isinstance(value, enum.Enum):
        value = value.value
    if spec["kind"] == "dict":
        out = {}
        for item in value:
            k, sep, v = item.partition("=")
            if not sep:
                raise typer.BadParameter(f"use KEY=VALUE, got {item!r}", param_hint=spec["flag"])
            out[k.strip()] = v.strip()
        return out
    if spec["kind"] == "dict_list":
        out = {}
        for item in value:
            k, sep, v = item.partition("=")
            if not sep:
                raise typer.BadParameter(f"use KEY=V1;V2, got {item!r}", param_hint=spec["flag"])
            out[k.strip()] = [x.strip() for x in v.split(";") if x.strip()]
        return out
    if spec["kind"] == "choice" and set(spec["choices"]) >= {"true", "false"}:
        return {"true": True, "false": False}.get(value, value)
    return value


def evaluation_overrides(values: dict) -> dict:
    """[evaluation] overrides from the generated options that were given (None = not given)."""
    specs = {s["name"]: s for s in option_specs()}
    ev = {k: _coerce(specs[k], v) for k, v in values.items() if k in specs and v is not None}
    if ev:
        try:
            EvaluationConfig(**ev)                   # same validation as ontoreview.toml
        except Exception as e:  # noqa: BLE001 - pydantic ValidationError
            raise typer.BadParameter(str(e)) from e
    return ev


def parse_set(items: list[str] | None) -> dict:
    """``--set KEY=VALUE`` items (any [evaluation] setting, e.g. cdi_tau=0.6, iri_network=false,
    cdi_references=ols,file.ttl, si_domain_map=ols:emi=1.5;1.6) → validated overrides."""
    if not items:
        return {}
    specs = {s["name"]: s for s in option_specs()}
    raw: dict = {}
    for item in items:
        key, sep, val = item.partition("=")
        key = key.strip().removeprefix("evaluation.").replace("-", "_")
        if not sep or key not in specs:
            raise typer.BadParameter(f"unknown setting {key!r} (see `ontoreview evaluate --list-options`)",
                                     param_hint="--set")
        kind = specs[key]["kind"]
        val = val.strip()
        if kind == "bool":
            if val.lower() not in ("true", "false", "on", "off", "1", "0", "yes", "no"):
                raise typer.BadParameter(f"{key} takes true or false", param_hint="--set")
            raw[key] = val.lower() in ("true", "on", "1", "yes")
        elif kind == "int":
            raw[key] = int(val)
        elif kind == "float":
            raw[key] = float(val)
        elif kind == "list":
            raw.setdefault(key, []).extend(x.strip() for x in val.split(",") if x.strip())
        elif kind in ("dict", "dict_list"):
            raw.setdefault(key, []).append(val)
        else:
            raw[key] = val
    return evaluation_overrides(raw)


def parse_only(only: list[str] | None) -> set[str] | None:
    if not only:
        return None
    names = {x.strip().lower() for item in only for x in item.split(",") if x.strip()}
    unknown = names - set(CHECKS)
    if unknown:
        raise typer.BadParameter(f"unknown {', '.join(sorted(unknown))}; use {', '.join(CHECKS)}",
                                 param_hint="--only")
    return names


def only_overrides(selected: set[str] | None) -> dict:
    """Turn off every evaluation not in ``selected`` (all run when nothing is selected)."""
    if not selected:
        return {}
    return {switch: "off" for name, switch in CHECKS.items() if switch and name not in selected}


# ------------------------------------------------------------------ result
def _sha256(source: str) -> str | None:
    p = Path(source)
    if p.is_file():
        return hashlib.sha256(p.read_bytes()).hexdigest()
    return None


def _status(name: str, selected: set[str] | None, cfg, report) -> dict:
    if name == "rules":
        if selected is not None and "rules" not in selected:
            return {"status": "off"}
        return {"status": "ran", "rules": len(report.rules_run), "findings": len(report.findings)}
    switch = CHECKS[name]
    if getattr(cfg.evaluation, switch) == "off":
        return {"status": "off"}
    ext = next((x for x in report.external if x.tool == TOOL_OF[name]), None)
    if ext is None:
        return {"status": "skipped", "reason": "not available (e.g. Docker or the optional extra not installed)"}
    if ext.error:
        return {"status": "error", "error": ext.error}
    return {"status": "ran", "findings": sum(ext.summary.values())}


def result_dict(source: str, onto, report, cfg, selected: set[str] | None, started: datetime,
                finished: datetime) -> dict:
    """The JSON result: what was evaluated, with which settings, and what was found."""
    from . import __version__
    settings = cfg.evaluation.model_dump()
    for k in SECRETS:
        if settings.get(k):
            settings[k] = "***"
    ps = report.plain_summary()
    md = onto.metadata
    return {
        "schema": SCHEMA,
        "tool": {"name": "OntoReview", "version": __version__},
        "source": {"location": str(source), "name": Path(str(source)).name, "sha256": _sha256(str(source))},
        "started_at": started.isoformat(timespec="seconds"), "finished_at": finished.isoformat(timespec="seconds"),
        "seconds": round((finished - started).total_seconds(), 2),
        "ontology": {"iri": md.iri, "title": md.title, "version": md.version_info, "version_iri": md.version_iri,
                     "license": md.license, "terms": len(onto.terms)},
        "evaluations": {n: {"title": CHECK_TITLES[n], **_status(n, selected, cfg, report)} for n in CHECKS},
        "summary": {"distinct_issues": ps["issues"], "raw_findings": ps["raw"], "by_severity": ps["by"],
                    "reported_by_several_checks": ps["overlap"], "consistent": ps["consistent"],
                    "scores": ps["scores"], "failed": ps["failed"]},
        "issues": report.merged_issues(),
        "settings": {"evaluation": settings, "checks": cfg.checks.model_dump()},
        "report": report.to_dict(),
    }


# ------------------------------------------------------------------ the command
def _list_options(fmt: str) -> None:
    specs = option_specs()
    extra = [{"name": "only", "flag": "--only", "kind": "list", "choices": list(CHECKS), "default": None,
              "help": "Run only these evaluations (comma-separated or repeated).", "group": "Selection",
              "secret": False},
             {"name": "disable_rule", "flag": "--disable-rule", "kind": "list", "choices": [], "default": [],
              "help": "Built-in rule id to skip, e.g. OB019. Repeatable.", "group": "Built-in rules",
              "secret": False},
             {"name": "severity", "flag": "--severity", "kind": "dict", "choices": ["error", "warning", "info"],
              "default": {}, "help": "Change a built-in rule's severity, as RULE=LEVEL. Repeatable.",
              "group": "Built-in rules", "secret": False}]
    if fmt == "json":
        sys.stdout.write(json.dumps({"schema": "ontoreview.evaluation-options/1", "checks": CHECK_TITLES,
                                     "options": extra + specs}, indent=2, default=str) + "\n")
        return
    from rich.console import Console
    from rich.table import Table
    t = Table("Option", "Type", "Default", "Description", title="ontoreview evaluate: options", show_lines=False)
    for s in extra + specs:
        kind = "|".join(s["choices"]) if s["kind"] == "choice" else s["kind"]
        t.add_row(s["flag"], kind, "" if s["default"] in (None, [], {}) else str(s["default"]), s["help"][:110])
    Console().print(t)


def evaluate(source: Optional[str], config: Optional[Path], only: Optional[list[str]],
             disable_rule: Optional[list[str]], severity: Optional[list[str]], fmt: str, output: Optional[Path],
             records: Optional[Path], fail_on: str, cq: Optional[list[str]], list_options: bool, verbose: bool,
             **settings) -> None:
    from rich.console import Console
    from rich.markup import escape

    from .build import check as do_check
    from .build import resolve_config

    fmt = getattr(fmt, "value", fmt)
    fail_on = getattr(fail_on, "value", fail_on)
    if list_options:
        _list_options(fmt)
        return
    if not source and not config:
        raise typer.BadParameter("give an ontology file or URL (or --config)", param_hint="SOURCE")
    if verbose:
        import logging
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    selected = parse_only(only)
    ev = evaluation_overrides(settings)
    if selected:
        ev |= only_overrides(selected)
        for name in selected:                        # selected ones run even if ontoreview.toml turns them off,
            sw = CHECKS[name]                        # unless the switch itself is given as an option
            if sw and settings.get(sw) is None:
                ev[sw] = ON[sw]
    checks: dict = {}
    if disable_rule:
        checks["disable"] = [r.strip() for x in disable_rule for r in x.split(",") if r.strip()]
    if severity:
        sev = {}
        for item in severity:
            k, sep, v = item.partition("=")
            if not sep or v.strip() not in ("error", "warning", "info"):
                raise typer.BadParameter("use RULE=error|warning|info", param_hint="--severity")
            sev[k.strip()] = v.strip()
        checks["severity"] = sev
    if checks:
        ChecksConfig(**checks)
    extra: dict = {"evaluation": ev} if ev else {}
    if checks:
        extra["checks"] = checks
    if cq:
        extra["competency_questions"] = [str(Path(c).resolve()) for c in cq]
    err = Console(stderr=True)
    started = datetime.now(timezone.utc)
    try:
        cfg = resolve_config(source, config, **extra)
        onto, report = do_check(source, config=config, **extra)
    except (ValueError, FileNotFoundError) as e:
        err.print(f"[bold red]Error:[/] {escape(str(e))}")
        raise typer.Exit(2) from e
    if selected is not None and "rules" not in selected:
        report.findings, report.rules_run = [], []
    finished = datetime.now(timezone.utc)
    if records:
        from .build import check_records
        check_records(records, source or Path(config or ".").name, onto, report, started)
    if fmt == "json":
        text = json.dumps(result_dict(source or str(config), onto, report, cfg, selected, started, finished),
                          indent=2, ensure_ascii=False, default=str)
        if output:
            output.write_text(text + "\n", "utf-8")
        else:
            sys.stdout.write(text + "\n")
    elif fmt == "html":
        from .report.html import quality_html
        target = output or Path("quality.html")
        target.write_text(quality_html(onto, report), "utf-8")
        err.print(f"Report written to {target}")
    else:
        from .report.console import print_report
        print_report(Console(), onto, report)
    if fail_on != "never" and report.failed(fail_on):
        raise typer.Exit(1)


def register(app: typer.Typer, panel: str | None = None) -> None:
    """Add ``evaluate`` to the CLI, with one option per [evaluation] setting."""
    from .cli import ConfigOpt, SourceArg

    fixed = [
        inspect.Parameter("source", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=SourceArg, annotation=Optional[str]),
        inspect.Parameter("config", inspect.Parameter.KEYWORD_ONLY, default=ConfigOpt, annotation=Optional[Path]),
        inspect.Parameter("only", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[list[str]], default=typer.Option(
            None, "--only", help=f"Run only these evaluations: {', '.join(CHECKS)} (comma-separated or repeated). "
                                 "Default: all.", rich_help_panel="Selection and output")),
        inspect.Parameter("disable_rule", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[list[str]],
                          default=typer.Option(None, "--disable-rule", help="Built-in rule to skip, e.g. OB019. "
                                               "Repeatable.", rich_help_panel="Built-in rules")),
        inspect.Parameter("severity", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[list[str]],
                          default=typer.Option(None, "--severity", metavar="RULE=LEVEL", help="Change a built-in "
                                               "rule's severity (error, warning, info). Repeatable.",
                                               rich_help_panel="Built-in rules")),
        inspect.Parameter("fmt", inspect.Parameter.KEYWORD_ONLY, annotation=FORMAT, default=typer.Option(
            "console", "--format", "-f",
            help="json: one result object (schema ontoreview.evaluation/1) for other tools.",
            rich_help_panel="Selection and output")),
        inspect.Parameter("output", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[Path], default=typer.Option(
            None, "--output", "-o", help="Write the result to this file (default: stdout).",
            rich_help_panel="Selection and output")),
        inspect.Parameter("records", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[Path], default=typer.Option(
            None, "--records", help="Also write the run records (cdi.json, si.json, iri-checks.json, provenance.ttl) "
                                    "to this folder.", rich_help_panel="Selection and output")),
        inspect.Parameter("fail_on", inspect.Parameter.KEYWORD_ONLY, annotation=FAIL_ON, default=typer.Option(
            "error", "--fail-on",
            help="Exit 1 if findings reach this severity.", rich_help_panel="Selection and output")),
        inspect.Parameter("cq", inspect.Parameter.KEYWORD_ONLY, annotation=Optional[list[str]], default=typer.Option(
            None, "--cq", help="Competency questions file; repeatable.", rich_help_panel="Selection and output")),
        inspect.Parameter("list_options", inspect.Parameter.KEYWORD_ONLY, annotation=bool, default=typer.Option(
            False, "--list-options", help="List every option (with --format json: machine-readable) and exit.",
            rich_help_panel="Selection and output")),
        inspect.Parameter("verbose", inspect.Parameter.KEYWORD_ONLY, annotation=bool,
                          default=typer.Option(False, "--verbose", "-v")),
    ]
    generated = [_typer_param(s) for s in option_specs()]

    def command(**kw):
        evaluate(**kw)

    params = fixed + generated
    command.__signature__ = inspect.Signature(params)
    command.__annotations__ = {p.name: p.annotation for p in params}
    command.__doc__ = ("Run the evaluations (built-in rules, ROBOT, reasoner, IRI checks, OntoCheck, OOPS!, "
                       "cross-domain and scientific interoperability) with every setting as an option. "
                       "--format json gives one result object for other tools and sites.")
    app.command("evaluate", rich_help_panel=panel)(command)


__all__ = ["CHECKS", "SCHEMA", "evaluation_overrides", "option_specs", "parse_only", "parse_set", "register", "result_dict"]
