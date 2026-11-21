"""The quality report's plain-language summary and merged "Issues at a glance" table."""

from __future__ import annotations

import re

from ontoreview.fixes.orcid import parse, query_for
from ontoreview.report.models import ExternalItem, ExternalReport, Finding, Report

A, B, C = "https://ex.org/A", "https://ex.org/B", "https://ex.org/hasX"


def report() -> Report:
    return Report(
        findings=[Finding("OB011", "Term without a definition", "warning", "…", A),
                  Finding("OB012", "Property without domain", "info", "…", C),
                  Finding("OB016", "Duplicate labels", "warning", "…", A)],
        external=[
            ExternalReport("ROBOT", "", items=[
                ExternalItem("missing_definition", "Missing definition", "warning", affected=[A, B]),
                ExternalItem("duplicate_label", "Duplicate label", "error", affected=[A, B])]),
            ExternalReport("OntoCheck", "", items=[
                ExternalItem("missingDomainRange", "Properties without domain or range", "info", affected=[C]),
                ExternalItem("definitionCheck", "Classes without skos:definition", "info", affected=[A])]),
            ExternalReport("Cross-domain interoperability", "", items=[
                ExternalItem("CDI-A", "No correspondence", "info", affected=[A])]),
            ExternalReport("OOPS!", "", error="unreachable"),
        ])


def test_overlapping_checks_merge_into_one_issue():
    issues = {i["key"]: i for i in report().merged_issues()}
    d = issues["OB011"]
    assert d["found_by"] == ["OntoReview", "ROBOT", "OntoCheck"] and d["elements"] == [A, B]
    assert issues["OB016"]["severity"] == "error"            # worst severity wins
    # "domain or range" goes to the issue the element already has, not to both
    assert C in issues["OB012"]["elements"] and "OB013" not in issues
    # interoperability is a score, not a defect
    assert not any(k.startswith("Cross-domain") for k in issues)


def test_plain_summary_counts_distinct_issues():
    ps = report().plain_summary()
    assert ps["issues"] == 3 and ps["raw"] > ps["issues"] and ps["overlap"] == 3
    assert ps["failed"] == ["OOPS!"]


def test_quality_section_has_summary_merged_table_and_no_bars(tmp_path):
    import ontoreview
    res = ontoreview.build("tests/fixtures/pizza.ttl", out=tmp_path / "s")
    html = (tmp_path / "s" / "index.html").read_text()
    assert 'class="qsum' in html and "checks ran on this version" in html
    assert "check-bar" not in html
    if res.report.external:
        assert "Issues at a glance" in html and "Found by" in html


def test_orcid_query_and_parse():
    assert 'given-names:"Ada" AND family-name:"Lovelace"' in query_for("Ada Lovelace")
    assert query_for("  ") == ""
    hits = parse({"expanded-result": [
        {"orcid-id": "0000-0002-1825-0097", "given-names": "Josiah", "family-names": "Carberry",
         "institution-name": ["Brown University", "Brown University"]},
        {"given-names": "no id"}]})
    assert hits == [{"orcid": "0000-0002-1825-0097", "name": "Josiah Carberry", "institutions": ["Brown University"],
                     "url": "https://orcid.org/0000-0002-1825-0097"}]
    assert re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", hits[0]["orcid"])
