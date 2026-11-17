from ontoreview.checks import Rule, run_checks
from ontoreview.config import Config
from ontoreview.diff import compare_files


def _ids(report):
    return {f.rule for f in report.findings}


def test_planted_defects_are_found(pizza):
    loaded, o = pizza
    report = run_checks(o, loaded.graph, Config())
    ids = _ids(report)
    for expected in ("OB010", "OB011", "OB016", "OB018", "OB019", "OB023", "OB024"):
        assert expected in ids, expected
    # metadata is complete in the fixture
    for absent in ("OB001", "OB002", "OB003", "OB005"):
        assert absent not in ids
    assert report.failed("error")
    assert report.summary["error"] >= 1


def test_inverse_property_not_flagged_for_domain(pizza):
    loaded, o = pizza
    report = run_checks(o, loaded.graph, Config())
    flagged = {f.subject for f in report.findings if f.rule in ("OB012", "OB013")}
    assert "https://example.org/pizza#isToppingOf" not in flagged


def test_disable_and_severity_override(pizza):
    loaded, o = pizza
    cfg = Config(checks={"disable": ["OB024"], "severity": {"OB016": "error"}})
    report = run_checks(o, loaded.graph, cfg)
    assert "OB024" not in _ids(report)
    assert all(f.severity == "error" for f in report.findings if f.rule == "OB016")


def test_extra_rule(pizza):
    loaded, o = pizza
    rule = Rule("X001", "Always", "info", "test", lambda ctx: [(None, "hello")])
    report = run_checks(o, loaded.graph, Config(), [rule])
    assert any(f.rule == "X001" and f.message == "hello" for f in report.findings)


def test_linkml_has_no_naming_noise(personinfo):
    loaded, o = personinfo
    ids = _ids(run_checks(o, loaded.graph, Config()))
    assert "OB019" not in ids and "OB027" not in ids


def test_diff(fixtures):
    log = compare_files(str(fixtures / "pizza.ttl"), str(fixtures / "pizza-v2.ttl"))
    assert [c.label for c in log.added] == ["Calzone"]
    assert [c.label for c in log.removed] == ["spicy_thing"]
    food = next(c for c in log.modified if c.label == "Food")
    assert any("Anything that can be eaten" in v for _, v in food.added)
    assert log.old_version == "1.2.0" and log.new_version == "1.3.0"
    assert log.metadata_changes
    md = log.to_markdown()
    assert "## Added (1)" in md
