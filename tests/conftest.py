from pathlib import Path

import pytest

from ontoreview import evaluate
from ontoreview.config import Config
from ontoreview.loader import load_ontology
from ontoreview.model.extract import extract

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
    Tests marked ``real_evaluators`` exercise the real dispatch with their own stubs."""
    if "real_evaluators" in request.keywords:
        return
    monkeypatch.setattr(evaluate, "run_robot", lambda *a, **k: None)
    monkeypatch.setattr(evaluate, "run_oops", lambda *a, **k: evaluate.ExternalReport("OOPS!", "https://oops.linkeddata.es"))


@pytest.fixture
def anyio_backend():
    return "asyncio"
