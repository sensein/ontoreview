"""Anonymous usage telemetry (PostHog).

What is sent, and which part can be switched off, is listed in :data:`SPEC`; the same table is shown
in the app (Settings › Telemetry) and by ``ontoreview telemetry show``. In short:

* **Mandatory (usage)**: an anonymous install id, country, how OntoReview is used (app, terminal or
  headless), which command / task and which quality checks ran, whether it worked, and the platform.
* **Optional (details)**, on by default: bucketed counts and categories that help improve the checks
  (check status, ontology size, finding counts, documentation options, AI provider, pages visited).

Never sent: ontology content, IRIs, file paths, URLs, labels, prompts, AI answers, keys or tokens.
Keys that are not in :data:`SPEC` are dropped before anything leaves the machine.

Three events only (PostHog bills per event): ``run_completed`` (one per CLI command or app task),
``ui_session`` (one per app session) and ``install_first_seen`` (once per install). Everything else is a
property of those events. Sending happens on a background thread and never fails or slows a run.

Switches: ``ontoreview telemetry disable`` / Settings › Telemetry / ``ONTOREVIEW_TELEMETRY_DETAILS=0``
turn off the optional details; ``DO_NOT_TRACK=1`` turns off everything.
"""

from __future__ import annotations

import atexit
import base64
import json
import logging
import os
import platform
import random
import sys
import threading
import time
import uuid
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

from . import __version__

log = logging.getLogger(__name__)


