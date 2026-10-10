"""Market headlines from public RSS feeds."""

import calendar
import html
import re
from datetime import UTC, datetime

import feedparser
import httpx
from pydantic import BaseModel

FEEDS: dict[str, str] = {
    "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Investing": "https://www.cnbc.com/id/15839069/device/rss/rss.html",
    "MarketWatch Bulletins": "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
    "Yahoo Finance": (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=ES=F,NQ=F,%5EGSPC&region=US&lang=en-US"
    ),
}

_TAG_RE = re.compile(r"<[^>]+>")
SUMMARY_MAX_CHARS = 300


class NewsItem(BaseModel):
    title: str
    source: str
    link: str
    published: datetime | None
    summary: str


class NewsResult(BaseModel):
    items: list[NewsItem]
    failed_sources: list[str]


def _clean(text: str) -> str:
    text = html.unescape(_TAG_RE.sub("", text or ""))
    return " ".join(text.split())[:SUMMARY_MAX_CHARS]


def parse_feed(content: bytes, source: str) -> list[NewsItem]:
    parsed = feedparser.parse(content)
    items = []
    for entry in parsed.entries:
        title = _clean(entry.get("title", ""))
        if not title:
            continue
        ts = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(ts), tz=UTC) if ts else None
        items.append(
            NewsItem(
                title=title,
                source=source,
                link=entry.get("link", ""),
                published=published,
                summary=_clean(entry.get("summary", "")),
            )
        )
    return items


def fetch_news(
    client: httpx.Client,
    since: datetime,
    feeds: dict[str, str] | None = None,
    query: str | None = None,
    limit: int = 25,
) -> NewsResult:
    """Fetch all feeds, keep items newer than `since`, dedupe by title, newest first.

    feedparser can fetch URLs itself, but it has no timeout — so we fetch with httpx
    and only use feedparser for parsing.
    """
    items: list[NewsItem] = []
    failed: list[str] = []
    for source, url in (feeds or FEEDS).items():
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError:
            failed.append(source)
            continue
        items.extend(parse_feed(resp.content, source))

    seen: set[str] = set()
    fresh: list[NewsItem] = []
    for item in items:
        key = item.title.lower()
        if key in seen or (item.published is not None and item.published < since):
            continue
        if query and query.lower() not in f"{item.title} {item.summary}".lower():
            continue
        seen.add(key)
        fresh.append(item)

    fresh.sort(key=lambda i: i.published or datetime.min.replace(tzinfo=UTC), reverse=True)
    return NewsResult(items=fresh[:limit], failed_sources=failed)
