"""The report schema. Claude's final answer is constrained to this shape by the API."""

from typing import Literal

from pydantic import BaseModel, Field

Bias = Literal["bullish", "neutral_up", "neutral_down", "bearish"]
Sentiment = Literal["risk-on", "risk-off", "mixed"]

BIAS_LABELS: dict[str, str] = {
    "bullish": "BULLISH",
    "neutral_up": "NEUTRAL ↑",
    "neutral_down": "NEUTRAL ↓",
    "bearish": "BEARISH",
}
# Direction drives color: up = green, down = magenta/red, flat = cyan.
BIAS_DIRECTION: dict[str, str] = {
    "bullish": "up",
    "neutral_up": "up",
    "neutral_down": "down",
    "bearish": "down",
}
SENTIMENT_DIRECTION: dict[str, str] = {"risk-on": "up", "risk-off": "down", "mixed": "flat"}


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
    sentiment: Sentiment
    sentiment_rationale: str
    bias: Bias = Field(
        description=(
            "bullish / bearish for a clear directional view. When the picture is mixed, "
            "still pick the side you lean toward: neutral_up or neutral_down."
        )
    )
    bias_rationale: str = Field(
        description="Why. For neutral_up / neutral_down, one sentence on why it leans that way."
    )
    risks: list[str] = Field(description="What would invalidate the bias.")
    data_gaps: list[str] = Field(
        description=(
            "Real failures only: a source that errored or returned missing fields. "
            "Data from the last completed session is expected and is NOT a gap. Empty if none."
        )
    )

    @property
    def bias_label(self) -> str:
        return BIAS_LABELS[self.bias]