class _DropPostHog(logging.Filter):
    """Drop urllib3's connection lines for the PostHog host (shown with --verbose otherwise)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return "posthog.com" not in record.getMessage() and HOST.split("//")[-1] not in record.getMessage()
        except Exception:  # noqa: BLE001
            return True


def _quiet() -> None:
    """Telemetry never writes to the console or the app's log panel, not even with --verbose.
    ONTOREVIEW_TELEMETRY_DEBUG=1 shows its messages again (for development)."""
    if (os.environ.get("ONTOREVIEW_TELEMETRY_DEBUG") or "").strip() in ("1", "true", "on"):
        return
    for name in (__name__, "posthog"):
        lg = logging.getLogger(name)
        lg.handlers[:] = [logging.NullHandler()]
        lg.propagate = False
    for name in ("urllib3.connectionpool", "requests"):
        logging.getLogger(name).addFilter(_DropPostHog())



HOST = os.environ.get("ONTOREVIEW_TELEMETRY_HOST", "https://us.i.posthog.com")
STATE_FILE = Path(os.environ.get("ONTOREVIEW_TELEMETRY_FILE",
                                 Path.home() / ".config" / "ontoreview" / "telemetry.json"))
DAILY_CAP = 30          # events per install per day; the rest are dropped and counted (capped_count)
CI_SAMPLE = 0.1         # share of CI / container runs that are sent (sample_rate on the event)
LAST_EVENTS = 10        # kept locally for "show what is sent"
DOCS = "https://github.com/sensein/ontoreview#telemetry"

# The project key is a public, write-only PostHog key ("phc_…": it can send events, not read them).
# It is kept in pieces and joined at run time so plain-text scrapers do not pick it up.
_K = (("3", "K~7O<T2)Lk"), ("0", "X;)ZtUt?%+"), ("5", "WOPenR&YXe"),
      ("1", "S4%cmNOf;f"), ("4", "WHd`iXH7>~"), ("2", "Q+aw!YFBba"))


def _key() -> str:
    return "".join(base64.b85decode(v).decode()[::-1] for _, v in sorted(_K, key=lambda p: int(p[0])))


_quiet()

Tier = Literal["mandatory", "optional"]


@dataclass(frozen=True)
class Prop:
    name: str
    tier: Tier
    events: str          # run, ui, install or a combination ("run, ui, install")
    example: str
    purpose: str


# One table drives the allowlist, the Settings table, `ontoreview telemetry show` and the tests.
SPEC: tuple[Prop, ...] = (
    # ---- mandatory: who uses it, where, how and with what
    Prop("install_id", "mandatory", "all", "random UUID (made on first run)",
         "Counts active installs (daily / weekly / monthly) and retention, not downloads"),
    Prop("$geoip_country_code", "mandatory", "all", "US, DE, NP",
         "Country of use; looked up by PostHog from the connection, the IP address is then discarded"),
    Prop("$geoip_continent_code", "mandatory", "all", "NA, EU, AS", "Region rollup of the country"),
    Prop("tz_country", "mandatory", "all", "US, IN",
         "Country from the system time zone (fallback behind VPNs and proxies)"),
    Prop("mode", "mandatory", "all", "ui, cli, headless",
         "How it is used: the app, an interactive terminal, or scripts / automation with no terminal"),
    Prop("is_ci", "mandatory", "all", "true / false", "Separates CI pipelines from people"),
    Prop("is_docker", "mandatory", "all", "true / false", "Runs inside a container"),
    Prop("surface", "mandatory", "run, ui", "ontoreview, ontoreview-ui", "Entry point"),
    Prop("command", "mandatory", "run", "build, check, evaluate, diff, export, fix list, terms search",
         "Which commands and app tasks are used"),
    Prop("task", "mandatory", "run", "site, single, markdown, check, interop, diff",
         "The app task (Build screen format) behind the command"),
    Prop("checks_run", "mandatory", "run", "rules, robot, reasoner, iri, ontocheck, cdi, si, oops",
         "Which quality checks people run"),
    Prop("outcome", "mandatory", "run", "ok, failed, cancelled, nonzero_exit", "Whether it works for people"),
    Prop("exit_code", "mandatory", "run", "0, 1, 2", "CLI exit status (1 can mean findings above --fail-on)"),
    Prop("error_class", "mandatory", "run", "ParseError, TimeoutError",
         "Most common failures (exception type name only, never the message)"),
    Prop("duration_bucket", "mandatory", "run", "<1s, 1-10s, 10-60s, 1-5m, >5m", "Performance in practice"),
    Prop("session_duration_bucket", "mandatory", "ui", "<1m, 1-5m, 5-30m, 30m-2h, >2h",
         "How long people stay in the app"),
    Prop("tasks_run_count", "mandatory", "ui", "3", "Tasks run in an app session"),
    Prop("version", "mandatory", "all", "1.0.2", "Version adoption"),
    Prop("python", "mandatory", "all", "3.12", "Supported Python range"),
    Prop("os", "mandatory", "all", "darwin, linux, windows", "Platform support"),
    Prop("arch", "mandatory", "all", "arm64, x86_64", "Platform support"),
    Prop("extras", "mandatory", "all", "ui, cdi, reason, excel", "Which optional installs are used"),
    Prop("sample_rate", "mandatory", "all", "1.0, 0.1", "Share of runs sent (CI is sampled), to scale counts"),
    Prop("capped_count", "mandatory", "all", "0, 12", "Events dropped by the daily limit the day before"),
    # ---- optional: details that help improve the checks and the app
    Prop("check_status", "optional", "run", "robot: ran, oops: failed, cdi: skipped",
         "Why checks do not run (no Docker, no network, …)"),
    Prop("robot_mode", "optional", "run", "local, docker, off", "How ROBOT is set up"),
    Prop("reasoner", "optional", "run", "hermit, elk, off", "Reasoner choice"),
    Prop("findings", "optional", "run", "error: 1-10, warning: 10-100, info: 0",
         "Typical quality of reviewed ontologies (bucketed counts, no findings themselves)"),
    Prop("ontology_format", "optional", "run", "ttl, owl, jsonld, yaml", "Which input formats to prioritise"),
    Prop("ontology_kind", "optional", "run", "rdf, linkml", "RDF / OWL / SKOS or LinkML"),
    Prop("classes", "optional", "run", "0, 1-100, 100-1k, 1k-10k, 10k+", "Scale to design for (bucketed)"),
    Prop("properties", "optional", "run", "1-100", "Scale to design for (bucketed)"),
    Prop("individuals", "optional", "run", "0", "Scale to design for (bucketed)"),
    Prop("concepts", "optional", "run", "100-1k", "SKOS use (bucketed)"),
    Prop("has_imports", "optional", "run", "true / false", "owl:imports use"),
    Prop("is_folder", "optional", "run", "true / false", "Collections (a folder of ontologies)"),
    Prop("ontologies", "optional", "run", "1, 2-10, 10-50, 50+", "Collection size (bucketed)"),
    Prop("docs_layout", "optional", "run", "single, multi", "Documentation layout"),
    Prop("docs_languages", "optional", "run", "1, 2", "Multilingual documentation (count only)"),
    Prop("docs_graph_notation", "optional", "run", "vowl, uml", "Figure notation"),
    Prop("docs_custom_theme", "optional", "run", "true / false", "Custom themes or CSS (yes / no only)"),
    Prop("docs_sections_off", "optional", "run", "graph, changelog", "Documentation sections turned off"),
    Prop("ai_source", "optional", "run, ui", "ollama, hf, api", "AI fix suggestions: where the model runs"),
    Prop("ai_provider", "optional", "run, ui", "openai, anthropic, ollama", "AI provider"),
    Prop("ai_model_family", "optional", "run, ui", "qwen, gpt, claude, llama, other", "Model family only"),
    Prop("ai_requests", "optional", "run, ui", "1-10", "AI requests (bucketed)"),
    Prop("features", "optional", "run, ui", "deploy: 1, fix_write: 2", "Other features used (counts)"),
    Prop("flags_used", "optional", "run", "--no-oops, --reason", "CLI option names (never their values)"),
    Prop("pages_visited", "optional", "ui", "build: 4, compare: 1, fixes: 2", "Which parts of the app are used"),
    Prop("settings_tabs", "optional", "ui", "checks, ai", "Which settings people change"),
)
TIERS: dict[str, Tier] = {p.name: p.tier for p in SPEC}
_SENT_BY_POSTHOG = {"$geoip_country_code", "$geoip_continent_code"}   # added server side, never by us
_POSTHOG_KEYS = {"$process_person_profile", "$lib_version_ontoreview"}
EVENTS = ("run_completed", "ui_session", "install_first_seen")

NEVER_SENT = ("ontology content, IRIs and labels", "file paths and URLs", "competency questions",
              "AI prompts and answers", "API keys and tokens", "ORCID, names, e-mail addresses",
              "git remotes and deploy targets", "IP address, city or coordinates (dropped after the country lookup)")

TASK_COMMANDS = {"site": "build", "single": "build", "markdown": "export", "myst": "export",
                 "check": "check", "interop": "check", "diff": "diff"}
CLI_GROUPS = {"terms", "fix", "telemetry"}
_CI_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "BUILDKITE", "CIRCLECI", "TRAVIS", "TF_BUILD",
            "BITBUCKET_BUILD_NUMBER", "TEAMCITY_VERSION", "CODEBUILD_BUILD_ID", "DRONE", "APPVEYOR")


# ------------------------------------------------------------------ switches and local state
def _falsy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("0", "false", "off", "no")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "on", "yes")


def disabled_reason() -> str | None:
    """Why nothing is sent at all, or ``None`` when telemetry is active."""
    if _truthy(os.environ.get("DO_NOT_TRACK")):
        return "DO_NOT_TRACK is set"
    if _falsy(os.environ.get("ONTOREVIEW_TELEMETRY")):
        return "ONTOREVIEW_TELEMETRY is off (tests and development)"
    if "dev" in __version__ or "PYTEST_CURRENT_TEST" in os.environ:
        return "development build"
    return None


def enabled() -> bool:
    return disabled_reason() is None


_lock = threading.RLock()


def _read_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(data: dict[str, Any]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), "utf-8")
        tmp.replace(STATE_FILE)
    except OSError as e:   # telemetry is never worth failing a run over
        log.debug("could not save telemetry state: %s", e)


def details_enabled() -> bool:
    """Whether the optional details are sent (on unless switched off)."""
    if _falsy(os.environ.get("ONTOREVIEW_TELEMETRY_DETAILS")):
        return False
    return bool(_read_state().get("details", True))


def details_env_locked() -> bool:
    """The optional details are switched off by the environment (the setting cannot turn them on)."""
    return _falsy(os.environ.get("ONTOREVIEW_TELEMETRY_DETAILS"))


def set_details(on: bool) -> None:
    with _lock:
        st = _read_state()
        st["details"] = bool(on)
        _write_state(st)


def last_events() -> list[dict]:
    return list(_read_state().get("last_events", []))


_ID_NAMESPACE = uuid.UUID("6f6e746f-7265-7669-6577-74656c656d31")   # fixed: ids are only comparable to ours


def _machine_id() -> str | None:
    """The operating system's own machine id (never sent: only a one-way hash of it is used)."""
    for f in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = Path(f).read_text().strip()
            if v:
                return v
        except OSError:
            pass
    try:
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True,
                                 text=True, timeout=2).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=", 1)[1].strip().strip('"')
        elif sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
    except Exception:  # noqa: BLE001
        pass
    return None


