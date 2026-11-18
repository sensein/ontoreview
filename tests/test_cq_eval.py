import os
import stat
import textwrap

import pytest

import ontoreview
from ontoreview.config import Config
from ontoreview.cq import evaluate, load_cqs, load_many, write_template
from ontoreview.quality_checks import oops as oops_mod
from ontoreview.quality_checks.evaluators import run_evaluations
from ontoreview.quality_checks.robot import run_robot
from ontoreview.report.models import ExternalReport
from ontoreview.report.oops import parse_oops
from ontoreview.report.robot import parse_robot_tsv

NO_REASONER = Config(evaluation={"reasoner": "off"})   # ROBOT-report tests: the reasoner has its own tests


def test_yaml_cqs_are_evaluated(fixtures, pizza):
    loaded, onto = pizza
    cqs = evaluate(load_many([fixtures / "cq" / "pizza-cq.yaml"]), loaded.full_graph, onto)
    by_id = {q.id: q for q in cqs.questions}
    assert by_id["CQ1"].status == "passed" and by_id["CQ1"].rows == [["d:pepperoni"]]
    assert by_id["CQ2"].total_rows == 2
    assert by_id["CQ3"].status == "failed"
    assert by_id["CQ4"].status == "passed" and by_id["CQ4"].rows == [["true"]]
    assert by_id["CQ5"].status == "untested"
    assert {r.label for r in by_id["CQ1"].term_refs} == {"has topping", "Meat topping"}
    assert cqs.summary == {"passed": 3, "failed": 1, "error": 0, "untested": 1}


def test_csv_loose_headers_and_errors(fixtures, pizza):
    loaded, onto = pizza
    cqs = evaluate(load_cqs(fixtures / "cq" / "pizza-cq.csv"), loaded.full_graph, onto)
    assert [q.id for q in cqs.questions] == ["CQ1", "CQ2"]
    assert cqs.questions[0].status == "passed"
    assert cqs.questions[0].answer == "Meat and cheese toppings"
    assert cqs.questions[1].status == "error" and cqs.questions[1].error


def test_excel_roundtrip(tmp_path, pizza):
    import openpyxl

    loaded, onto = pizza
    path = tmp_path / "cq.xlsx"
    write_template(path)
    wb = openpyxl.load_workbook(path)
    wb.active.append(["CQ2", "Which classes are food?", "SELECT ?c WHERE { ?c rdfs:subClassOf pizza:Food }",
                      "", "pizza:Food", "", ""])
    wb.save(path)
    cqs = evaluate(load_cqs(path), loaded.full_graph, onto)
    assert [q.status for q in cqs.questions] == ["passed", "passed"]


def test_templates(tmp_path):
    for name in ("a.yaml", "a.csv", "a.tsv", "a.xlsx"):
        assert load_cqs(write_template(tmp_path / name)).questions[0].id == "CQ1"


def test_build_with_cqs(fixtures, tmp_path):
    res = ontoreview.build(fixtures / "pizza.ttl", out=tmp_path,
                        competency_questions=[str(fixtures / "cq" / "pizza-cq.yaml")])
    html = (tmp_path / "index.html").read_text()
    assert 'id="competency-questions"' in html and 'id="cq-CQ1"' in html
    assert 'href="#cq-CQ1"' in html  # back-link from a term entry
    assert any(f.rule == "CQ001" for f in res.report.findings)
    assert (tmp_path / "competency-questions.json").exists()


