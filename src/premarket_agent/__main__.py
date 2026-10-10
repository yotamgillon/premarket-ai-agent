"""CLI entrypoint: `python -m premarket_agent` or `premarket-agent`."""

import argparse
import sys
from datetime import date, datetime

import anthropic

from premarket_agent.agent.runner import AgentError, run_agent
from premarket_agent.agent.tools import Toolkit
from premarket_agent.collectors import NY_TZ, make_http_client
from premarket_agent.config import get_settings
from premarket_agent.trading_calendar import is_trading_day


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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    now_et = datetime.now(NY_TZ)
    report_date = args.date or now_et.date()

    if not args.force and not is_trading_day(report_date):
        print(f"{report_date} is not a trading day — skipping (use --force to override).")
        return 0
    if settings.anthropic_api_key is None:
        print("ANTHROPIC_API_KEY is not set — see .env.example.", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    with make_http_client() as http:
        try:
            result = run_agent(
                client,
                Toolkit(http, report_date, now_et),
                model=settings.claude_model,
                report_date=report_date,
                now_et=now_et,
                effort=settings.claude_effort,
            )
        except (AgentError, anthropic.APIError) as exc:
            print(f"Run failed: {exc}", file=sys.stderr)
            return 1

    print(result.report.model_dump_json(indent=2))
    print(
        f"model={result.model} turns={result.iterations} tools={result.tool_calls} "
        f"usage={result.usage}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