def anonymous_id() -> str:
    """A stable, anonymous id for this user on this computer.

    A one-way hash (UUID v5, OntoReview's own namespace) of the machine id and the OS user id, so the same
    person running OntoReview many times, from several virtual environments, after reinstalling or after the
    settings file was deleted or could not be written, is still counted once. The machine id and user name
    never leave the computer and cannot be recovered from the id. Falls back to a random id."""
    mid = _machine_id()
    if not mid:
        return str(uuid.uuid4())
    try:
        user = str(os.getuid())                       # type: ignore[attr-defined]
    except AttributeError:
        user = os.environ.get("USERNAME", "")
    return str(uuid.uuid5(_ID_NAMESPACE, f"{mid}:{user}"))


_ID: str | None = None


def install_id() -> str:
    """The anonymous id (the saved one, else :func:`anonymous_id`; the same for the whole process)."""
    global _ID
    with _lock:
        st = _read_state()
        iid = st.get("install_id") or _ID
        if not iid:
            iid = anonymous_id()
            st.update(install_id=iid, created=date.today().isoformat(), first_seen_pending=True)
            _write_state(st)
        _ID = iid
        return iid


def first_run_notice() -> str | None:
    """A one-time notice (returned once per install, then ``None``)."""
    if not enabled():
        return None
    with _lock:
        st = _read_state()
        if st.get("notice_shown"):
            return None
        st["notice_shown"] = True
        _write_state(st)
    return ("OntoReview sends anonymous usage statistics (country, commands and checks run, platform; never your "
            "ontologies, paths or keys). Optional details can be switched off with `ontoreview telemetry disable` "
            f"or in Settings › Telemetry. Details: {DOCS}")


