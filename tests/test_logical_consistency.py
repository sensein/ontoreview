"""Reasoner consistency check (quality_checks/logical_consistency.py, report/reasoner.py)."""

import os
import shutil
import stat
import subprocess
import textwrap

import pytest
from rdflib import Graph

from ontoreview.config import Config
from ontoreview.quality_checks.evaluators import run_evaluations
from ontoreview.quality_checks.logical_consistency import run_reasoner
from ontoreview.report.reasoner import parse_reason_output

UNSAT_LOG = """\
2026-11-18 01:08:32,205 ERROR org.obolibrary.robot.ReasonerHelper - There are 2 unsatisfiable classes in the ontology.
2026-11-18 01:08:32,206 ERROR org.obolibrary.robot.ReasonerHelper -     unsatisfiable: http://ex.org/o#D
2026-11-18 01:08:32,206 ERROR org.obolibrary.robot.ReasonerHelper -     unsatisfiable: http://ex.org/o#C
"""
INCONSISTENT_LOG = ("2026-11-18 01:08:33,724 ERROR org.obolibrary.robot.ReasonerHelper - The ontology is "
                    "inconsistent. TIP: use a tool like Protege to find explanations\n")

UNSAT_TTL = """\
@prefix : <http://ex.org/o#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://ex.org/o> a owl:Ontology .
:A a owl:Class . :B a owl:Class . :A owl:disjointWith :B .
:C a owl:Class ; rdfs:subClassOf :D . :D a owl:Class ; rdfs:subClassOf :A, :B .
"""
INCONSISTENT_TTL = """\
@prefix : <http://ex.org/o#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
<http://ex.org/o> a owl:Ontology .
:A a owl:Class . :B a owl:Class . :A owl:disjointWith :B .
:x a owl:NamedIndividual, :A, :B .
"""


def test_parse_reason_output():
    assert parse_reason_output("") == []
    [unsat] = parse_reason_output(UNSAT_LOG)
    assert (unsat.code, unsat.severity, unsat.affected) == (
        "unsatisfiable_class", "error", ["http://ex.org/o#C", "http://ex.org/o#D"])
    [inc] = parse_reason_output(INCONSISTENT_LOG, "elk")
    assert inc.code == "inconsistent_ontology" and "ELK" in inc.description


