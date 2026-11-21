"""Scientific interoperability: parity with the reference script, domain assignment, the
upper-level filter, the report section, the build record and the app settings. Offline: file and
SSSOM references, a fixed stand-in for the language model and for the domain classifier."""

import json

import pytest
from rdflib import Graph

import ontoreview
from ontoreview.config import EvaluationConfig
from ontoreview.quality_checks import cdi
from ontoreview.quality_checks.cdi import core, si
from ontoreview.ui_core import Settings


def fake_levels(text: str) -> list[float]:
    return [0.1, 0.2, 0.4, 0.2, 0.1] if len(text) > 60 else [0.5, 0.3, 0.1, 0.05, 0.05]


class FakeClassifier:
    """Stands in for the zero-shot domain classifier: one fixed answer per text."""

    def __init__(self, answer=("1.5", 0.9)):
        self.answer, self.seen = answer, []

    def classify(self, texts):
        self.seen += list(texts)
        return [self.answer for _ in texts]


@pytest.fixture
def toy(fixtures):
    d = fixtures / "cdi"
    return d / "toy_onto.ttl", d / "toy_ref.ttl", d / "toy_to_bfo.sssom.tsv"


MAP = {"file:toy_ref.ttl": ["1.5"], "sssom:toy_to_bfo.sssom.tsv": ["3.2", "1.6"]}


def _ev(**kw) -> EvaluationConfig:
    return EvaluationConfig(**{"cdi_ontoaligner": "off", "cdi_term_db": False, **kw})


def test_scores_match_reference_script(toy):
    onto_path, ref, sssom = toy
    onto = core.load_ontology(onto_path)
    res, _, rows, M = core.evaluate(onto, [core.LocalFileSource(ref), core.SSSOMSource(sssom)],
                                    core.CallableBackend(fake_levels), verbose=False)
    r, domains, assigned, m_no_u = si.evaluate_si(onto, res, rows, M, "4.1", "user", MAP, theta_s=0.3)
    # values produced by scientific_interoperability.py on the same inputs
    assert (r.si, r.covered_domains, r.n_correspondences_removed_upper) == (1, ["1.5 Earth and related environmental sciences"], 2)
    assert r.si_normalised == pytest.approx(1 / 41) and r.taxonomy_size == 42
    assert r.generality_ceiling == pytest.approx(0.555305, abs=1e-6) and r.proposition_holds
    top = {d["domain"]: d for d in domains}
    assert top["1.5"]["cdi_delta"] == pytest.approx(0.360828, abs=1e-6) and top["1.5"]["covered"]
    assert top["3.2"]["cdi_delta"] == pytest.approx(0.20951, abs=1e-5) and not top["3.2"]["covered"]
    assert "4.1" not in top                                   # the own domain is never counted
    assert all(not si.is_upper_entity(m.target) for m in m_no_u) and len(m_no_u) == len(M) - 2


def test_resolve_fos():
    assert si.resolve_fos("1.2") == "1.2" and si.resolve_fos("computer and information") == "1.2"
    assert si.resolve_fos("1.5 Earth and related environmental sciences") == "1.5"
    with pytest.raises(ValueError, match="matches"):
        si.resolve_fos("sciences")
    with pytest.raises(ValueError, match="no match"):
        si.resolve_fos("astrology")


def test_domain_assignment_priority():
    onts = [{"id": "ols:bfo", "domain": "", "title": "BFO"},
            {"id": "ols:envo", "domain": "environment", "title": "ENVO"},
            {"id": "ols:emi", "domain": "", "title": "Earth Metabolome", "description": "soil and water"},
            {"id": "ols:x", "domain": "health", "title": "X"},
            {"id": "ols:low", "domain": "", "title": "Low confidence"},
            {"id": "ols:none", "domain": "", "title": ""}]
    clf = FakeClassifier()
    clf.classify = lambda texts: [("1.5", 0.9) if "Earth" in t else ("1.1", 0.05) for t in texts]
    a = si.assign_domains(onts, {"ols:x": ["Mathematics"]}, clf)
    assert (a["ols:bfo"].source, a["ols:bfo"].domains) == ("upper", [])               # rule (a)
    assert (a["ols:envo"].source, a["ols:envo"].domains) == ("metadata", ["1.5"])     # crosswalk
    assert (a["ols:emi"].source, a["ols:emi"].domains) == ("classifier", ["1.5"])
    assert (a["ols:x"].source, a["ols:x"].domains) == ("override", ["1.1"])           # override beats metadata
    assert a["ols:low"].source == "none" and a["ols:none"].source == "none"            # below p_min / no text
    assert si.assign_domains([{"id": "ols:o", "domain": "upper"}])["ols:o"].source == "upper"


