"""Structured JSON logging (stdlib only). One JSON object per line on stdout.

JSON logs are machine-parseable: `docker logs agent | jq 'select(.level=="ERROR")'`,
CloudWatch / Loki / Datadog ingest them without regex parsing.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has; anything else came from `extra=` and is ours to emit.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Third-party libraries are chatty at INFO (every HTTP request); keep them at WARNING.
    for noisy in ("httpx", "httpx2", "httpcore", "anthropic", "yfinance", "urllib3", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
