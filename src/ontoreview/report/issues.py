"""A quality report as table rows, for the app's Issues table and collection summaries."""

from __future__ import annotations

from .models import SEVERITY_ORDER


def report_issues(report, limit: int = 500) -> list[dict]:
    """A quality report as table rows: built-in checks grouped by rule, plus ROBOT / OOPS! items.

    Each row: severity (error | warning | info), check, rule, affected (a term or "N elements").
    """
    rows: list[dict] = []
    by_rule: dict[str, list] = {}
    for f in report.findings:
        by_rule.setdefault(f.rule, []).append(f)
    for rid, items in by_rule.items():
        first = items[0]
        subjects = sorted({i.subject_label or i.subject for i in items if i.subject_label or i.subject})
        affected = subjects[0] if len(subjects) == 1 else (f"{len(subjects)} elements" if subjects else "ontology")
        rows.append({"severity": first.severity, "check": "OntoReview", "rule": f"{rid} · {first.title}",
                     "affected": affected, "count": len(items)})
    for ext in report.external:
        if ext.error:
            rows.append({"severity": "warning", "check": ext.tool, "rule": "Could not run",
                         "affected": ext.error, "count": 1})
            continue
        for it in ext.items:
            name = it.name if it.name and it.name != it.code else ""
            rule = f"{it.code} · {name}" if name and it.code[:1].upper() == "P" and it.code[1:].isdigit() else (it.code or name)
            n = len(it.affected)
            affected = it.affected[0] if n == 1 else (f"{n} elements" if n else (it.note[:80] or "ontology"))
            rows.append({"severity": it.severity, "check": ext.tool, "rule": rule, "affected": affected,
                         "count": max(n, 1)})
    rows.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 3), r["check"], r["rule"]))
    return rows[:limit]
