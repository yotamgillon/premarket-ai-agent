from datetime import UTC, datetime
from pathlib import Path

import httpx

from premarket_agent.collectors.news import fetch_news, parse_feed

FEEDS = {
    "A": "https://feeds.test/a",
    "B": "https://feeds.test/b",
    "Down": "https://feeds.test/down",
}
SINCE = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def _client(fixtures_dir: Path) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(200, content=(fixtures_dir / "feed_a.xml").read_bytes())
        if request.url.path == "/b":
            return httpx.Response(200, content=(fixtures_dir / "feed_b.xml").read_bytes())
        return httpx.Response(503)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_feed_cleans_html(fixtures_dir: Path) -> None:
    items = parse_feed((fixtures_dir / "feed_a.xml").read_bytes(), "A")
    assert len(items) == 3
    assert items[0].summary == "Nasdaq futures gained 0.4% & S&P futures rose."
    assert items[0].published == datetime(2026, 10, 12, 11, 30, tzinfo=UTC)


def test_fetch_news_filters_dedupes_and_sorts(fixtures_dir: Path) -> None:
    result = fetch_news(_client(fixtures_dir), since=SINCE, feeds=FEEDS)
    titles = [i.title for i in result.items]
    assert titles == [
        "Stocks futures rise ahead of CPI report",  # dupe from B dropped
        "Fed's Waller says inflation progress is uneven",
        "Oil slips as OPEC+ weighs output",
    ]
    assert "Old story from last week" not in titles
    assert result.failed_sources == ["Down"]


def test_fetch_news_query_and_limit(fixtures_dir: Path) -> None:
    result = fetch_news(_client(fixtures_dir), since=SINCE, feeds=FEEDS, query="cpi", limit=1)
    assert [i.title for i in result.items] == ["Stocks futures rise ahead of CPI report"]
