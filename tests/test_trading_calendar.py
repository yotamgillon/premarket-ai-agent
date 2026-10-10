from datetime import date

import pytest

from premarket_agent.trading_calendar import is_trading_day


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 12), True),  # regular Monday (Columbus Day — NYSE open)
        (date(2026, 10, 10), False),  # Saturday
        (date(2026, 11, 26), False),  # Thanksgiving
        (date(2026, 7, 3), False),  # Independence Day observed (Jul 4 is a Saturday)
        (date(2026, 12, 25), False),  # Christmas
    ],
)
def test_is_trading_day(day: date, expected: bool) -> None:
    assert is_trading_day(day) is expected
