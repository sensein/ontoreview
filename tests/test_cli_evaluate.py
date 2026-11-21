"""`ontoreview evaluate`: every evaluation setting as an option, and a stable JSON result."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from ontoreview.cli import app
from ontoreview.cli_evaluate import parse_set
from ontoreview.config import EvaluationConfig

runner = CliRunner()


def test_every_evaluation_setting_is_an_option():
    r = runner.invoke(app, ["evaluate", "--list-options", "--format", "json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    names = {o["name"] for o in data["options"]}
    assert set(EvaluationConfig.model_fields) <= names
    assert {"only", "disable_rule", "severity"} <= names
    secret = next(o for o in data["options"] if o["name"] == "cdi_hf_token")
    assert secret["secret"] and secret["default"] is None


def test_evaluate_json_result(fixtures, tmp_path):
    out = tmp_path / "result.json"
    r = runner.invoke(app, ["evaluate", str(fixtures / "pizza.ttl"), "--only", "rules,iri", "--no-iri-network",
                            "--iri-timeout", "5", "--disable-rule", "OB019", "--severity", "OB011=info",
                            "-f", "json", "-o", str(out), "--fail-on", "never"])
    assert r.exit_code == 0, r.output
    d = json.loads(out.read_text())
    assert d["schema"] == "ontoreview.evaluation/1" and d["source"]["sha256"]
    assert d["evaluations"]["rules"]["status"] == "ran"
    assert d["evaluations"]["robot"]["status"] == "off" and d["evaluations"]["cdi"]["status"] == "off"
    assert d["settings"]["evaluation"]["iri_network"] is False and d["settings"]["evaluation"]["iri_timeout"] == 5
    assert "OB019" in d["settings"]["checks"]["disable"]
    assert not any(f["rule"] == "OB019" for f in d["report"]["findings"])
    assert all(f["severity"] == "info" for f in d["report"]["findings"] if f["rule"] == "OB011")
    assert isinstance(d["issues"], list) and "distinct_issues" in d["summary"]


def test_secrets_are_not_echoed(fixtures, tmp_path, monkeypatch):
    out = tmp_path / "r.json"
    r = runner.invoke(app, ["evaluate", str(fixtures / "pizza.ttl"), "--only", "rules", "--cdi-hf-token", "hf_secret",
                            "--cdi-api-keys", "bioportal=abc123", "-f", "json", "-o", str(out), "--fail-on", "never"])
    assert r.exit_code == 0, r.output
    text = out.read_text()
    assert "hf_secret" not in text and "abc123" not in text


def test_set_validates_like_the_config():
    assert parse_set(["cdi_tau=0.6", "iri_network=false", "cdi_references=ols,ref.ttl",
                      "si_domain_map=ols:emi=1.5;1.6"]) == {
        "cdi_tau": 0.6, "iri_network": False, "cdi_references": ["ols", "ref.ttl"],
        "si_domain_map": {"ols:emi": ["1.5", "1.6"]}}
    r = runner.invoke(app, ["check", "x.ttl", "--set", "cdi_tau=7"])           # out of range
    assert r.exit_code != 0
    r = runner.invoke(app, ["check", "x.ttl", "--set", "nonsense=1"])
    assert r.exit_code != 0 and "unknown setting" in r.output


def test_check_accepts_set(fixtures, tmp_path):
    out = tmp_path / "q.json"
    r = runner.invoke(app, ["check", str(fixtures / "pizza.ttl"), "--set", "iri_network=false", "-f", "json",
                            "-o", str(out), "--fail-on", "never"])
    assert r.exit_code == 0, r.output
    assert "summary" in json.loads(out.read_text())
