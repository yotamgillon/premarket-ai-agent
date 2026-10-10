"""The report schema. Claude's final answer is constrained to this shape by the API."""

from typing import Literal

from pydantic import BaseModel, Field


class KeyLevel(BaseModel):
    instrument: Literal["NQ", "ES"]
    level: float
    label: str = Field(description="What the level is, e.g. 'Prior day high' or 'Overnight low'.")


class ScheduledEvent(BaseModel):
    time_et: str = Field(description="Release time in New York time, HH:MM.")
    event: str
    impact: Literal["High", "Medium"]
    note: str = Field(description="Forecast vs previous and why it matters today.")


class Headline(BaseModel):
    title: str
    source: str
    why_it_matters: str


class PreMarketReport(BaseModel):
    tldr: str = Field(description="One sentence a trader can read in 5 seconds.")
    overnight_summary: str = Field(description="2-4 sentences on what happened since the close.")
    key_levels: list[KeyLevel]
    scheduled_events: list[ScheduledEvent]
    top_news: list[Headline] = Field(description="At most 5, market-moving only.")
    sentiment: Literal["risk-on", "risk-off", "mixed"]
    sentiment_rationale: str
    bias: Literal["bullish", "bearish", "neutral"]
    bias_rationale: str
    risks: list[str] = Field(description="What would invalidate the bias.")
    data_gaps: list[str] = Field(description="Sources that were unavailable. Empty if none.")
