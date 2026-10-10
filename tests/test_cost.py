import pytest

from premarket_agent.agent.runner import Usage
from premarket_agent.observability.cost import PRICES, cost_usd


def test_cost_sonnet_matches_hand_calculation() -> None:
    usage = Usage(
        input_tokens=4357,
        output_tokens=1368,
        cache_read_input_tokens=2985,
        cache_creation_input_tokens=2985,
    )
    # 4357*2 + 1368*10 + 2985*0.20 + 2985*2*1.25  (per million tokens)
    expected = (8714 + 13680 + 597 + 7462.5) / 1_000_000
    assert cost_usd("claude-sonnet-5-5", usage) == pytest.approx(expected, abs=1e-6)


def test_output_tokens_dominate() -> None:
    opus = PRICES["claude-opus-5-5"]
    assert opus.output == 5 * opus.input
    assert opus.cache_write == pytest.approx(5.0)


def test_unknown_model_returns_none() -> None:
    assert cost_usd("some-future-model", Usage(input_tokens=10)) is None


def test_zero_usage_is_free() -> None:
    assert cost_usd("claude-opus-5-5", Usage()) == 0.0
