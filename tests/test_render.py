from datetime import date, datetime
from pathlib import Path

import pytest

from premarket_agent.collectors import NY_TZ
from premarket_agent.collectors.prices import PriceSnapshot
from premarket_agent.report.models import PreMarketReport
from premarket_agent.report.render import RenderedReport, write_report

NOW = datetime(2026, 10, 12, 8, 5, tzinfo=NY_TZ)

NQ = PriceSnapshot(
    symbol="NQ=F",
    name="Nasdaq-100 E-mini futures",
    as_of=NOW,
    last=31234.5,
    prev_close=31108.75,
    change=125.75,
    change_pct=0.4,
    prior_high=31266.5,
    prior_low=30953.0,
    overnight_high=None,
    overnight_low=None,
    week_high=31616.5,
    week_low=30792.0,
)


@pytest.fixture
def rendered(sample_report: PreMarketReport) -> RenderedReport:
    return RenderedReport(
        report=sample_report,
        report_date=date(2026, 10, 12),
        generated_at=NOW,
        model="claude-opus-5-5",
        snapshots=[NQ],
    )


def test_markdown_contains_all_sections(rendered: RenderedReport) -> None:
    md = rendered.markdown()
    assert md.startswith("# Pre-Market Report — Monday, October 12, 2026")
    for heading in ("Market snapshot", "Key levels", "Scheduled events", "Top news", "Risks"):
        assert f"## {heading}" in md
    assert "| 31,234.50 | +125.75 (+0.40%) |" in md
    assert "— / —" in md  # missing overnight range renders as dashes, not "None"
    assert "Data gaps" not in md  # section hidden when empty
    assert "not investment advice" in md


def test_html_escapes_untrusted_headlines(rendered: RenderedReport) -> None:
    html = rendered.html()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert 'class="chip bullish"' in html
    assert "prefers-color-scheme: dark" in html


def test_empty_events_and_gaps(rendered: RenderedReport) -> None:
    rendered.report = rendered.report.model_copy(
        update={"scheduled_events": [], "data_gaps": ["VIX unavailable"]}
    )
    md = rendered.markdown()
    assert "No medium/high-impact US events" in md
    assert "## Data gaps" in md
    assert "VIX unavailable" in md


def test_write_report_creates_dated_folder(rendered: RenderedReport, tmp_path: Path) -> None:
    out = write_report(rendered, tmp_path)
    assert out == tmp_path / "2026-10-12"
    assert sorted(p.name for p in out.iterdir()) == ["report.html", "report.json", "report.md"]
    assert PreMarketReport.model_validate_json((out / "report.json").read_text()) == rendered.report
