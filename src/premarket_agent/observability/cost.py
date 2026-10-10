"""Turn token usage into dollars.

Prices are USD per million tokens (Anthropic first-party API). Update the table when
pricing changes; an unknown model yields cost=None rather than a wrong number.
"""

from dataclasses import dataclass

from premarket_agent.agent.runner import Usage

# 5-minute cache writes are billed at 1.25x the base input price.
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float

    @property
    def cache_write(self) -> float:
        return self.input * CACHE_WRITE_MULTIPLIER


PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": ModelPrice(input=10.00, output=50.00, cache_read=0.25),
    "claude-opus-5-5": ModelPrice(input=4.00, output=20.00, cache_read=0.20),
    "claude-opus-5": ModelPrice(input=5.00, output=25.00, cache_read=0.50),
    "claude-sonnet-5-5": ModelPrice(input=2.00, output=10.00, cache_read=0.20),
    "claude-haiku-5-5": ModelPrice(input=0.10, output=0.50, cache_read=0.01),
}


def cost_usd(model: str, usage: Usage) -> float | None:
    """Dollar cost of a run. Note `input_tokens` is only the uncached part of the prompt."""
    price = PRICES.get(model)
    if price is None:
        return None
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_input_tokens * price.cache_read
        + usage.cache_creation_input_tokens * price.cache_write
    ) / 1_000_000
    return round(total, 6)
