"""OntoCheck metrics: runner (quality_checks/ontocheck.py) and report (report/ontocheck.py)."""

import pytest
from rdflib import Graph

from ontoreview.config import Config
from ontoreview.quality_checks.ontocheck import run_ontocheck
from ontoreview.report.ontocheck import GROUPS, METRICS, ontocheck_report

pytestmark = pytest.mark.real_ontocheck

ALL = ["checkLabel", "altLabelCheck", "definitionCheck", "isolatedElements", "classConnections",
       "missingDomainRange", "leafNodeCheck", "semanticConnection", "sparqlEndpoint", "rdfDump", "humanLicense",
       "externalLinks", "classCapitalCheck", "classSpaceCheck", "spellCheck", "duplicateLabels", "searchClass"]

def test_every_requested_metric_is_reported(fixtures, pizza):
    loaded, _ = pizza
    rep = run_ontocheck(loaded.graph, fixtures / "pizza.ttl", network=False, search="Pizza")
    assert rep.tool == "OntoCheck" and rep.error is None
    assert [m["metric"] for m in rep.metrics] == ALL == list(METRICS)
    assert {m["group"] for m in rep.metrics} == set(GROUPS)
    by = {m["metric"]: m for m in rep.metrics}
    assert by["checkLabel"]["value"] == "7 of 8 classes (88%)" and by["checkLabel"]["status"] == "warn"
    assert by["sparqlEndpoint"]["status"] == "skipped" and "network" in by["sparqlEndpoint"]["value"]
    assert by["searchClass"]["value"].startswith("4 classes match")
    assert by["spellCheck"]["status"] == "ok"                 # Spanish labels are not spell-checked as English
    assert not any(m["status"] == "error" for m in rep.metrics), rep.metrics
    codes = {i.code for i in rep.items}
    assert {"checkLabel", "definitionCheck", "duplicateLabels", "isolatedElements", "missingDomainRange"} <= codes
    dup = next(i for i in rep.items if i.code == "duplicateLabels")
    assert len(dup.affected) == 3 and "pizza" in dup.note       # taken from OntoCheck's own log output


def test_without_search_term_and_non_turtle_source(pizza):
    loaded, _ = pizza
    rep = run_ontocheck(loaded.graph, "pizza.owl", network=False)
    by = {m["metric"]: m for m in rep.metrics}
    assert by["searchClass"]["status"] == "skipped" and by["classSpaceCheck"]["status"] == "skipped"


def test_space_check_ignores_blank_node_fragments(fixtures):
    g = Graph().parse(fixtures / "real" / "prov-o.ttl")
    rep = run_ontocheck(g, fixtures / "real" / "prov-o.ttl", network=False)
    by = {m["metric"]: m for m in rep.metrics}
    assert by["classSpaceCheck"]["value"] == "None"            # OntoCheck's text heuristic misreads "[ a owl:Class"


def test_one_failing_metric_does_not_stop_the_others():
    rep = ontocheck_report({"checkLabel": {"error": "ValueError: boom"},
                            "humanLicense": {"value": 0, "items": []}})
    assert rep.metrics[0]["status"] == "error" and "checkLabel" in rep.scope
    assert [i.name for i in rep.items] == ["No human-readable license"]


def test_runs_between_reasoner_and_oops(pizza, monkeypatch):
    from ontoreview.quality_checks import oops
    from ontoreview.quality_checks.evaluators import run_evaluations
    from ontoreview.report.models import ExternalReport

    monkeypatch.setattr(oops, "run_oops", lambda *a, **k: ExternalReport("OOPS!", "x"))
    loaded, _ = pizza
    cfg = Config(evaluation={"robot": "off", "ontocheck_network": False})
    assert [r.tool for r in run_evaluations(loaded.graph, cfg)] == ["OntoCheck", "OOPS!"]
    off = Config(evaluation={"robot": "off", "ontocheck": "off", "oops": "off"})
    assert run_evaluations(loaded.graph, off) == []


def test_settings_round_trip():
    from ontoreview import ui_core

    s = ui_core.Settings(source="a.ttl", task="check", ontocheck=False, ontocheck_search="Pizza")
    assert "--no-ontocheck" in s.cli() and s.evaluation()["ontocheck"] == "off"
    assert s.evaluation()["ontocheck_search"] == "Pizza" and 'ontocheck = "off"' in s.to_toml()
    assert Config(evaluation={"ontocheck": False}).evaluation.ontocheck == "off"
