"""The agent loop: call Claude, run requested tools, repeat until a report comes back."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from premarket_agent.agent.prompts import SYSTEM_PROMPT, user_prompt
from premarket_agent.agent.tools import TOOL_DEFINITIONS
from premarket_agent.report.models import PreMarketReport

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8
MAX_TOKENS = 16000
# If a safety classifier declines, the API retries on Anthropic's recommended fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AgentError(RuntimeError):
    """The agent could not produce a report. Carries the tokens spent before failing."""

    def __init__(self, message: str, usage: "Usage | None" = None) -> None:
        super().__init__(message)
        self.usage = usage


class ToolExecutor(Protocol):
    def execute(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]: ...


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_input_tokens += usage.cache_read_input_tokens or 0
        self.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0

    def as_dict(self) -> dict[str, int]:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cache_read": self.cache_read_input_tokens,
            "cache_write": self.cache_creation_input_tokens,
        }


@dataclass
class AgentResult:
    report: PreMarketReport
    model: str
    usage: Usage
    iterations: int
    tool_calls: list[str] = field(default_factory=list)


def run_agent(
    client: Any,
    tools: ToolExecutor,
    model: str,
    report_date: date,
    now_et: datetime,
    effort: str = "medium",
) -> AgentResult:
    """Run the tool-use loop.

    A hand-written loop (rather than the SDK's beta tool runner) so that token usage is
    accounted for on every turn, the number of turns is capped, and every stop reason is
    handled explicitly.
    """
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt(report_date, now_et)}]
    usage = Usage()
    tool_calls: list[str] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.beta.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            # cache_control on the system block caches tools + system prompt (the stable prefix).
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            tools=TOOL_DEFINITIONS,
            messages=messages,
            output_format=PreMarketReport,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        usage.add(response.usage)
        log.info(
            "agent turn",
            extra={"iteration": iteration, "stop_reason": response.stop_reason},
        )

        if response.stop_reason == "refusal":
            raise AgentError(f"model declined the request: {response.stop_details}", usage)
        if response.stop_reason == "max_tokens":
            raise AgentError("response hit max_tokens before finishing", usage)

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tool_calls.append(block.name)
                output, is_error = tools.execute(block.name, block.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                        "is_error": is_error,
                    }
                )
            # All results for one turn go back in a single user message.
            messages.append({"role": "user", "content": results})
            continue

        report = response.parsed_output
        if report is None:
            raise AgentError(f"no structured report (stop_reason={response.stop_reason})", usage)
        return AgentResult(
            report=report,
            model=response.model,
            usage=usage,
            iterations=iteration,
            tool_calls=tool_calls,
        )

    raise AgentError(f"no report after {MAX_ITERATIONS} turns", usage)
