from datetime import date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from premarket_agent.collectors import NY_TZ
from premarket_agent.collectors.prices import PriceSnapshot
from premarket_agent.report.models import PreMarketReport
from premarket_agent.report.render import (
    RenderedReport,
    build_ladders,
    range_position,
    session_note,
    write_report,
)

NOW = datetime(2026, 10, 12, 8, 5, tzinfo=NY_TZ)

NQ = PriceSnapshot(
    symbol="NQ=F",
    name="Nasdaq-100 E-mini futures",
    as_of=NOW,
    last_bar_time=datetime(2026, 10, 9, 16, 45, tzinfo=NY_TZ),
    last=31234.5,
    prev_close=31108.75,
    change=125.75,
    change_pct=0.4,
    prior_high=31266.5,
    prior_low=30953.0,
    range_position_pct=89.8,
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


def test_html_terminal_design(rendered: RenderedReport) -> None:
    html = rendered.html()
    assert '<div class="badge up">' in html  # bullish badge glows green
    assert "BULLISH" in html
    assert "prefers-color-scheme: light" in html  # dark-first, light still supported
    assert "JetBrains Mono" in html
    assert "<script" not in html  # no JS at all
    assert "Prices as of Fri Oct 09, 16:45 ET" in html
    # Last 31234.5 between prior low 30953 and high 31266.5 -> 89.8%
    assert 'class="marker" style="left: 89.8%"' in html
    assert 'class="tick now"' in html


@pytest.mark.parametrize(
    ("bias", "label", "css"),
    [
        ("bullish", "BULLISH", "up"),
        ("neutral_up", "NEUTRAL ↑", "up"),
        ("neutral_down", "NEUTRAL ↓", "down"),
        ("bearish", "BEARISH", "down"),
    ],
)
def test_bias_labels(rendered: RenderedReport, bias: str, label: str, css: str) -> None:
    rendered.report = rendered.report.model_copy(update={"bias": bias})
    assert f"**Bias:** {label}" in rendered.markdown()
    html = rendered.html()
    assert f'<div class="badge {css}">' in html
    assert f'<span class="v">{label}</span>' in html


def test_plain_neutral_bias_is_rejected(sample_report: PreMarketReport) -> None:
    data = sample_report.model_dump() | {"bias": "neutral"}
    with pytest.raises(ValidationError):
        PreMarketReport.model_validate(data)


def test_session_note_shown_once_in_markdown(rendered: RenderedReport) -> None:
    md = rendered.markdown()
    assert md.count("Prices as of Fri Oct 09, 16:45 ET") == 1
    assert session_note([]) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(5, 50.0), (0, 0.0), (10, 100.0), (-3, 0.0), (42, 100.0)],
)
def test_range_position_clamps(value: float, expected: float) -> None:
    assert range_position(value, 0, 10) == expected
    assert range_position(7, 5, 5) == 50.0  # degenerate range


def test_ladders_sorted_with_current_marked(sample_report: PreMarketReport) -> None:
    ladders = build_ladders(sample_report, [NQ])
    nq = next(lad for lad in ladders if lad.instrument == "NQ")
    assert [r.price for r in nq.rungs] == [31234.5, 31266.5]  # sorted low -> high
    assert nq.rungs[0].is_current
    assert nq.rungs[1].side == "up"  # above last = resistance
    es = next(lad for lad in ladders if lad.instrument == "ES")
    assert es.current is None  # no ES snapshot: ladder still renders, no current marker
    assert not any(r.is_current for r in es.rungs)


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


def test_ladder_merges_level_equal_to_last(sample_report: PreMarketReport) -> None:
    levels = [
        {"instrument": "NQ", "level": 31234.5, "label": "Prior close"},
        {"instrument": "NQ", "level": 31266.5, "label": "Prior day high"},
    ]
    report = PreMarketReport.model_validate(sample_report.model_dump() | {"key_levels": levels})
    nq = build_ladders(report, [NQ])[0]
    assert [(r.price, r.label) for r in nq.rungs] == [
        (31234.5, "Last · Prior close"),
        (31266.5, "Prior day high"),
    ]


def test_rationale_text_not_tinted(rendered: RenderedReport) -> None:
    html = rendered.html()
    assert 'class="panel call call-up reveal"' in html
    assert 'class="panel call up' not in html