# ------------------------------------------------------------------ environment
def bucket(n: int | float | None, edges: tuple[int, ...] = (1, 100, 1000, 10000)) -> str:
    """0 → "0", 42 → "1-100", 1500 → "1k-10k", 20000 → "10k+"."""
    n = int(n or 0)
    if n <= 0:
        return "0"

    def k(v: int) -> str:
        return f"{v // 1000}k" if v >= 1000 else str(v)

    for lo, hi in zip(edges, edges[1:], strict=False):
        if lo <= n < hi:
            return f"{k(lo)}-{k(hi)}"
    return f"{k(edges[-1])}+"


def duration_bucket(seconds: float) -> str:
    for limit, label in ((1, "<1s"), (10, "1-10s"), (60, "10-60s"), (300, "1-5m")):
        if seconds < limit:
            return label
    return ">5m"


def session_bucket(seconds: float) -> str:
    for limit, label in ((60, "<1m"), (300, "1-5m"), (1800, "5-30m"), (7200, "30m-2h")):
        if seconds < limit:
            return label
    return ">2h"


def is_ci() -> bool:
    return any(os.environ.get(v) and not _falsy(os.environ.get(v)) for v in _CI_VARS)


def is_docker() -> bool:
    return Path("/.dockerenv").exists() or bool(os.environ.get("KUBERNETES_SERVICE_HOST"))


def _tz_name() -> str | None:
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz:
        return tz
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        return None
    marker = "zoneinfo/"
    return target.split(marker, 1)[1] if marker in target else None


def tz_country() -> str | None:
    """ISO country code of the system time zone (zone.tab of the system tz database), offline."""
    name = _tz_name()
    if not name:
        return None
    import zoneinfo

    for base in list(zoneinfo.TZPATH) + ["/usr/share/zoneinfo"]:
        try:
            for line in (Path(base) / "zone.tab").read_text("utf-8").splitlines():
                cols = line.split("\t")
                if len(cols) >= 3 and not line.startswith("#") and cols[2] == name:
                    return cols[0]
        except OSError:
            continue
    return None


def _extras() -> list[str]:
    from importlib.util import find_spec

    probes = {"ui": "nicegui", "cdi": "transformers", "reason": "owlrl", "excel": "openpyxl"}
    return sorted(k for k, mod in probes.items() if find_spec(mod) is not None)


def _base_cache() -> dict[str, Any]:
    global _BASE
    if _BASE is None:
        _BASE = {"version": __version__, "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                 "os": {"win32": "windows"}.get(sys.platform, sys.platform),
                 "arch": platform.machine().lower() or "unknown", "extras": _extras(), "is_ci": is_ci(),
                 "is_docker": is_docker(), "tz_country": tz_country()}
    return dict(_BASE)


_BASE: dict[str, Any] | None = None