OOPS_SAMPLE = """<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:oops="http://oops.linkeddata.es/def#">
  <rdf:Description rdf:about="http://oops.linkeddata.es/data/1">
    <rdf:type rdf:resource="http://oops.linkeddata.es/def#pitfall"/>
    <oops:hasCode>P08</oops:hasCode><oops:hasName>Missing annotations</oops:hasName>
    <oops:hasImportanceLevel>Minor</oops:hasImportanceLevel>
    <oops:hasDescription>Elements lack   labels.</oops:hasDescription>
    <oops:hasAffectedElement>https://example.org/pizza#MeatTopping</oops:hasAffectedElement>
  </rdf:Description>
  <rdf:Description rdf:about="http://oops.linkeddata.es/data/2">
    <rdf:type rdf:resource="http://oops.linkeddata.es/def#pitfall"/>
    <oops:hasCode>P05</oops:hasCode><oops:hasName>Wrong inverse</oops:hasName>
    <oops:hasImportanceLevel>Critical</oops:hasImportanceLevel>
    <oops:hasAffectedElement>There are elements with different naming conventions</oops:hasAffectedElement>
  </rdf:Description>
  <rdf:Description rdf:about="http://oops.linkeddata.es/data/3">
    <rdf:type rdf:resource="http://oops.linkeddata.es/def#suggestion"/>
    <oops:hasName>Symmetric or transitive object properties</oops:hasName>
  </rdf:Description>
</rdf:RDF>"""


def test_parse_oops():
    items = parse_oops(OOPS_SAMPLE)
    assert [(i.code, i.severity) for i in items] == [("P05", "error"), ("P08", "info"), ("Suggestion", "info")]
    p08 = items[1]
    assert p08.affected == ["https://example.org/pizza#MeatTopping"] and p08.description == "Elements lack labels."
    assert items[0].note.startswith("There are elements")


ROBOT_TSV = "Level\tRule Name\tSubject\tProperty\tValue\nERROR\tmissing_label\tpizza:A\trdfs:label\t\n" \
            "WARN\tmissing_definition\tpizza:A\t\t\nWARN\tmissing_definition\tpizza:B\t\t\nINFO\tlowercase_definition\tpizza:B\t\t\n"


def test_parse_robot():
    items = parse_robot_tsv(ROBOT_TSV)
    assert [(i.code, i.severity, len(i.affected)) for i in items] == [
        ("missing_label", "error", 1), ("missing_definition", "warning", 2), ("lowercase_definition", "info", 1)]


def _fake_oops(monkeypatch):
    """Replace the OOPS! web call; returns the list of graphs it was called with."""
    calls = []

    def fake(graph, *a, **k):
        calls.append(graph)
        return ExternalReport("OOPS!", "https://oops.linkeddata.es", items=parse_oops(OOPS_SAMPLE))
    monkeypatch.setattr(oops_mod, "run_oops", fake)
    return calls


@pytest.mark.real_evaluators
def test_robot_stub(tmp_path, pizza, monkeypatch):
    loaded, _ = pizza
    oops_calls = _fake_oops(monkeypatch)
    canned = tmp_path / "canned.tsv"
    canned.write_text(ROBOT_TSV)
    stub = tmp_path / "robot"
    stub.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        # minimal stand-in for `robot report --input X --output Y ...`
        while [ $# -gt 0 ]; do if [ "$1" = "--output" ]; then out="$2"; fi; shift; done
        cp "{canned}" "$out"
        """))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    rep = run_robot(loaded.graph)
    assert rep is not None and rep.error is None and rep.summary == {"error": 1, "warning": 1, "info": 1}
    reports = run_evaluations(loaded.graph, NO_REASONER)
    assert [r.tool for r in reports] == ["ROBOT"] and not oops_calls  # ROBOT worked: no OOPS! fallback


@pytest.mark.real_evaluators
def test_no_robot_falls_back_to_oops(pizza, monkeypatch):
    loaded, _ = pizza
    oops_calls = _fake_oops(monkeypatch)
    monkeypatch.setenv("PATH", "/nonexistent")  # no robot, no docker
    reports = run_evaluations(loaded.graph, Config())
    assert [r.tool for r in reports] == ["OOPS!"] and len(oops_calls) == 1
    forced = run_evaluations(loaded.graph, Config(evaluation={"robot": "on"}))
    assert [r.tool for r in forced] == ["ROBOT", "Logical consistency", "OOPS!"]
    assert "not available" in forced[0].error and "not available" in forced[1].error


@pytest.mark.real_evaluators
def test_oops_off_never_uploads(pizza, monkeypatch):
    loaded, _ = pizza
    oops_calls = _fake_oops(monkeypatch)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert run_evaluations(loaded.graph, Config(evaluation={"oops": "off"})) == []
    assert run_evaluations(loaded.graph, Config(evaluation={"robot": "off"})) == []
    assert not oops_calls


def test_oops_config_accepts_booleans():
    assert Config(evaluation={"oops": True}).evaluation.oops == "on"
    assert Config(evaluation={"oops": False}).evaluation.oops == "off"
    assert Config().evaluation.oops == "auto" and Config().evaluation.robot == "auto"


def test_parse_oops_documented_namespace():
    doc = OOPS_SAMPLE.replace("http://oops.linkeddata.es/def#", "http://www.oeg-upm.net/oops#")
    assert [i.code for i in parse_oops(doc)] == [i.code for i in parse_oops(OOPS_SAMPLE)]


def _docker_stub(tmp_path, canned, has_image):
    """A fake `docker` CLI: answers `info`, `image inspect` and `run ... robot report`."""
    log = tmp_path / "docker.log"
    stub = tmp_path / "docker"
    stub.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo "$@" >> "{log}"
        case "$1" in
          info) echo 29.0.0; exit 0 ;;
          image) exit {0 if has_image else 1} ;;
          run)
            while [ $# -gt 0 ]; do
              if [ "$1" = "-v" ]; then host="${{2%%:/work}}"; fi
              if [ "$1" = "--output" ]; then out="$2"; fi
              shift
            done
            cp "{canned}" "$host/${{out#/work/}}" ;;
        esac
        """))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return log


