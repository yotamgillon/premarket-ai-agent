import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from premarket_agent.collectors import CollectorError
from premarket_agent.collectors.econ_calendar import events_for_day, fetch_calendar, parse_calendar

DAY = date(2026, 10, 12)


def test_events_for_day_filters_country_impact_and_date(fixtures_dir: Path) -> None:
    events = parse_calendar(json.loads((fixtures_dir / "calendar.json").read_text()))
    selected = events_for_day(events, DAY)
    assert [e.title for e in selected] == [
        "CPI m/m",
        "Core CPI m/m",
        "FOMC Member Speaks",
        "Late-night USD event",
    ]
    assert selected[0].forecast == "0.3%"
    assert selected[2].forecast is None  # empty string normalised to None


def test_fetch_calendar_http_error_raises() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429)))
    with pytest.raises(CollectorError):
        fetch_calendar(client, DAY)


def test_fetch_calendar_ok(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "calendar.json").read_bytes()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    client = httpx.Client(transport=transport)
    assert len(fetch_calendar(client, DAY)) == 4
