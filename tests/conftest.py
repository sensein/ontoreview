from pathlib import Path

import pytest

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