def detect_mode(surface: str) -> str:
    if surface == "ontoreview-ui":
        return "ui"
    try:
        return "cli" if sys.stdin.isatty() and sys.stdout.isatty() else "headless"
    except (AttributeError, ValueError):
        return "headless"


# ------------------------------------------------------------------ sending (outbox first, offline-safe)
OUTBOX_MAX = 200        # events kept while offline; the oldest are dropped beyond this
OUTBOX_DAYS = 14        # events older than this are not sent any more
_client = None
_sample: bool | None = None
_drainer: threading.Thread | None = None
_failed = threading.Event()


def _on_error(error, batch) -> None:      # called on the sending thread (sync_mode)
    _failed.set()
    log.debug("telemetry: not delivered (%s); kept for later", error)


def _get_client():
    global _client
    if _client is None:
        from posthog import Posthog

        # sync_mode: each send happens on our own background thread and reports failure to _on_error,
        # so an event leaves the outbox only once PostHog has it.
        # disable_geoip=False: PostHog derives the country from the connection; the IP itself is removed
        # by the project's ingestion transformation (see DECISIONS.md D-046)
        _client = Posthog(_key(), host=HOST, disable_geoip=False, sync_mode=True, timeout=4, max_retries=0,
                          on_error=_on_error, enable_exception_autocapture=False, enable_local_evaluation=False)
    return _client


def _outbox_add(msg: dict) -> None:
    st = _read_state()
    box = [m for m in st.get("outbox", []) if isinstance(m, dict)]
    st["outbox"] = (box + [msg])[-OUTBOX_MAX:]
    _write_state(st)


def pending() -> int:
    """Events waiting to be sent (e.g. collected while offline)."""
    return len(_read_state().get("outbox", []))


