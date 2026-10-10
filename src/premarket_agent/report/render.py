"""Render a PreMarketReport to Markdown / HTML and write it to reports/YYYY-MM-DD/."""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from premarket_agent.collectors import NY_TZ
from premarket_agent.collectors.prices import PriceSnapshot
from premarket_agent.report.models import BIAS_DIRECTION, SENTIMENT_DIRECTION, PreMarketReport

_env = Environment(
    loader=PackageLoader("premarket_agent", "report/templates"),
    # HTML is escaped (headlines come from the internet); Markdown is not.
    autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),
    undefined=StrictUndefined,  # a typo in a template fails loudly instead of rendering ""
    trim_blocks=True,
    lstrip_blocks=True,
)

# Report key levels use "NQ"/"ES"; snapshots use the Yahoo symbols.
INSTRUMENT_SYMBOLS = {"NQ": "NQ=F", "ES": "ES=F"}


def num(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def signed(value: float) -> str:
    return f"{value:+,.2f}"


def direction(value: float) -> str:
    return "up" if value > 0 else "down" if value < 0 else "flat"


def range_position(value: float, low: float, high: float) -> float:
    """Where `value` sits between low and high, as 0-100 (clamped). 50 if the range is empty."""
    if high <= low:
        return 50.0
    return round(min(max((value - low) / (high - low) * 100, 0.0), 100.0), 1)


@dataclass
class LadderRung:
    price: float
    label: str
    position: float  # 0-100 along the ladder
    is_current: bool = False
    side: str = "flat"  # "up" = above current price (resistance), "down" = below (support)


@dataclass
class Ladder:
    instrument: str
    current: float | None
    rungs: list[LadderRung]


def build_ladders(report: PreMarketReport, snapshots: list[PriceSnapshot]) -> list[Ladder]:
    """One ladder per instrument: key levels + current price, sorted low to high."""
    last_by_symbol = {s.symbol: s.last for s in snapshots}
    ladders = []
    for instrument in ("NQ", "ES"):
        levels = [k for k in report.key_levels if k.instrument == instrument]
        if not levels:
            continue
        current = last_by_symbol.get(INSTRUMENT_SYMBOLS[instrument])
        # A level at exactly the current price (e.g. prior close on a weekend) merges into
        # the "Last" rung instead of showing two identical chips.
        same_as_last = [k.label for k in levels if current is not None and k.level == current]
        points = [(k.level, k.label, False) for k in levels if k.label not in same_as_last]
        if current is not None:
            points.append((current, " · ".join(["Last", *same_as_last]), True))
        points.sort(key=lambda p: (p[0], p[2]))
        low, high = points[0][0], points[-1][0]
        rungs = [
            LadderRung(
                price=price,
                label=label,
                position=range_position(price, low, high),
                is_current=is_current,
                side=("flat" if is_current or current is None else direction(price - current)),
            )
            for price, label, is_current in points
        ]
        ladders.append(Ladder(instrument=instrument, current=current, rungs=rungs))
    return ladders


def session_note(snapshots: list[PriceSnapshot]) -> str | None:
    """Which session the prices reflect, e.g. 'Fri Oct 09, 16:45 ET'. Shown once."""
    if not snapshots:
        return None
    latest = max(s.last_bar_time for s in snapshots).astimezone(NY_TZ)
    return f"{latest:%a %b %d, %H:%M} ET"


_env.globals.update(
    num=num,
    signed=signed,
    direction=direction,
    range_position=range_position,
    bias_direction=BIAS_DIRECTION,
    sentiment_direction=SENTIMENT_DIRECTION,
)


@dataclass
class RenderedReport:
    report: PreMarketReport
    report_date: date
    generated_at: datetime
    model: str
    snapshots: list[PriceSnapshot] = field(default_factory=list)

    def _context(self) -> dict[str, object]:
        return {
            "r": self.report,
            "report_date": self.report_date,
            "generated_at": self.generated_at,
            "model": self.model,
            "snapshots": self.snapshots,
            "ladders": build_ladders(self.report, self.snapshots),
            "session_note": session_note(self.snapshots),
        }

    def markdown(self) -> str:
        return _env.get_template("report.md.j2").render(self._context())

    def html(self) -> str:
        return _env.get_template("report.html.j2").render(self._context())


def write_report(rendered: RenderedReport, reports_dir: Path) -> Path:
    """Write report.md, report.html and report.json; return the output directory."""
    out_dir = reports_dir / rendered.report_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(rendered.markdown(), encoding="utf-8")
    (out_dir / "report.html").write_text(rendered.html(), encoding="utf-8")
    # Raw structured output: lets you diff days or re-render with a new template later.
    (out_dir / "report.json").write_text(rendered.report.model_dump_json(indent=2), "utf-8")
    return out_dir
