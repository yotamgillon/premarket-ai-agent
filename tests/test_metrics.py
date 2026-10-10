from datetime import datetime
from typing import Any

import pytest
from prometheus_client import generate_latest

from premarket_agent.observability import metrics
from premarket_agent.observability.run_record import RunRecord


def _record(status: str = "success") -> RunRecord:
    return RunRecord(
        report_date="2026-10-12",
        started_at=datetime(2026, 10, 12, 8, 0),
        status=status,
        duration_s=26.4,
        model="claude-sonnet-5-5",
        iterations=2,
        tool_calls=["get_market_snapshot", "get_news", "get_economic_calendar"],
        tokens={"input": 4357, "output": 1368, "cache_read": 2985, "cache_write": 2985},
        cost_usd=0.030454,
    )


def _exposition(record: RunRecord) -> str:
    return generate_latest(metrics.build_registry(record, now=1_760_000_000)).decode()


def test_success_metrics() -> None:
    text = _exposition(_record())
    assert "premarket_run_success 1.0" in text
    assert "premarket_run_duration_seconds 26.4" in text
    assert "premarket_run_cost_usd 0.030454" in text
    assert 'premarket_run_tokens{type="output"} 1368.0' in text
    assert "premarket_run_tool_calls 3.0" in text
    assert 'premarket_run_info{model="claude-sonnet-5-5",status="success"} 1.0' in text
    assert "premarket_last_success_timestamp_seconds 1.76e+09" in text


def test_failed_run_does_not_touch_last_success() -> None:
    text = _exposition(_record(status="failed"))
    assert "premarket_run_success 0.0" in text
    assert "premarket_last_success_timestamp_seconds" not in text
    assert "premarket_last_run_timestamp_seconds" in text


def test_push_uses_pushadd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        metrics, "pushadd_to_gateway", lambda url, **kw: calls.append(kw | {"url": url})
    )
    assert metrics.push_metrics("http://pushgateway:9091", _record())
    assert calls[0]["url"] == "http://pushgateway:9091"
    assert calls[0]["job"] == "premarket_agent"


def test_push_failure_is_swallowed() -> None:
    # Nothing listens on port 9 (discard): connection refused -> logged, returns False.
    assert metrics.push_metrics("http://127.0.0.1:9", _record()) is False
