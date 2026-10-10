"""Deterministic data collectors. No LLM here — just fetching and shaping data."""

from zoneinfo import ZoneInfo

import httpx

# Futures and the economic calendar are quoted in New York time, so all
# market-time logic is done in ET regardless of where the agent runs.
NY_TZ = ZoneInfo("America/New_York")

USER_AGENT = "Mozilla/5.0 (compatible; premarket-agent/0.1; +https://github.com/yotamgillon)"


class CollectorError(RuntimeError):
    """A data source failed or returned unusable data."""


def make_http_client(timeout: float = 10.0) -> httpx.Client:
    # Explicit timeout + connection retries: a hung feed must never hang the daily run.
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        transport=httpx.HTTPTransport(retries=2),
    )
