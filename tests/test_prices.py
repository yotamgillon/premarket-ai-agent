from datetime import datetime

import pandas as pd
import pytest

from premarket_agent.collectors import NY_TZ, CollectorError, prices


def _daily(rows: list[tuple[str, float, float, float]]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(d, tz=NY_TZ) for d, *_ in rows])
    return pd.DataFrame(
        {"High": [r[1] for r in rows], "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]},
        index=idx,
    )


def _intraday(rows: list[tuple[str, float, float, float]]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(ts, tz=NY_TZ) for ts, *_ in rows])
    return pd.DataFrame(
        {"High": [r[1] for r in rows], "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]},
        index=idx,
    )


# Daily bars: Thu, Fri completed; Mon (today) in progress.
DAILY = _daily(
    [
        ("2026-10-08", 105.0, 95.0, 100.0),
        ("2026-10-09", 110.0, 98.0, 108.0),
        ("2026-10-12", 112.0, 107.0, 111.0),
    ]
)
INTRADAY = _intraday(
    [
        ("2026-10-09 15:45", 109.0, 107.0, 108.0),  # Fri regular session — not overnight
        ("2026-10-11 18:00", 109.5, 107.5, 109.0),  # Sun reopen — overnight
        ("2026-10-12 03:00", 112.0, 108.5, 111.5),  # overnight
        ("2026-10-12 07:45", 111.8, 110.5, 111.0),  # last bar before "now"
    ]
)
MONDAY_8AM = datetime(2026, 10, 12, 8, 0, tzinfo=NY_TZ)


def test_build_snapshot_monday_includes_weekend_reopen() -> None:
    snap = prices.build_snapshot("NQ=F", DAILY, INTRADAY, MONDAY_8AM)
    assert snap.name == "Nasdaq-100 E-mini futures"
    assert snap.prev_close == 108.0  # Friday close, not today's in-progress bar
    assert snap.prior_high == 110.0
    assert snap.prior_low == 98.0
    assert snap.last == 111.0
    assert snap.change == 3.0
    assert snap.change_pct == pytest.approx(2.78)
    assert snap.overnight_high == 112.0
    assert snap.overnight_low == 107.5  # Sunday bar counted, Friday 15:45 bar excluded
    assert snap.week_high == 112.0
    assert snap.week_low == 95.0


def test_build_snapshot_no_overnight_bars() -> None:
    # e.g. ^VIX, which has no Globex-style overnight session
    snap = prices.build_snapshot("^VIX", DAILY, INTRADAY.iloc[:1], MONDAY_8AM)
    assert snap.overnight_high is None
    assert snap.overnight_low is None


def test_build_snapshot_empty_daily_raises() -> None:
    with pytest.raises(CollectorError):
        prices.build_snapshot("NQ=F", DAILY.iloc[0:0], INTRADAY, MONDAY_8AM)


def test_fetch_all_turns_failure_into_message(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        def history(self, period: str, interval: str) -> pd.DataFrame:
            if self.symbol == "^VIX":
                raise ConnectionError("boom")
            return DAILY if interval == "1d" else INTRADAY

    monkeypatch.setattr(prices.yf, "Ticker", FakeTicker)
    result = prices.fetch_all(["NQ=F", "^VIX"], now=MONDAY_8AM)
    assert isinstance(result["NQ=F"], prices.PriceSnapshot)
    assert isinstance(result["^VIX"], str)
    assert "boom" in result["^VIX"]
