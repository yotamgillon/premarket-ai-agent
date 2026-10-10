"""CLI entrypoint: `python -m premarket_agent` or `premarket-agent`."""

import argparse
from datetime import date

from premarket_agent.config import get_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a pre-market research report.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Report date (YYYY-MM-DD). Defaults to today in the configured timezone.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    print(f"premarket-agent: model={settings.claude_model} date={args.date or 'today'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
