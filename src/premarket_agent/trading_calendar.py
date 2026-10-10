"""Is the US equity market open on a given day?"""

from datetime import date

import holidays


def is_trading_day(day: date) -> bool:
    """Weekdays that are not NYSE holidays. Used to skip the cron run on days off."""
    if day.weekday() >= 5:
        return False
    return day not in holidays.financial_holidays("NYSE", years=day.year)
