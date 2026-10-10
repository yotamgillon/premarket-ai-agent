from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from premarket_agent.agent import runner
from premarket_agent.agent.runner import AgentError, run_agent
from premarket_agent.collectors import NY_TZ
from premarket_agent.report.models import PreMarketReport

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=NY_TZ)
DAY = date(2026, 10, 12)

REPORT = PreMarketReport(
    tldr="Futures firm ahead of CPI.",
    overnight_summary="NQ +0.4% overnight.",
    key_levels=[{"instrument": "NQ", "level": 31266.5, "label": "Prior day high"}],
    scheduled_events=[
        {"time_et": "08:30", "event": "CPI m/m", "impact": "High", "note": "f 0.3% p 0.4%"}
    ],
    top_news=[{"title": "x", "source": "CNBC", "why_it_matters": "y"}],
    sentiment="risk-on",
    sentiment_rationale="r",
    bias="bullish",
    bias_rationale="b",
    risks=["Hot CPI"],
    data_gaps=[],
)


def _usage(i: int = 100, o: int = 50) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=i, output_tokens=o, cache_read_input_tokens=10, cache_creation_input_tokens=0
    )


def _tool_use(*calls: tuple[str, str, dict[str, Any]]) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="tool_use", id=i, name=n, input=inp) for i, n, inp in calls]
    return SimpleNamespace(stop_reason="tool_use", content=blocks, usage=_usage(), model="m")


def _final(report: PreMarketReport | None = REPORT, stop: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop,
        content=[],
        usage=_usage(200, 400),
        model="claude-opus-5-5",
        parsed_output=report,
        stop_details=None,
    )


class FakeClient:
    """Mimics client.beta.messages.parse with a scripted list of responses."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = iter(responses)
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot messages: the runner mutates the same list between turns.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return next(self._responses)


class FakeTools:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def execute(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        self.executed.append((name, tool_input))
        if name in self.fail:
            return "Error: source down", True
        return '{"ok": true}', False


def test_happy_path_runs_tools_then_returns_report() -> None:
    client = FakeClient(
        [
            _tool_use(
                ("t1", "get_market_snapshot", {"symbols": ["NQ=F"]}),
                ("t2", "get_economic_calendar", {}),
            ),
            _tool_use(("t3", "get_news", {"query": "cpi"})),
            _final(),
        ]
    )
    tools = FakeTools()
    result = run_agent(client, tools, "claude-opus-5-5", DAY, NOW)

    assert result.report == REPORT
    assert result.iterations == 3
    assert result.tool_calls == ["get_market_snapshot", "get_economic_calendar", "get_news"]
    assert result.usage.input_tokens == 100 + 100 + 200
    assert result.usage.output_tokens == 50 + 50 + 400
    assert result.usage.cache_read_input_tokens == 30

    # Both parallel tool results go back in ONE user message, matched by tool_use_id.
    second_call_msgs = client.calls[1]["messages"]
    results = second_call_msgs[-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert all(r["is_error"] is False for r in results)


def test_request_shape() -> None:
    client = FakeClient([_final()])
    run_agent(client, FakeTools(), "claude-opus-5-5", DAY, NOW, effort="high")
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is PreMarketReport
    assert call["output_config"] == {"effort": "high"}
    assert call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Monday, October 12, 2026" in call["messages"][0]["content"]
    assert all(t["strict"] for t in call["tools"])


def test_tool_error_is_reported_to_model_not_raised() -> None:
    client = FakeClient([_tool_use(("t1", "get_news", {"query": ""})), _final()])
    run_agent(client, FakeTools(fail={"get_news"}), "m", DAY, NOW)
    result_block = client.calls[1]["messages"][-1]["content"][0]
    assert result_block["is_error"] is True


def test_refusal_raises() -> None:
    client = FakeClient([_final(report=None, stop="refusal")])
    with pytest.raises(AgentError, match="declined"):
        run_agent(client, FakeTools(), "m", DAY, NOW)


def test_max_tokens_raises() -> None:
    client = FakeClient([_final(report=None, stop="max_tokens")])
    with pytest.raises(AgentError, match="max_tokens"):
        run_agent(client, FakeTools(), "m", DAY, NOW)


def test_iteration_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "MAX_ITERATIONS", 3)
    looping = [_tool_use(("t", "get_news", {"query": ""})) for _ in range(3)]
    with pytest.raises(AgentError, match="3 turns"):
        run_agent(FakeClient(looping), FakeTools(), "m", DAY, NOW)