def _drain() -> None:
    """Send the outbox, oldest first; stop at the first failure (offline) and keep the rest for next time."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=OUTBOX_DAYS)
    while True:
        with _lock:
            box = list(_read_state().get("outbox", []))
        if not box:
            return
        msg = box[0]
        try:
            when = datetime.fromisoformat(msg["timestamp"])
        except (KeyError, ValueError, TypeError):
            when = None
        ok = True
        if when is not None and when >= cutoff:
            _failed.clear()
            props = msg.get("properties") or {}
            if not details_enabled():       # switched off after the event was queued: drop the optional part
                props = {k: v for k, v in props.items() if TIERS.get(k) != "optional"}
            try:
                _get_client().capture(msg["event"], distinct_id=msg["distinct_id"], uuid=msg["uuid"],
                                      timestamp=when, properties=props)
            except Exception as e:  # noqa: BLE001
                log.debug("telemetry: %s", e)
                _failed.set()
            ok = not _failed.is_set()
        if not ok:
            return                          # offline or refused: try again on the next run
        with _lock:                         # sent (or too old): remove it
            st = _read_state()
            st["outbox"] = [m for m in st.get("outbox", []) if m.get("uuid") != msg.get("uuid")]
            _write_state(st)


def _kick() -> None:
    """Start sending the outbox in the background (one sender at a time)."""
    global _drainer
    with _lock:
        if _drainer is not None and _drainer.is_alive():
            return
        _drainer = threading.Thread(target=_drain, name="ontoreview-telemetry", daemon=True)
        _drainer.start()


def flush(timeout: float = 3.0) -> None:
    """Wait a little for the sender (at exit); never longer than ``timeout`` seconds."""
    t = _drainer
    if t is not None and t.is_alive():
        t.join(timeout)


atexit.register(flush)


def _sampled_in() -> bool:
    global _sample
    if _sample is None:
        _sample = not (is_ci() or is_docker()) or random.random() < CI_SAMPLE
    return _sample


def clean(props: dict[str, Any], details: bool) -> dict[str, Any]:
    """Only keys from :data:`SPEC`; optional keys only when details are on; empty values dropped."""
    out = {}
    for k, v in props.items():
        tier = TIERS.get(k)
        if tier is None or k in _SENT_BY_POSTHOG:
            if k not in _POSTHOG_KEYS:
                log.debug("telemetry: dropped unknown property %s", k)
            continue
        if tier == "optional" and not details:
            continue
        if v is None or v == [] or v == {}:
            continue
        out[k] = v
    return out


def track(event: str, props: dict[str, Any] | None = None, *, surface: str = "ontoreview") -> dict | None:
    """Send one event (in the background). Returns the payload that was queued, or ``None``."""
    if event not in EVENTS or not enabled():
        return None
    try:
        return _track(event, props or {}, surface)
    except Exception as e:  # noqa: BLE001 - telemetry must never break a run
        log.debug("telemetry failed: %s", e)
        return None


def _track(event: str, props: dict[str, Any], surface: str) -> dict | None:
    iid = install_id()
    with _lock:
        st = _read_state()
        if st.pop("first_seen_pending", False) and event != "install_first_seen" and not (is_ci() or is_docker()):
            _write_state(st)
            _track("install_first_seen", {}, surface)
            st = _read_state()
        today = date.today().isoformat()
        if st.get("day") != today:
            st.update(day=today, count=0, carry_capped=st.get("capped", 0), capped=0)
        if event != "install_first_seen" and not _sampled_in():
            return None
        if st.get("count", 0) >= DAILY_CAP:
            st["capped"] = st.get("capped", 0) + 1
            _write_state(st)
            return None
        st["count"] = st.get("count", 0) + 1
        capped = st.pop("carry_capped", 0)
        details = not details_env_locked() and bool(st.get("details", True))
        payload = clean({**_base_cache(), "mode": detect_mode(surface), "surface": surface,
                         "sample_rate": 1.0 if not (is_ci() or is_docker()) else CI_SAMPLE,
                         "capped_count": capped or None, **props}, details)
        st["last_events"] = ([{"event": event, "when": int(time.time()), "properties": payload}]
                             + list(st.get("last_events", [])))[:LAST_EVENTS]
        _write_state(st)
        # outbox first: kept if there is no connection now, sent on a later run. The uuid lets PostHog
        # de-duplicate an event that is sent twice; the timestamp keeps the time it happened.
        from datetime import datetime, timezone
        _outbox_add({"event": event, "distinct_id": iid, "uuid": str(uuid.uuid4()),
                     "timestamp": datetime.now(timezone.utc).isoformat(),
                     "properties": {**payload, "$process_person_profile": False}})
    _kick()
    return payload


# ------------------------------------------------------------------ what a run did
@dataclass
class _Acc:
    """Details noted during a run (or an app session): merged into one event."""
    checks: set[str] = field(default_factory=set)
    check_status: dict[str, str] = field(default_factory=dict)
    findings: Counter = field(default_factory=Counter)
    ontology: dict[str, Any] = field(default_factory=dict)
    ontologies: int = 0
    docs: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    ai_requests: int = 0
    features: Counter = field(default_factory=Counter)
    evaluation: dict[str, Any] = field(default_factory=dict)

    def props(self) -> dict[str, Any]:
        p: dict[str, Any] = {}
        if self.checks:
            p["checks_run"] = sorted(self.checks)
        if self.check_status:
            p["check_status"] = dict(sorted(self.check_status.items()))
        if self.findings or "rules" in self.checks:
            p["findings"] = {k: bucket(self.findings.get(k, 0), (1, 10, 100, 1000))
                             for k in ("error", "warning", "info")}
        p.update(self.evaluation)
        p.update({k: v for k, v in self.ontology.items() if not k.startswith("_")})
        if self.ontologies:
            p["ontologies"] = bucket(self.ontologies, (1, 2, 10, 50)) if self.ontologies > 1 else "1"
        p.update(self.docs)
        if self.ai_requests:
            p.update(self.ai)
            p["ai_requests"] = bucket(self.ai_requests, (1, 10, 50, 200))
        if self.features:
            p["features"] = dict(self.features)
        return p


@dataclass
class Run(_Acc):
    command: str = ""
    surface: str = "ontoreview"
    task: str | None = None
    flags: list[str] = field(default_factory=list)
    is_folder: bool | None = None
    started: float = field(default_factory=time.perf_counter)
    outcome: str = "ok"
    exit_code: int | None = None
    error_class: str | None = None


@dataclass
class Session(_Acc):
    started: float = field(default_factory=time.monotonic)
    tasks: int = 0
    pages: Counter = field(default_factory=Counter)
    tabs: set[str] = field(default_factory=set)


_local = threading.local()
_session: Session | None = None


def _current() -> _Acc | None:
    return getattr(_local, "run", None) or _session


@contextmanager
def run(command: str, *, surface: str = "ontoreview", task: str | None = None,
        flags: list[str] | None = None, is_folder: bool | None = None) -> Iterator[Run]:
    """Time a command or app task and send ``run_completed`` when it ends (however it ends)."""
    prev = getattr(_local, "run", None)
    if prev is not None:                 # nested (e.g. an app task inside a command): one event, the outer one
        yield prev
        return
    r = Run(command=command, surface=surface, task=task, flags=sorted(set(flags or [])), is_folder=is_folder)
    _local.run = r
    try:
        yield r
    except KeyboardInterrupt:
        r.outcome, r.exit_code = "cancelled", 130
        raise
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        r.exit_code = code
        r.outcome = "ok" if code == 0 else "nonzero_exit"
        raise
    except BaseException as e:
        r.outcome, r.error_class = "failed", type(e).__name__
        raise
    finally:
        _local.run = prev
        if _session is not None and surface == "ontoreview-ui":
            _session.tasks += 1
        track("run_completed", {
            "command": r.command, "task": r.task, "outcome": r.outcome, "exit_code": r.exit_code,
            "error_class": r.error_class, "duration_bucket": duration_bucket(time.perf_counter() - r.started),
            "flags_used": r.flags, "is_folder": r.is_folder, **r.props()}, surface=surface)


def start_session() -> None:
    """The app started: one ``ui_session`` event is sent when it stops."""
    global _session
    if _session is None:
        _session = Session()
        atexit.register(end_session)
        if enabled() and pending():
            _kick()                         # events collected while offline


def end_session() -> None:
    global _session
    s, _session = _session, None
    if s is None:
        return
    track("ui_session", {"session_duration_bucket": session_bucket(time.monotonic() - s.started),
                         "tasks_run_count": s.tasks, "pages_visited": dict(s.pages),
                         "settings_tabs": sorted(s.tabs), **s.props()}, surface="ontoreview-ui")
    flush()


def note_page(key: str) -> None:
    if _session is not None and key:
        _session.pages[key] += 1


def note_settings_tab(key: str) -> None:
    if _session is not None and key:
        _session.tabs.add(key)


def note_feature(name: str) -> None:
    acc = _current()
    if acc is not None:
        acc.features[name] += 1


_TOOL_KEYS = {"ROBOT": "robot", "Logical consistency": "reasoner", "OntoCheck": "ontocheck", "IRI checks": "iri",
              "OOPS!": "oops", "Cross-domain interoperability": "cdi", "Scientific interoperability": "si"}


def note_evaluations(config, reports) -> None:
    """Which checks were switched on, and what became of each (from ``run_evaluations``)."""
    acc = _current()
    if acc is None:
        return
    try:
        ev = config.evaluation
        on = {"robot": ev.robot != "off", "reasoner": ev.robot != "off" and ev.reasoner != "off",
              "iri": ev.iri_checks == "on", "ontocheck": ev.ontocheck == "on", "cdi": ev.cdi == "on",
              "si": ev.si == "on", "oops": ev.oops != "off"}
        wanted = {k for k, v in on.items() if v}
        acc.checks |= wanted
        got = {}
        for r in reports:
            k = _TOOL_KEYS.get(getattr(r, "tool", ""))
            if k:
                got[k] = "failed" if getattr(r, "error", None) else "ran"
        for k in wanted:
            acc.check_status[k] = got.get(k, acc.check_status.get(k, "skipped"))
        acc.evaluation = {"robot_mode": "off" if ev.robot == "off" else ("local" if ev.robot_path else "docker"),
                          "reasoner": ev.reasoner if ev.robot != "off" else "off"}
    except Exception as e:  # noqa: BLE001
        log.debug("telemetry: %s", e)


def note_report(report) -> None:
    """Built-in rules ran; add the report's finding counts (summed over a collection)."""
    acc = _current()
    if acc is None or report is None:
        return
    acc.checks.add("rules")
    try:
        for k, v in report.totals.items():
            acc.findings[k] += int(v)
    except Exception as e:  # noqa: BLE001
        log.debug("telemetry: %s", e)


