"""CLI entrypoint: `python -m premarket_agent` or `premarket-agent`."""

import argparse
import logging
import time
from datetime import date, datetime

import anthropic

from premarket_agent.agent.runner import AgentError, run_agent
from premarket_agent.agent.tools import Toolkit
from premarket_agent.collectors import NY_TZ, make_http_client
from premarket_agent.config import Settings, get_settings
from premarket_agent.notify import send_notifications
from premarket_agent.observability.cost import cost_usd
from premarket_agent.observability.logging import setup_logging
from premarket_agent.observability.metrics import push_metrics
from premarket_agent.observability.run_record import RunRecord, append_run_log
from premarket_agent.report.render import RenderedReport, write_report
from premarket_agent.trading_calendar import is_trading_day

log = logging.getLogger("premarket_agent")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a pre-market research report.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Report date (YYYY-MM-DD). Defaults to today in New York.",
    )
    parser.add_argument(
        "--force", action="store_true", help="Run even if the date is not a trading day."
    )
    return parser.parse_args(argv)


def generate(settings: Settings, record: RunRecord, report_date: date, now_et: datetime) -> None:
    """Do the work, filling in `record` as we go. Raises on failure."""
    assert settings.anthropic_api_key is not None
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    record.model = settings.claude_model

    with make_http_client() as http:
        toolkit = Toolkit(http, report_date, now_et)
        try:
            result = run_agent(
                client,
                toolkit,
                model=settings.claude_model,
                report_date=report_date,
                now_et=now_et,
                effort=settings.claude_effort,
            )
        except AgentError as exc:
            if exc.usage:  # a failed run still costs money: record what was spent
                record.tokens = exc.usage.as_dict()
                record.cost_usd = cost_usd(settings.claude_model, exc.usage)
            raise

        record.model = result.model
        record.iterations = result.iterations
        record.tool_calls = result.tool_calls
        record.tokens = result.usage.as_dict()
        record.cost_usd = cost_usd(result.model, result.usage)

        rendered = RenderedReport(
            report=result.report,
            report_date=report_date,
            generated_at=datetime.now(NY_TZ),
            model=result.model,
            snapshots=list(toolkit.snapshots.values()),
        )
        out_dir = write_report(rendered, settings.reports_dir)
        record.report_path = str(out_dir)
        record.notifications = send_notifications(settings, rendered, out_dir, http)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)

    now_et = datetime.now(NY_TZ)
    report_date = args.date or now_et.date()
    record = RunRecord(report_date=report_date.isoformat(), started_at=now_et)

    if not args.force and not is_trading_day(report_date):
        log.info("not a trading day, skipping", extra={"report_date": record.report_date})
        return 0
    if settings.anthropic_api_key is None:
        log.error("ANTHROPIC_API_KEY is not set, see .env.example")
        return 2

    start = time.perf_counter()
    try:
        generate(settings, record, report_date, now_et)
        record.status = "success"
    except (AgentError, anthropic.APIError) as exc:
        record.error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # unexpected bug: still record the failed run, then report it
        record.error = f"{type(exc).__name__}: {exc}"
        log.exception("unexpected error")
    finally:
        record.duration_s = round(time.perf_counter() - start, 2)

    level = logging.INFO if record.success else logging.ERROR
    log.log(level, "run finished", extra={"run": record.__dict__})
    append_run_log(record, settings.reports_dir / "runs.jsonl")
    if settings.pushgateway_url:
        push_metrics(settings.pushgateway_url, record)
    return 0 if record.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
