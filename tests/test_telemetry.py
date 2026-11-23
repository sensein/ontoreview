"""Telemetry: what is sent, the mandatory / optional split, offline outbox, one event per run."""

from __future__ import annotations

import json
import re

import pytest

from ontoreview import telemetry
from ontoreview.config import Config


class FakeClient:
    def __init__(self, online: bool = True):
        self.online = online
        self.sent: list[dict] = []

    def capture(self, event, **kw):
        if not self.online:
            telemetry._on_error(ConnectionError("offline"), [kw])
            return None
        self.sent.append({"event": event, **kw})
        return kw.get("uuid")


@pytest.fixture
def tel(monkeypatch, tmp_path):
    """Telemetry switched on, with a fake PostHog client; returns the client."""
    client = FakeClient()
    monkeypatch.setattr(telemetry, "STATE_FILE", tmp_path / "telemetry.json")
    monkeypatch.setattr(telemetry, "disabled_reason", lambda: None)
    monkeypatch.setattr(telemetry, "_get_client", lambda: client)
    monkeypatch.setattr(telemetry, "_kick", telemetry._drain)          # send synchronously in tests
    monkeypatch.setattr(telemetry, "_sample", True)
    monkeypatch.setattr(telemetry, "_ID", None)
    monkeypatch.setattr(telemetry, "is_ci", lambda: False)
    monkeypatch.setattr(telemetry, "is_docker", lambda: False)
    monkeypatch.setattr(telemetry, "_BASE", None)
    monkeypatch.delenv("ONTOREVIEW_TELEMETRY_DETAILS", raising=False)
    return client


def runs(client):
    return [m for m in client.sent if m["event"] == "run_completed"]


def test_key_is_assembled_at_run_time():
    key = telemetry._key()
    assert key.startswith("phc_") and len(key) == 48
    assert key not in (telemetry.__file__ and open(telemetry.__file__, encoding="utf-8").read())


def test_off_in_tests_and_with_do_not_track(monkeypatch):
    assert not telemetry.enabled()
    monkeypatch.setattr(telemetry, "__version__", "1.0.0")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ONTOREVIEW_TELEMETRY", "on")
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    assert telemetry.disabled_reason() == "DO_NOT_TRACK is set"
    assert telemetry.track("run_completed", {"command": "build"}) is None


def test_one_event_per_run_with_mandatory_and_optional(tel):
    cfg = Config()
    with telemetry.run("check", flags=["--no-oops"]):
        telemetry.note_evaluations(cfg, [])
        with telemetry.run("nested"):               # nested runs do not send their own event
            pass
    [ev] = runs(tel)
    p = ev["properties"]
    assert p["command"] == "check" and p["outcome"] == "ok"
    assert {"robot", "iri", "cdi", "si"} <= set(p["checks_run"])
    assert p["check_status"]["robot"] == "skipped"
    assert p["flags_used"] == ["--no-oops"] and p["mode"] in ("cli", "headless")
    assert p["$process_person_profile"] is False and ev["uuid"] and ev["timestamp"]
    # first event of a new install also sends install_first_seen, once
    assert [m["event"] for m in tel.sent].count("install_first_seen") == 1


def test_optional_details_off_keeps_mandatory_only(tel):
    telemetry.set_details(False)
    with telemetry.run("build", flags=["--reason"]):
        telemetry.note_evaluations(Config(), [])
    p = runs(tel)[0]["properties"]
    assert "checks_run" in p and "command" in p
    assert not [k for k in p if telemetry.TIERS.get(k) == "optional"]


def test_env_switch_turns_details_off(tel, monkeypatch):
    monkeypatch.setenv("ONTOREVIEW_TELEMETRY_DETAILS", "0")
    with telemetry.run("build", flags=["--reason"]):
        pass
    assert "flags_used" not in runs(tel)[0]["properties"]


