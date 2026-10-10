import json
from pathlib import Path
from typing import Any

import pytest

import premarket_agent.__main__ as cli
from premarket_agent.agent.runner import AgentError, Usage
from premarket_agent.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key="sk-test",
        claude_model="claude-sonnet-5-5",
        reports_dir=tmp_path,
        pushgateway_url="http://pushgateway:9091",
    )


@pytest.fixture
def pushed(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> list[Any]:
    calls: list[Any] = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "push_metrics", lambda url, record: calls.append(record) or True)
    return calls


def _runs(settings: Settings) -> list[dict[str, Any]]:
    lines = (settings.reports_dir / "runs.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def test_success_is_recorded(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, pushed: list[Any]
) -> None:
    def fake_generate(_s: Settings, record: Any, *_a: Any) -> None:
        record.tokens = {"input": 1}
        record.cost_usd = 0.01

    monkeypatch.setattr(cli, "generate", fake_generate)
    assert cli.main(["--date", "2026-10-12"]) == 0
    [run] = _runs(settings)
    assert run["status"] == "success"
    assert run["cost_usd"] == 0.01
    assert run["duration_s"] >= 0
    assert pushed[0].success == 1


def test_agent_failure_records_partial_cost(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, pushed: list[Any]
) -> None:
    def failing_generate(*_a: Any) -> None:
        raise AgentError("model declined", Usage(input_tokens=1000, output_tokens=100))

    # generate() is what converts AgentError.usage into cost; exercise that path directly.
    monkeypatch.setattr(cli, "run_agent", lambda *a, **k: failing_generate())
    assert cli.main(["--date", "2026-10-12"]) == 1
    [run] = _runs(settings)
    assert run["status"] == "failed"
    assert "model declined" in run["error"]
    assert run["tokens"]["input"] == 1000
    assert run["cost_usd"] == pytest.approx((1000 * 2 + 100 * 10) / 1_000_000)
    assert pushed[0].success == 0


def test_unexpected_exception_still_recorded(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, pushed: list[Any]
) -> None:
    def buggy(*_a: Any) -> None:
        raise ZeroDivisionError("oops")

    monkeypatch.setattr(cli, "generate", buggy)
    assert cli.main(["--date", "2026-10-12"]) == 1
    assert _runs(settings)[0]["error"] == "ZeroDivisionError: oops"
    assert len(pushed) == 1


def test_skipped_day_writes_nothing(settings: Settings, pushed: list[Any]) -> None:
    assert cli.main(["--date", "2026-10-10"]) == 0
    assert not (settings.reports_dir / "runs.jsonl").exists()
    assert pushed == []
