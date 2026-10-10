"""Tools exposed to Claude. Each one wraps a deterministic collector."""

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from premarket_agent.collectors import NY_TZ, CollectorError, prices
from premarket_agent.collectors.econ_calendar import fetch_calendar
from premarket_agent.collectors.news import NewsResult, fetch_news

# `strict: True` makes the API guarantee tool inputs match the schema exactly.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_market_snapshot",
        "description": (
            "Latest price, change vs prior close, prior-session high/low, overnight "
            "high/low and 5-day range for NQ and ES futures and the VIX."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(prices.INSTRUMENTS)},
                    "description": "Symbols to fetch. Use all three unless you need fewer.",
                }
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_news",
        "description": (
            "Market headlines from the last 36 hours (CNBC, MarketWatch, Yahoo Finance), "
            "newest first. Pass a keyword to narrow down, or an empty string for all."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Case-insensitive keyword, or ''."}
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_economic_calendar",
        "description": "Today's scheduled USD economic events of medium or high impact (ET).",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


class Toolkit:
    """Executes tool calls for one run. News is fetched once and filtered in memory."""

    def __init__(self, client: httpx.Client, report_date: date, now: datetime | None = None):
        self._client = client
        self._date = report_date
        self._now = now or datetime.now(NY_TZ)
        self._news: NewsResult | None = None
        self._handlers: dict[str, Callable[..., Any]] = {
            "get_market_snapshot": self.get_market_snapshot,
            "get_news": self.get_news,
            "get_economic_calendar": self.get_economic_calendar,
        }

    def execute(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Run a tool and return (json_result, is_error). Never raises."""
        handler = self._handlers.get(name)
        if handler is None:
            return f"Unknown tool: {name}", True
        try:
            return json.dumps(handler(**tool_input), default=str), False
        except (CollectorError, httpx.HTTPError, TypeError) as exc:
            return f"Error: {exc}", True

    def get_market_snapshot(self, symbols: list[str]) -> dict[str, Any]:
        results = prices.fetch_all(symbols, now=self._now)
        return {s: (v if isinstance(v, str) else v.model_dump()) for s, v in results.items()}

    def get_news(self, query: str) -> dict[str, Any]:
        if self._news is None:
            self._news = fetch_news(self._client, since=self._now - timedelta(hours=36))
        q = query.strip().lower()
        items = [
            i.model_dump(exclude={"link"})
            for i in self._news.items
            if not q or q in f"{i.title} {i.summary}".lower()
        ]
        return {"items": items, "failed_sources": self._news.failed_sources}

    def get_economic_calendar(self) -> dict[str, Any]:
        events = fetch_calendar(self._client, self._date)
        return {"date": self._date.isoformat(), "events": [e.model_dump() for e in events]}
