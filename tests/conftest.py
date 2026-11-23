import os
from pathlib import Path

import pytest

os.environ["ONTOREVIEW_TELEMETRY"] = "off"      # tests never send usage statistics (tests/test_telemetry.py fakes it)

from ontoreview.config import Config
from ontoreview.loader import load_ontology
from ontoreview.model.extract import extract
from ontoreview.quality_checks import cdi, iri, logical_consistency, ontocheck, oops, robot
from ontoreview.report.models import ExternalReport

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def pizza():
    loaded = load_ontology(FIXTURES / "pizza.ttl")
    return loaded, extract(loaded, Config())


@pytest.fixture
def personinfo():
    loaded = load_ontology(FIXTURES / "linkml" / "personinfo.yaml")
    return loaded, extract(loaded, Config())


@pytest.fixture(autouse=True)
def _private_iri_db(tmp_path, monkeypatch):
    """Never touch the user's IRI term cache from tests."""
    monkeypatch.setenv("ONTOREVIEW_IRI_DB", str(tmp_path / "iri-cache.sqlite3"))
    from ontoreview import telemetry
    monkeypatch.setattr(telemetry, "STATE_FILE", tmp_path / "telemetry.json")
    # fixtures include third-party ontologies without a license or creators; tests of the
    # required-metadata rule turn it on explicitly (require_metadata=True)
    monkeypatch.setenv("ONTOREVIEW_REQUIRE_METADATA", "0")


@pytest.fixture(autouse=True)
def _no_external_evaluators(request, monkeypatch):
    """Builds run ROBOT (Docker) and the OOPS! web service by default; tests must stay offline.
    Tests marked ``real_evaluators`` exercise the real dispatch with their own stubs; OntoCheck
    (in-process, a few seconds) only runs in tests marked ``real_ontocheck``."""
    if "real_ontocheck" not in request.keywords:
        monkeypatch.setattr(ontocheck, "check_ontocheck", lambda *a, **k: None)
    if "real_iri" not in request.keywords:
        monkeypatch.setattr(iri, "check_iris", lambda *a, **k: None)
    if "real_cdi" not in request.keywords:      # on by default: OLS queries and a language model
        monkeypatch.setattr(cdi, "check_cdi", lambda *a, **k: [])
    import ontoreview.fixes.orcid as orcid      # the creator form looks names up in ORCID
    monkeypatch.setattr(orcid, "search_orcid", lambda *a, **k: [])
    if "real_evaluators" in request.keywords:
        return
    monkeypatch.setattr(robot, "run_robot", lambda *a, **k: None)
    monkeypatch.setattr(logical_consistency, "run_reasoner", lambda *a, **k: None)
    monkeypatch.setattr(oops, "run_oops", lambda *a, **k: ExternalReport("OOPS!", "https://oops.linkeddata.es"))


@pytest.fixture
def anyio_backend():
    return "asyncio"
