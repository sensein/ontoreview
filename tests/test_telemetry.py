"""Telemetry: what is sent, the mandatory / optional split, offline outbox, one event per run."""

from __future__ import annotations

import json
import re

import pytest

from ontoreview import telemetry
from ontoreview.config import Config

REAL_IS_CI = telemetry.is_ci
REAL_DISABLED = telemetry.disabled_reason
CI_ENV = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "BUILDKITE", "CIRCLECI", "TRAVIS", "TF_BUILD",
          "BITBUCKET_BUILD_NUMBER", "TEAMCITY_VERSION", "CODEBUILD_BUILD_ID", "DRONE", "APPVEYOR")


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


def test_full_opt_out_is_saved_and_discards_the_outbox(tel, monkeypatch):
    tel.online = False
    with telemetry.run("build"):
        pass
    assert telemetry.pending() == 2
    telemetry.set_enabled(False)
    assert telemetry.pending() == 0
    monkeypatch.setattr(telemetry, "disabled_reason", REAL_DISABLED)
    assert telemetry.disabled_reason().startswith("switched off")
    assert telemetry.track("run_completed", {"command": "build"}) is None
    telemetry.set_enabled(True)
    assert not (telemetry.disabled_reason() or "").startswith("switched off")


@pytest.fixture
def github(monkeypatch):
    for v in CI_ENV:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(telemetry, "is_ci", REAL_IS_CI)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY_ID", "123456")
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/private-repo")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("ONTOREVIEW_WORKFLOW", "ontoreview-init")


def test_github_actions_is_recorded_and_counted_per_repository(tel, github, monkeypatch):
    with telemetry.run("check"):
        pass
    [ev] = runs(tel)
    p = ev["properties"]
    assert p["is_ci"] is True and p["ci_provider"] == "github_actions" and p["ci_workflow"] == "ontoreview-init"
    assert p["ci_event"] == "pull_request" and p["ci_runner"] == "github-hosted"
    blob = json.dumps(ev, default=str)
    assert "private-repo" not in blob and "123456" not in blob
    first = ev["distinct_id"]
    assert first == telemetry.ci_project_id() != telemetry.install_id()     # one id per repository
    monkeypatch.setenv("GITHUB_REPOSITORY_ID", "999")
    assert telemetry.ci_project_id() != first
    assert [m["event"] for m in tel.sent] == ["run_completed"]               # runners are not new installs


def test_other_ci_providers(monkeypatch):
    for v in CI_ENV:
        monkeypatch.delenv(v, raising=False)
    assert telemetry.ci_provider() is None and telemetry.ci_props() == {}
    monkeypatch.setenv("GITLAB_CI", "true")
    assert telemetry.ci_provider() == "gitlab"
    assert telemetry.ci_props()["ci_workflow"] == "custom"
    monkeypatch.delenv("GITLAB_CI")
    monkeypatch.setenv("CI", "true")
    assert telemetry.ci_provider() == "other"


@pytest.fixture
def library(tel, monkeypatch):
    monkeypatch.setattr(telemetry, "_library_wanted", lambda: telemetry.enabled() and not telemetry.is_ci())
    monkeypatch.setattr(telemetry, "_library", None)
    monkeypatch.setattr(telemetry, "_api_calls", telemetry.Counter())
    return tel


def test_python_api_sends_one_event_per_process(library, fixtures, tmp_path):
    import ontoreview
    from ontoreview.collection import build_collection

    ontoreview.check(fixtures / "pizza.ttl")
    ontoreview.check(fixtures / "pizza.ttl")
    folder = tmp_path / "f"
    folder.mkdir()
    (folder / "a.ttl").write_text((fixtures / "pizza.ttl").read_text())
    build_collection(folder, tmp_path / "out")                       # calls build() inside: counted once
    assert runs(library) == []                                         # sent when the process ends
    telemetry._api_end()
    [ev] = runs(library)
    p = ev["properties"]
    assert p["surface"] == "library" and p["mode"] == "script" and p["command"] == "library"
    assert p["api_calls"] == {"check": 2, "build_collection": 1}
    assert "rules" in p["checks_run"] and p["outcome"] == "ok"
    assert str(fixtures) not in json.dumps(p) and "pizza" not in json.dumps(p).lower()


def test_python_api_failure_and_no_double_count_inside_cli(library, tmp_path):
    import ontoreview

    with pytest.raises(FileNotFoundError), telemetry.run("check"):
        ontoreview.check(tmp_path / "missing.ttl")                     # part of the CLI run, not the library
    assert telemetry._library is None
    with pytest.raises(FileNotFoundError):
        ontoreview.check(tmp_path / "missing.ttl")
    telemetry._api_end()
    lib = [m for m in runs(library) if m["properties"]["surface"] == "library"][0]["properties"]
    assert lib["outcome"] == "failed" and lib["error_class"] and lib["api_calls"] == {"check": 1}


def test_python_api_not_tracked_in_ci(library, github):
    import ontoreview

    with pytest.raises(FileNotFoundError):
        ontoreview.check("/nonexistent.ttl")
    telemetry._api_end()
    assert library.sent == []
