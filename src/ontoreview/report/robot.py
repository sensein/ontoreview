"""ROBOT report output (TSV) → findings."""

from __future__ import annotations

import csv
import re

from .models import ExternalItem, ExternalReport, new_report, sort_items

ROBOT_LEVELS = {"error": "error", "warn": "warning", "info": "info"}
_NOISE = ("use the -vvv option", "use the --help option", "unfortunately, robot is not able", "tip:")
_LOG_PREFIX = re.compile(r"^\S+ \S+ (ERROR|WARN|INFO) \S+ - \s*")


def robot_message(output: str) -> str:
    """The most useful line of ROBOT's console output: its first real message, without log
    prefixes or the generic "Use the --help option" hints that ROBOT prints last."""
    for line in output.splitlines():
        line = _LOG_PREFIX.sub("", line.strip())
        if line and not line.lower().startswith(_NOISE) and not line.startswith("at "):
            return line
    return ""


def parse_robot_tsv(text: str) -> list[ExternalItem]:
    """Findings from a ``robot report`` TSV, one item per (level, rule) with the subjects listed."""
    grouped: dict[tuple[str, str], ExternalItem] = {}
    for row in csv.DictReader(text.splitlines(), delimiter="\t"):
        level = ROBOT_LEVELS.get((row.get("Level") or "").strip().lower(), "info")
        rule = (row.get("Rule Name") or "").strip()
        item = grouped.setdefault((level, rule), ExternalItem(
            code=rule, name=rule.replace("_", " ").capitalize(), severity=level))
        subject = (row.get("Subject") or "").strip()
        if subject:
            item.affected.append(subject)
    return sort_items(list(grouped.values()))


def robot_report(tsv: str | None, failure: str | None = None) -> ExternalReport:
    """Report from ``robot report`` output: its TSV, or the reason it produced none."""
    if tsv is None:
        return new_report("robot", error=failure or "ROBOT report failed")
    return new_report("robot", parse_robot_tsv(tsv))
