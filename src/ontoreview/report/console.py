"""A quality report printed to the terminal (``ontoreview check``)."""

from __future__ import annotations

import re

from rich.console import Console

SEV_STYLE = {"error": "bold red", "warning": "yellow", "info": "cyan"}


def _esc(s: str) -> str:
    return s.replace("[", "\\[")


def print_findings(console: Console, report) -> None:
    """Built-in rule findings, grouped by rule (worst first)."""
    if not report.findings:
        console.print("[green]✓ No issues found.[/]")
    for rule, findings in report.by_rule():
        sev = findings[0].severity
        console.print(f"\n[{SEV_STYLE[sev]}]{sev.upper():8}[/] [bold]{rule.id}[/] {rule.title} "
                      f"[dim]({len(findings)})[/]")
        for f in findings[:50]:
            msg = re.sub(r"`([^`]+)`", r"[bold]\1[/]", _esc(f.message))
            console.print(f"   • {msg}")
        if len(findings) > 50:
            console.print(f"   [dim]… and {len(findings) - 50} more[/]")


def print_external(console: Console, report) -> None:
    """One section per external checker (ROBOT, logical consistency, OntoCheck, OOPS!)."""
    for ext in report.external:
        console.print(f"\n[bold]{ext.tool}[/] [dim]{ext.url}[/]")
        if ext.scope:
            console.print(f"   [dim]{_esc(ext.scope)}[/]")
        if ext.error:
            console.print(f"   [red]{_esc(ext.error)}[/]")
            continue
        print_metrics(console, ext.metrics)
        if not ext.items and not ext.metrics:
            console.print(f"   [green]{_esc(ext.note or 'No issues reported.')}[/]")
        for it in ext.items:
            console.print(f"   [{SEV_STYLE[it.severity]}]{it.severity.upper():8}[/] {it.code} {_esc(it.name)} "
                          + (f"[dim]({len(it.affected)})[/]" if it.affected else ""))
            if it.note and not it.affected:
                console.print(f"            [dim]{_esc(it.note[:300])}[/]")


METRIC_STYLE = {"ok": "green", "warn": "yellow", "error": "bold red", "info": "", "skipped": "dim"}


def print_metrics(console: Console, metrics: list[dict]) -> None:
    """A scorecard (OntoCheck): one line per metric, grouped by category."""
    group = None
    for m in metrics:
        if m["group"] != group:
            group = m["group"]
            console.print(f"   [bold]{_esc(group)}[/]")
        style = METRIC_STYLE.get(m["status"], "")
        value = f"[{style}]{_esc(m['value'])}[/]" if style else _esc(m["value"])
        console.print(f"     {_esc(m['title']):<26} {value}")


def print_report(console: Console, onto, report) -> None:
    print_findings(console, report)
    print_external(console, report)
    s = report.totals
    console.print(f"\n[bold]{s['error']}[/] errors, [bold]{s['warning']}[/] warnings, "
                  f"[bold]{s['info']}[/] suggestions in {len(onto.terms)} terms (all checks).")