_FORMATS = {".ttl": "ttl", ".owl": "owl", ".rdf": "rdfxml", ".xml": "rdfxml", ".jsonld": "jsonld",
            ".json": "jsonld", ".nt": "nt", ".n3": "n3", ".trig": "trig", ".nq": "nq", ".obo": "obo",
            ".yaml": "yaml", ".yml": "yaml", ".ofn": "ofn", ".omn": "omn", ".owx": "owx"}


def note_ontology(onto, loaded=None) -> None:
    """Format, kind and size buckets of the ontology just loaded (the largest one in a collection)."""
    acc = _current()
    if acc is None or onto is None:
        return
    try:
        terms = onto.terms.values() if isinstance(onto.terms, dict) else onto.terms
        kinds = Counter(getattr(t, "kind", "") for t in terms)
        props = sum(v for k, v in kinds.items() if k.endswith("property"))
        acc.ontologies += 1
        n_classes = kinds.get("class", 0)
        if acc.ontology and acc.ontology.get("_classes", 0) > n_classes:
            return
        src = str(getattr(loaded, "source", "") or "")
        suffix = Path(src.split("?", 1)[0]).suffix.lower() if src else ""
        acc.ontology = {
            "ontology_format": _FORMATS.get(suffix, "url" if src.startswith(("http://", "https://")) else "other"),
            "ontology_kind": getattr(loaded, "source_kind", None) or getattr(onto, "source_kind", None),
            "classes": bucket(n_classes), "properties": bucket(props),
            "individuals": bucket(kinds.get("individual", 0)), "concepts": bucket(kinds.get("concept", 0)),
            "has_imports": bool(getattr(loaded, "imports_loaded", None)), "_classes": n_classes}
    except Exception as e:  # noqa: BLE001
        log.debug("telemetry: %s", e)


