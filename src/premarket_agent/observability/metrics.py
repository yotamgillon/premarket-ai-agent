"""Prometheus metrics for a batch job, delivered via the Pushgateway.

Prometheus normally *pulls* (scrapes) long-running services. This agent runs once a day for
~30 seconds and exits, so there is nothing to scrape. The job pushes its final metrics to a
Pushgateway, which holds them for Prometheus to scrape.
"""

import logging
import time

from prometheus_client import CollectorRegistry, Gauge, pushadd_to_gateway

from premarket_agent.observability.run_record import RunRecord

log = logging.getLogger(__name__)

JOB_NAME = "premarket_agent"


def build_registry(record: RunRecord, now: float | None = None) -> CollectorRegistry:
    now = now or time.time()
    registry = CollectorRegistry()

    def gauge(name: str, doc: str, value: float, labels: dict[str, str] | None = None) -> None:
        g = Gauge(name, doc, list(labels or {}), registry=registry)
        (g.labels(**labels) if labels else g).set(value)

    gauge("premarket_run_success", "1 if the last run produced a report, else 0", record.success)
    gauge(
        "premarket_run_duration_seconds", "Wall-clock duration of the last run", record.duration_s
    )
    gauge("premarket_last_run_timestamp_seconds", "Unix time the last run finished", now)
    gauge("premarket_run_iterations", "Agent loop turns in the last run", record.iterations)
    gauge("premarket_run_tool_calls", "Tool calls made in the last run", len(record.tool_calls))
    if record.cost_usd is not None:
        gauge("premarket_run_cost_usd", "Estimated API cost of the last run (USD)", record.cost_usd)

    tokens = Gauge(
        "premarket_run_tokens",
        "Tokens used in the last run, by type",
        ["type"],
        registry=registry,
    )
    for kind, value in record.tokens.items():
        tokens.labels(type=kind).set(value)

    info = Gauge(
        "premarket_run_info",
        "Model and outcome of the last run",
        ["model", "status"],
        registry=registry,
    )
    info.labels(model=record.model or "unknown", status=record.status).set(1)

    # Only pushed on success. With pushadd (HTTP POST), metrics absent from a push are kept,
    # so a failed run leaves the previous success timestamp in place. That is what lets an
    # alert say "no successful run in 26h" instead of losing the history on the first failure.
    if record.success:
        gauge("premarket_last_success_timestamp_seconds", "Unix time of the last success", now)
    return registry


def push_metrics(gateway_url: str, record: RunRecord) -> bool:
    """Push to the Pushgateway. Monitoring must never break the job, so errors are logged."""
    try:
        pushadd_to_gateway(gateway_url, job=JOB_NAME, registry=build_registry(record), timeout=5)
    except OSError as exc:
        log.warning("metrics push failed", extra={"gateway": gateway_url, "error": str(exc)})
        return False
    return True
