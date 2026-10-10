import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest

from premarket_agent.agent import tools as tools_mod
from premarket_agent.agent.tools import TOOL_DEFINITIONS, Toolkit
from premarket_agent.collectors import NY_TZ, CollectorError

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=NY_TZ)
DAY = date(2026, 10, 12)


def _client(fixtures_dir: Path) -> tuple[httpx.Client, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if "faireconomy" in request.url.host:
            return httpx.Response(200, content=(fixtures_dir / "calendar.json").read_bytes())
        return httpx.Response(200, content=(fixtures_dir / "feed_a.xml").read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_every_tool_definition_has_a_handler(fixtures_dir: Path) -> None:
    client, _ = _client(fixtures_dir)
    kit = Toolkit(client, DAY, NOW)
    for tool in TOOL_DEFINITIONS:
        assert tool["name"] in kit._handlers
        assert tool["input_schema"]["additionalProperties"] is False


def test_news_fetched_once_and_filtered_in_memory(fixtures_dir: Path) -> None:
    client, requested = _client(fixtures_dir)
    kit = Toolkit(client, DAY, NOW)
    all_items, _ = kit.execute("get_news", {"query": ""})
    oil, err = kit.execute("get_news", {"query": "OIL"})
    assert not err
    n_feeds = len(requested)
    kit.execute("get_news", {"query": "cpi"})
    assert len(requested) == n_feeds  # no re-fetch on later calls
    assert [i["title"] for i in json.loads(oil)["items"]] == ["Oil slips as OPEC+ weighs output"]
    assert "link" not in json.loads(all_items)["items"][0]  # trimmed to save tokens


def test_calendar_tool(fixtures_dir: Path) -> None:
    client, _ = _client(fixtures_dir)
    out, err = Toolkit(client, DAY, NOW).execute("get_economic_calendar", {})
    assert not err
    assert [e["title"] for e in json.loads(out)["events"]][:2] == ["CPI m/m", "Core CPI m/m"]


def test_unknown_tool_and_collector_error(
    fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _client(fixtures_dir)
    kit = Toolkit(client, DAY, NOW)
    assert kit.execute("nope", {}) == ("Unknown tool: nope", True)

    def boom(*_a: object, **_k: object) -> None:
        raise CollectorError("calendar down")

    monkeypatch.setattr(tools_mod, "fetch_calendar", boom)
    out, err = kit.execute("get_economic_calendar", {})
    assert err
    assert "calendar down" in out
