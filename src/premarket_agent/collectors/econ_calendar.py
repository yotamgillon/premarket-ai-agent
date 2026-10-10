"""Economic calendar from the ForexFactory weekly JSON feed (free, no API key)."""

from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from premarket_agent.collectors import NY_TZ, CollectorError

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_RANK = {"Holiday": 0, "Low": 1, "Medium": 2, "High": 3}


class EconomicEvent(BaseModel):
    title: str
    country: str
    time: datetime
    impact: str
    forecast: str | None
    previous: str | None


def parse_calendar(raw: list[dict[str, Any]]) -> list[EconomicEvent]:
    return [
        EconomicEvent(
            title=row["title"],
            country=row["country"],
            time=datetime.fromisoformat(row["date"]),
            impact=row.get("impact", "Low"),
            forecast=row.get("forecast") or None,
            previous=row.get("previous") or None,
        )
        for row in raw
    ]


def events_for_day(
    events: list[EconomicEvent],
    day: date,
    countries: frozenset[str] = frozenset({"USD"}),
    min_impact: str = "Medium",
) -> list[EconomicEvent]:
    """Events on `day` (New York date) for the given countries at or above `min_impact`."""
    threshold = IMPACT_RANK[min_impact]
    selected = [
        e
        for e in events
        if e.time.astimezone(NY_TZ).date() == day
        and e.country in countries
        and IMPACT_RANK.get(e.impact, 0) >= threshold
    ]
    return sorted(selected, key=lambda e: e.time)


def fetch_calendar(client: httpx.Client, day: date) -> list[EconomicEvent]:
    try:
        resp = client.get(CALENDAR_URL)
        resp.raise_for_status()
        events = parse_calendar(resp.json())
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise CollectorError(f"economic calendar unavailable: {exc}") from exc
    return events_for_day(events, day)
