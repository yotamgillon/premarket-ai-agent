from pathlib import Path

import pytest

from premarket_agent.report.models import PreMarketReport

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def sample_report() -> PreMarketReport:
    return PreMarketReport.model_validate_json((FIXTURES / "report.json").read_text())
