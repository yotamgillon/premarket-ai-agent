"""Render a PreMarketReport to Markdown / HTML and write it to reports/YYYY-MM-DD/."""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from premarket_agent.collectors.prices import PriceSnapshot
from premarket_agent.report.models import PreMarketReport

_env = Environment(
    loader=PackageLoader("premarket_agent", "report/templates"),
    # HTML is escaped (headlines come from the internet); Markdown is not.
    autoescape=select_autoescape(enabled_extensions=("html.j2",), default_for_string=False),
    undefined=StrictUndefined,  # a typo in a template fails loudly instead of rendering ""
    trim_blocks=True,
    lstrip_blocks=True,
)


def num(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def signed(value: float) -> str:
    return f"{value:+,.2f}"


_env.globals.update(num=num, signed=signed)


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