def test_report_section(toy):
    onto_path, ref, sssom = toy
    ev = _ev(cdi_references=[str(ref), str(sssom)], si_home_domain="4.1",
             si_domain_map={"file:toy_ref.ttl": ["1.5"]})
    cdi_rep, si_rep = cdi.run_interoperability(Graph().parse(onto_path), ev, str(onto_path),
                                               backend=core.CallableBackend(fake_levels), classifier=FakeClassifier(("1.1", 0.01)))
    assert cdi_rep.error is None and si_rep.error is None and si_rep.tool == "Scientific interoperability"
    m = {r["metric"]: r for r in si_rep.metrics}
    assert m["SI"]["value"].startswith("1 of 41 domains covered (1.5 Earth") and m["SI"]["status"] == "ok"
    assert m["D"]["value"] == "4.1 Agriculture, forestry, and fisheries (user)"
    assert m["1.5"]["status"] == "ok" and m["file:toy_ref.ttl"]["about"].startswith("your domain map")
    codes = {i.code: i for i in si_rep.items}
    assert "sssom:toy_to_bfo.sssom.tsv" in codes["SI-D"].note      # no domain: classifier below p_min
    s = si_rep.provenance["summary"]
    assert (s["si"], s["interoperable"], s["display"]) == (1, True, "1")
    assert s["display_note"] == "of 41 domains (θ_s = 0.3)"
    from ontoreview.report.models import Report
    tile = next(x for x in Report(external=[cdi_rep, si_rep]).scores() if x["tool"] == "Scientific interoperability")
    assert tile["display"] == "1" and tile["passed"] is True and tile["anchor"] == "quality-scientific-interoperability"


def test_home_domain_from_classifier_and_failures(toy):
    onto_path, ref, _ = toy
    g = Graph().parse(onto_path)
    ev = _ev(cdi_references=[str(ref)])
    # no title/description in the toy header and no setting: says what to set
    _, rep = cdi.run_interoperability(g, ev, str(onto_path), backend=core.CallableBackend(fake_levels),
                                      classifier=FakeClassifier())
    assert rep.error and "si_home_domain" in rep.error
    # Gen missing: SI cannot be computed and says why
    _, rep = cdi.run_interoperability(g, _ev(cdi_references=[str(ref)], cdi_generality=False, si_home_domain="1.2"),
                                      str(onto_path))
    assert rep.error.startswith("Not computed: needs the generality score")
    # classified own domain: reported, with a pointer to the setting
    header = {"title": "Soil sensing", "description": "pH readings"}
    code, how = si.resolve_home_domain(None, header, FakeClassifier(("4.1", 0.42)))
    assert code == "4.1" and how == "classifier (p = 0.42)"


@pytest.mark.real_cdi
def test_cdi_off_si_on_and_both_off(toy, monkeypatch):
    onto_path, ref, sssom = toy
    monkeypatch.setattr(cdi, "generality_backend", lambda ev: (core.CallableBackend(fake_levels), ""))
    g = Graph().parse(onto_path)
    reps = cdi.check_cdi(g, _ev(cdi="off", cdi_references=[str(ref), str(sssom)], si_home_domain="4.1",
                                si_domain_map=MAP), str(onto_path))
    assert [r.tool for r in reps] == ["Scientific interoperability"] and reps[0].error is None
    assert cdi.check_cdi(g, _ev(cdi="off", si="off")) == []
    only_cdi = cdi.check_cdi(g, _ev(si="off", cdi_references=[str(ref)]), str(onto_path))
    assert [r.tool for r in only_cdi] == ["Cross-domain interoperability"]


