from pathlib import Path

import pytest

from ontoreview.config import Config
from ontoreview.loader import load_ontology
from ontoreview.model.extract import extract
from ontoreview.quality_checks import logical_consistency, ontocheck, oops, robot
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
def _no_external_evaluators(request, monkeypatch):
    """Builds run ROBOT (Docker) and the OOPS! web service by default; tests must stay offline.
    Tests marked ``real_evaluators`` exercise the real dispatch with their own stubs; OntoCheck
    (in-process, a few seconds) only runs in tests marked ``real_ontocheck``."""
    if "real_ontocheck" not in request.keywords:
        monkeypatch.setattr(ontocheck, "check_ontocheck", lambda *a, **k: None)
    if "real_evaluators" in request.keywords:
        return
    monkeypatch.setattr(robot, "run_robot", lambda *a, **k: None)
    monkeypatch.setattr(logical_consistency, "run_reasoner", lambda *a, **k: None)
    monkeypatch.setattr(oops, "run_oops", lambda *a, **k: ExternalReport("OOPS!", "https://oops.linkeddata.es"))


@pytest.fixture
def anyio_backend():
    return "asyncio"