def note_docs(cfg) -> None:
    """Documentation options of a build (choices only, no text)."""
    acc = _current()
    if acc is None:
        return
    try:
        acc.docs = {"docs_layout": cfg.layout, "docs_languages": len(cfg.languages or ["en"]),
                    "docs_graph_notation": cfg.ui.graph_notation,
                    "docs_custom_theme": bool(cfg.theme or cfg.custom_css),
                    "docs_sections_off": sorted(k for k, v in cfg.sections.model_dump().items() if not v)}
    except Exception as e:  # noqa: BLE001
        log.debug("telemetry: %s", e)


_FAMILIES = ("qwen", "gpt", "claude", "llama", "gemini", "gemma", "mistral", "mixtral", "phi", "deepseek",
             "command", "o1", "o3", "o4")


def model_family(model: str | None) -> str:
    m = (model or "").lower().rsplit("/", 1)[-1]
    return next((f for f in _FAMILIES if m.startswith(f)), "other")


def note_ai(provenance: dict) -> None:
    """One AI request (source, provider, model family; never the prompt or answer)."""
    acc = _current()
    if acc is None:
        return
    try:
        src = provenance.get("source") or "unknown"
        prov = str(provenance.get("provider") or src)
        provider = "ollama" if src == "ollama" else ("huggingface" if src == "hf" else prov.lower())
        known = ("openai", "anthropic", "openrouter", "gemini", "mistral", "groq", "custom", "ollama", "huggingface")
        acc.ai = {"ai_source": src, "ai_provider": provider if provider in known else "other",
                  "ai_model_family": model_family(provenance.get("model"))}
        acc.ai_requests += 1
    except Exception as e:  # noqa: BLE001
        log.debug("telemetry: %s", e)


# ------------------------------------------------------------------ CLI helpers
def cli_command(argv: list[str]) -> str | None:
    """``["build", "x.ttl", "-o", "d"]`` → "build"; ``["terms", "search", "q"]`` → "terms search".
    ``None`` for help, version and the bare command (not a real use)."""
    if any(a in ("--help", "-h", "--version", "-V") for a in argv):
        return None
    words = [a for a in argv if not a.startswith("-")]
    if not words:
        return None
    if words[0] in CLI_GROUPS:
        return f"{words[0]} {words[1]}" if len(words) > 1 else None
    return words[0]


def cli_flags(argv: list[str]) -> list[str]:
    """Option names only: ``--robot=off`` → ``--robot``; values never leave the machine."""
    return sorted({a.split("=", 1)[0] for a in argv if a.startswith("--") and len(a) > 2})


def status_lines() -> list[str]:
    reason = disabled_reason()
    st = _read_state()
    lines = [f"Telemetry: {'off (' + reason + ')' if reason else 'on'}",
             f"Optional details: {'on' if details_enabled() else 'off'}"
             + (" (ONTOREVIEW_TELEMETRY_DETAILS=0)" if details_env_locked() else ""),
             f"Install id: {st.get('install_id', '(not created yet)')}",
             f"Sent to: {HOST} (PostHog)", f"Settings file: {STATE_FILE}", f"Details: {DOCS}"]
    return lines