@pytest.mark.real_evaluators
def test_robot_docker(tmp_path, pizza, monkeypatch):
    loaded, _ = pizza
    oops_calls = _fake_oops(monkeypatch)
    canned = tmp_path / "canned.tsv"
    canned.write_text(ROBOT_TSV)
    log = _docker_stub(tmp_path, canned, has_image=True)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin{os.pathsep}/bin")
    rep = run_robot(loaded.graph, image="obolibrary/robot")
    assert rep is not None and rep.error is None and rep.summary == {"error": 1, "warning": 1, "info": 1}
    calls = log.read_text()
    assert "run --rm" in calls and ":/work -w /work" in calls and "obolibrary/robot robot report" in calls
    assert not oops_calls


@pytest.mark.real_evaluators
def test_robot_docker_pulls_by_default(tmp_path, pizza, monkeypatch):
    loaded, _ = pizza
    oops_calls = _fake_oops(monkeypatch)
    canned = tmp_path / "canned.tsv"
    canned.write_text(ROBOT_TSV)
    log = _docker_stub(tmp_path, canned, has_image=False)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}/usr/bin{os.pathsep}/bin")
    reports = run_evaluations(loaded.graph, NO_REASONER)  # image missing: `docker run` pulls it
    assert [r.tool for r in reports] == ["ROBOT"] and reports[0].error is None
    assert "\nrun --rm" in f"\n{log.read_text()}" and not oops_calls


def test_llm_files(fixtures, tmp_path):
    import json

    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, competency_questions=[str(fixtures / "cq" / "pizza-cq.yaml")])
    llms = (tmp_path / "llms.txt").read_text()
    assert llms.startswith("# Pizza Ontology") and "[Classes](classes.md)" in llms and "ontology.json" in llms
    assert "### Pizza" in (tmp_path / "classes.md").read_text()
    assert "SELECT ?pizza" in (tmp_path / "llms-full.txt").read_text()
    data = json.loads((tmp_path / "ontology.json").read_text())
    pizza = next(t for t in data["terms"] if t.get("curie") == "pizza:Pizza")
    assert pizza["superclasses"] == ["pizza:Food"]
    assert 'type="text/markdown"' in (tmp_path / "index.html").read_text()


def test_llm_files_can_be_disabled(fixtures, tmp_path):
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, llm=False)
    assert not (tmp_path / "llms.txt").exists()
