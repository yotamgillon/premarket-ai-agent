"""Futures / index price snapshots from Yahoo Finance (yfinance)."""

from datetime import datetime, time

import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from premarket_agent.collectors import NY_TZ, CollectorError

INSTRUMENTS: dict[str, str] = {
    "NQ=F": "Nasdaq-100 E-mini futures",
    "ES=F": "S&P 500 E-mini futures",
    "^VIX": "CBOE Volatility Index",
}

# CME equity futures settle at 17:00 ET and the overnight (Globex) session reopens at 18:00 ET.
SESSION_CLOSE_ET = time(17, 0)


class PriceSnapshot(BaseModel):
    symbol: str
    name: str
    as_of: datetime
    last_bar_time: datetime  # when the `last` price printed — tells you which session it reflects
    last: float
    prev_close: float
    change: float
    change_pct: float
    prior_high: float
    prior_low: float
    # Where `last` sits in the prior session's range: 0 = prior low, 100 = prior high.
    # Not clamped: >100 / <0 means price has broken out of the range.
    range_position_pct: float | None
    overnight_high: float | None
    overnight_low: float | None
    week_high: float
    week_low: float


def build_snapshot(
    symbol: str, daily: pd.DataFrame, intraday: pd.DataFrame, now: datetime
) -> PriceSnapshot:
    """Pure function: turn raw OHLC frames into a snapshot. Easy to unit test."""
    if daily.empty:
        raise CollectorError(f"no daily data for {symbol}")

    today_et = now.astimezone(NY_TZ).date()
    daily_dates = pd.DatetimeIndex(daily.index).tz_convert(NY_TZ).date
    completed = daily[daily_dates < today_et]
    if completed.empty:
        raise CollectorError(f"no completed session before {today_et} for {symbol}")
    prior = completed.iloc[-1]
    prior_date = pd.Timestamp(completed.index[-1]).tz_convert(NY_TZ).date()

    # "Overnight" = everything after the prior session's 17:00 ET close. On a Monday
    # that's Friday 17:00 onward, so the Sunday-evening reopen is included automatically.
    overnight_start = datetime.combine(prior_date, SESSION_CLOSE_ET, tzinfo=NY_TZ)
    if intraday.empty:
        overnight = intraday
    else:
        intraday_idx = pd.DatetimeIndex(intraday.index).tz_convert(NY_TZ)
        overnight = intraday[(intraday_idx >= overnight_start) & (intraday_idx <= now)]

    latest = intraday if not intraday.empty else daily
    last = float(latest["Close"].iloc[-1])
    prev_close = float(prior["Close"])
    change = last - prev_close
    week = daily.tail(5)
    prior_high, prior_low = float(prior["High"]), float(prior["Low"])
    prior_range = prior_high - prior_low
    range_position_pct = (
        round((last - prior_low) / prior_range * 100, 1) if prior_range > 0 else None
    )

    return PriceSnapshot(
        symbol=symbol,
        name=INSTRUMENTS.get(symbol, symbol),
        as_of=now,
        last_bar_time=pd.Timestamp(latest.index[-1]).tz_convert(NY_TZ).to_pydatetime(),
        last=round(last, 2),
        prev_close=round(prev_close, 2),
        change=round(change, 2),
        change_pct=round(change / prev_close * 100, 2),
        prior_high=round(prior_high, 2),
        prior_low=round(prior_low, 2),
        range_position_pct=range_position_pct,
        overnight_high=round(float(overnight["High"].max()), 2) if not overnight.empty else None,
        overnight_low=round(float(overnight["Low"].min()), 2) if not overnight.empty else None,
        week_high=round(float(week["High"].max()), 2),
        week_low=round(float(week["Low"].min()), 2),
    )


def fetch_snapshot(symbol: str, now: datetime | None = None) -> PriceSnapshot:
    now = now or datetime.now(NY_TZ)
    try:
        ticker = yf.Ticker(symbol)
        daily = ticker.history(period="10d", interval="1d")
        # 5 days of 15m bars so a Monday run still sees Friday's close + Sunday's reopen.
        intraday = ticker.history(period="5d", interval="15m")
    except Exception as exc:  # yfinance raises a zoo of exception types
        raise CollectorError(f"yfinance failed for {symbol}: {exc}") from exc
    return build_snapshot(symbol, daily, intraday, now)


def fetch_all(
    symbols: list[str] | None = None, now: datetime | None = None
) -> dict[str, PriceSnapshot | str]:
    """Fetch every instrument; a failure becomes an error string instead of aborting the run."""
    results: dict[str, PriceSnapshot | str] = {}
    for symbol in symbols or list(INSTRUMENTS):
        try:
            results[symbol] = fetch_snapshot(symbol, now)
        except CollectorError as exc:
            results[symbol] = f"unavailable: {exc}"
    return results