@pytest.mark.real_cdi
def test_build_writes_record(toy, tmp_path, monkeypatch):
    onto_path, ref, sssom = toy
    monkeypatch.setattr(cdi, "generality_backend", lambda ev: (core.CallableBackend(fake_levels), ""))
    ontoreview.build(onto_path, out=tmp_path, evaluation={
        "cdi_references": [str(ref), str(sssom)], "cdi_ontoaligner": "off", "si_home_domain": "4.1",
        "si_domain_map": MAP, "oops": "off"})
    rec = json.loads((tmp_path / "si.json").read_text())
    assert rec["summary"]["si"] == 1 and rec["per_domain"] and rec["domain_assignments"]
    assert rec["taxonomy"].startswith("OECD Fields of Science")
    html = (tmp_path / "index.html").read_text()
    overview = html.split('id="overview"', 1)[1].split("</section>", 1)[0]
    assert "Scientific interoperability" in overview and "of 41 domains" in overview
    assert 'id="quality-scientific-interoperability"' in html and "SI 1 of 41 scientific domains" in html


def test_app_settings(toy):
    s = Settings(source=str(toy[0]), si_home_domain="1.2", si_theta_s=0.4,
                 si_domain_map="ols:emi = 1.5; Biological sciences\nbioportal:NCIT = 3.2")
    ev = s.evaluation()
    assert ev["si_home_domain"] == "1.2" and ev["si_theta_s"] == 0.4
    assert ev["si_domain_map"] == {"ols:emi": ["1.5", "Biological sciences"], "bioportal:NCIT": ["3.2"]}
    assert EvaluationConfig(**ev).si_domain_map["ols:emi"] == ["1.5", "1.6"]
    cli = s.cli()
    assert "--si-home-domain 1.2" in cli and "--si-theta-s 0.4" in cli and "--si-domain 'ols:emi=1.5;Biological sciences'" in cli
    assert not s.validate()
    assert any("Own scientific domain" in p for p in Settings(source=str(toy[0]), si_home_domain="sciences").validate())
    assert any("ontology id = field" in p for p in Settings(source=str(toy[0]), si_domain_map="ols:emi 1.5").validate())
    off = Settings(source=str(toy[0]), si=False, cdi=False)
    assert off.evaluation()["si"] == "off" and "--no-si" in off.cli() and "--no-cdi" in off.cli()
    only_si = Settings(source=str(toy[0]), cdi=False, cdi_references="ols:envo")
    assert only_si.evaluation()["cdi_references"] == ["ols:envo"]        # SI still needs the references


def test_toml_round_trip(toy, tmp_path):
    s = Settings(source=str(toy[0]), si_home_domain="1.2", si_theta_s=0.35, si_domain_map="ols:emi = 1.5")
    f = tmp_path / "ontoreview.toml"
    f.write_text(s.to_toml())
    back = Settings.from_toml(f)
    assert (back.si, back.si_home_domain, back.si_theta_s, back.si_domain_map) == (True, "1.2", 0.35, "ols:emi = 1.5")
    from ontoreview.config import load_config
    ev = load_config(f).evaluation
    assert ev.si_home_domain == "1.2" and ev.si_domain_map == {"ols:emi": ["1.5"]}


def test_cli_overrides():
    from ontoreview.cli import _eval_overrides, _si_overrides
    ev = _eval_overrides(None, None, si=_si_overrides(False, "Mathematics", 0.25, ["ols:emi=1.5;1.6"]))
    assert ev == {"si_home_domain": "Mathematics", "si_theta_s": 0.25, "si_domain_map": {"ols:emi": ["1.5", "1.6"]}}
    ev = _eval_overrides(None, None, cdi=["ols"], no_cdi=True, si={})
    assert ev["cdi"] == "off" and ev["cdi_references"] == ["ols"]        # --no-cdi with references: SI only
