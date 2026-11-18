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
    """One section per external checker (ROBOT, logical consistency, OOPS!)."""
    for ext in report.external:
        console.print(f"\n[bold]{ext.tool}[/] [dim]{ext.url}[/]")
        if ext.error:
            console.print(f"   [red]{_esc(ext.error)}[/]")
            continue
        if not ext.items:
            console.print(f"   [green]{_esc(ext.note or 'No issues reported.')}[/]")
        for it in ext.items:
            console.print(f"   [{SEV_STYLE[it.severity]}]{it.severity.upper():8}[/] {it.code} {_esc(it.name)} "
                          + (f"[dim]({len(it.affected)})[/]" if it.affected else ""))


def print_report(console: Console, onto, report) -> None:
    print_findings(console, report)
    print_external(console, report)
    s = report.summary
    console.print(f"\n[bold]{s['error']}[/] errors, [bold]{s['warning']}[/] warnings, "
                  f"[bold]{s['info']}[/] suggestions in {len(onto.terms)} terms.")