def _robot_stub(tmp_path, log_text, code):
    stub = tmp_path / "robot"
    (tmp_path / "out.log").write_text(log_text)
    stub.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$@" >> "{tmp_path / 'calls.log'}"
        cat "{tmp_path / 'out.log'}" >&2
        exit {code}
        """))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


@pytest.mark.real_evaluators
def test_run_reasoner_with_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin{os.pathsep}/bin")
    g = Graph().parse(data=UNSAT_TTL, format="turtle")
    _robot_stub(tmp_path, UNSAT_LOG, 1)
    rep = run_reasoner(g, "hermit")
    assert rep.tool == "Logical consistency" and rep.error is None and rep.summary["error"] == 2   # two unsatisfiable classes
    assert "reason --input" in (tmp_path / "calls.log").read_text() and "--reasoner hermit" in (tmp_path / "calls.log").read_text()
    _robot_stub(tmp_path, "", 0)                                   # consistent
    rep = run_reasoner(g, "elk")
    assert rep.error is None and rep.items == []
    _robot_stub(tmp_path, "OWLReasonerRuntimeException: boom\n", 1)  # crash, not a finding
    rep = run_reasoner(g)
    assert rep.items == [] and "boom" in rep.error
    with pytest.raises(ValueError):
        run_reasoner(g, "pellet")


@pytest.mark.real_evaluators
def test_reasoner_order_and_switches(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin{os.pathsep}/bin")
    _robot_stub(tmp_path, UNSAT_LOG, 1)        # `robot report` gets no output file -> report error
    g = Graph().parse(data=UNSAT_TTL, format="turtle")
    monkeypatch.setattr("ontoreview.quality_checks.oops.run_oops", lambda *a, **k: pytest.fail("no OOPS! upload"))
    tools = [r.tool for r in run_evaluations(g, Config(evaluation={"oops": "off"}))]
    assert tools == ["ROBOT", "Logical consistency"]
    assert [r.tool for r in run_evaluations(g, Config(evaluation={"oops": "off", "reasoner": "off"}))] == ["ROBOT"]
    assert run_evaluations(g, Config(evaluation={"oops": "off", "robot": "off"})) == []   # reasoner needs ROBOT


def test_config_default():
    assert Config().evaluation.reasoner == "hermit"
    assert Config(evaluation={"reasoner": "elk"}).evaluation.reasoner == "elk"


def _docker_ready():
    exe = shutil.which("docker")
    if not exe or os.environ.get("ONTOREVIEW_SKIP_DOCKER"):
        return False
    ok = subprocess.run([exe, "image", "inspect", "obolibrary/robot"], capture_output=True).returncode == 0
    return ok


@pytest.mark.real_evaluators
@pytest.mark.skipif(not _docker_ready(), reason="Docker with obolibrary/robot not available")
def test_hermit_in_docker():
    unsat = run_reasoner(Graph().parse(data=UNSAT_TTL, format="turtle"), "hermit", pull=False)
    assert [i.code for i in unsat.items] == ["unsatisfiable_class"]
    assert unsat.items[0].affected == ["http://ex.org/o#C", "http://ex.org/o#D"]
    inc = run_reasoner(Graph().parse(data=INCONSISTENT_TTL, format="turtle"), "hermit", pull=False)
    assert [i.code for i in inc.items] == ["inconsistent_ontology"]


def test_cli_and_ui_settings(fixtures):
    from typer.testing import CliRunner

    from ontoreview import ui_core
    from ontoreview.cli import app

    r = CliRunner().invoke(app, ["check", str(fixtures / "pizza.ttl"), "--reasoner", "pellet"])
    assert r.exit_code == 2 and "hermit, elk or off" in r.output
    r = CliRunner().invoke(app, ["check", str(fixtures / "pizza.ttl"), "--reasoner", "elk", "--fail-on", "never"])
    assert r.exit_code == 0, r.output
    s = ui_core.Settings(source="a.ttl", task="check", reasoner="elk")
    assert "--reasoner elk" in s.cli() and s.evaluation()["reasoner"] == "elk"
    assert 'reasoner = "elk"' in s.to_toml()
    p = ui_core.Prefs(reasoner="off")
    t = ui_core.Settings()
    p.apply(t)
    assert t.reasoner == "off"


def test_report_builders():
    from ontoreview.report.models import TOOLS, unavailable
    from ontoreview.report.reasoner import reasoner_report
    from ontoreview.report.robot import robot_report

    ok = reasoner_report(0, "", "elk")
    assert ok.tool == TOOLS["reasoner"].name and ok.items == [] and ok.note.endswith("(ELK).") and not ok.error
    bad = reasoner_report(1, UNSAT_LOG)
    assert bad.summary["error"] == 2 and not bad.note and not bad.error
    crash = reasoner_report(1, "java.lang.OutOfMemoryError\n")
    assert "OutOfMemoryError" in crash.error and crash.items == []
    assert "not available" in unavailable("robot", "obolibrary/robot").error
    assert robot_report(None, "boom").error == "boom"
    assert robot_report("Level\tRule Name\tSubject\nerror\tmissing_label\thttp://x/a\n").summary["error"] == 1


def test_readable_robot_errors_and_outside_dl():
    from ontoreview.report.reasoner import reasoner_report
    from ontoreview.report.robot import robot_message

    out = ("Non-simple property '<http://ex.org/n#partOf>' or its inverse appears in the cardinality restriction "
           "'ObjectMaxCardinality(1 <http://ex.org/n#partOf> owl:Thing)'.\n"
           "Use the -vvv option to show the stack trace.\nUse the --help option to see usage information.\n")
    assert robot_message(out).startswith("Non-simple property")
    assert robot_message("2026-11-18 01:08:33,724 ERROR org.x.Y - Something broke\nUse the --help option\n") == "Something broke"
    rep = reasoner_report(1, out, "hermit")
    [item] = rep.items
    assert item.code == "outside_owl2_dl" and item.severity == "warning" and "partOf" in item.note and not rep.error
    crash = reasoner_report(1, "OWLOntologyCreationException: bad syntax\nUse the --help option to see usage information.\n")
    assert crash.error.endswith("OWLOntologyCreationException: bad syntax")


def test_totals_include_external_checks():
    from ontoreview.report.models import ExternalItem, Finding, Report, new_report

    rep = Report(findings=[Finding("OB001", "t", "warning", "m")],
                 external=[new_report("robot", [ExternalItem("duplicate_label", "Duplicate label", "error",
                                                              affected=["http://x/a", "http://x/b"])]),
                           new_report("reasoner", [ExternalItem("inconsistent_ontology", "Inc", "error")])])
    assert rep.summary == {"error": 0, "warning": 1, "info": 0}            # built-in only
    assert rep.totals == {"error": 3, "warning": 1, "info": 0}             # per affected element
    assert rep.to_dict()["totals"] == rep.totals