def test_failures_and_exit_codes(tel):
    with pytest.raises(ValueError), telemetry.run("build"):
        raise ValueError("secret path /home/me/onto.ttl")
    with pytest.raises(SystemExit), telemetry.run("check"):
        raise SystemExit(1)
    a, b = (m["properties"] for m in runs(tel))
    assert a["outcome"] == "failed" and a["error_class"] == "ValueError"
    assert "/home/me" not in json.dumps(a)
    assert b["outcome"] == "nonzero_exit" and b["exit_code"] == 1


def test_real_check_sends_no_content(tel, fixtures):
    from ontoreview.build import check

    with telemetry.run("check"):
        check(fixtures / "pizza.ttl")
    p = runs(tel)[0]["properties"]
    assert p["ontology_format"] == "ttl" and p["classes"] != "0" and "rules" in p["checks_run"]
    assert set(p) - {"$process_person_profile"} <= set(telemetry.TIERS)
    blob = json.dumps(p)
    assert "pizza" not in blob.lower() and str(fixtures) not in blob and "http" not in blob


def test_offline_events_are_kept_and_sent_later(tel):
    tel.online = False
    with telemetry.run("build"):
        pass
    assert tel.sent == [] and telemetry.pending() == 2          # install_first_seen + run_completed
    tel.online = True
    telemetry._drain()
    assert telemetry.pending() == 0
    assert [m["event"] for m in tel.sent] == ["install_first_seen", "run_completed"]
    assert len({m["uuid"] for m in tel.sent}) == 2              # PostHog de-duplicates on these


def test_daily_cap(tel, monkeypatch):
    monkeypatch.setattr(telemetry, "DAILY_CAP", 3)
    for _ in range(5):
        with telemetry.run("build"):
            pass
    assert len(tel.sent) == 3
    assert json.loads(telemetry.STATE_FILE.read_text())["capped"] == 3   # 1 first_seen + 2 runs, 3 dropped


def test_ci_does_not_count_as_new_install(tel, monkeypatch):
    monkeypatch.setattr(telemetry, "is_ci", lambda: True)
    with telemetry.run("check"):
        pass
    assert [m["event"] for m in tel.sent] == ["run_completed"]
    assert runs(tel)[0]["properties"]["sample_rate"] == telemetry.CI_SAMPLE


def test_same_user_same_id(tel, tmp_path, monkeypatch):
    first = telemetry.install_id()
    telemetry.STATE_FILE.unlink()                               # settings deleted / reinstalled
    monkeypatch.setattr(telemetry, "_ID", None)
    assert telemetry.install_id() == first
    assert re.fullmatch(r"[0-9a-f-]{36}", first)


def test_ui_session_counts(tel):
    telemetry.start_session()
    telemetry.note_page("build")
    telemetry.note_page("build")
    telemetry.note_settings_tab("telemetry")
    with telemetry.run("build", surface="ontoreview-ui", task="site"):
        pass
    telemetry.end_session()
    s = [m for m in tel.sent if m["event"] == "ui_session"][0]["properties"]
    assert s["tasks_run_count"] == 1 and s["pages_visited"] == {"build": 2} and s["mode"] == "ui"


@pytest.mark.parametrize("argv,cmd", [(["build", "a.ttl"], "build"), (["terms", "search", "x"], "terms search"),
                                       (["--help"], None), ([], None), (["build", "--help"], None)])
def test_cli_command(argv, cmd):
    assert telemetry.cli_command(argv) == cmd


def test_cli_flags_never_values():
    assert telemetry.cli_flags(["build", "/secret/a.ttl", "--robot=off", "--base-url", "https://x"]) == \
        ["--base-url", "--robot"]


def test_buckets():
    assert [telemetry.bucket(n) for n in (0, 5, 150, 1500, 20000)] == ["0", "1-100", "100-1k", "1k-10k", "10k+"]
    assert telemetry.model_family("Qwen/Qwen3.5-4B") == "qwen" and telemetry.model_family("my-model") == "other"


def test_spec_is_consistent():
    names = [p.name for p in telemetry.SPEC]
    assert len(names) == len(set(names))
    for must in ("install_id", "$geoip_country_code", "mode", "command", "checks_run", "outcome"):
        assert telemetry.TIERS[must] == "mandatory"
