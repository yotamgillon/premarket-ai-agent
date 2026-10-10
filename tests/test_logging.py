import json
import logging

from premarket_agent.observability.logging import JsonFormatter


def _format(**extra: object) -> dict[str, object]:
    record = logging.LogRecord(
        "premarket_agent", logging.INFO, __file__, 1, "run %s", ("done",), None
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonFormatter().format(record))


def test_json_line_has_core_fields() -> None:
    out = _format()
    assert out["level"] == "INFO"
    assert out["logger"] == "premarket_agent"
    assert out["msg"] == "run done"
    assert out["ts"].endswith("+00:00")


def test_extra_fields_are_included() -> None:
    out = _format(iteration=2, stop_reason="tool_use")
    assert out["iteration"] == 2
    assert out["stop_reason"] == "tool_use"
    assert "args" not in out and "pathname" not in out  # stdlib noise excluded
