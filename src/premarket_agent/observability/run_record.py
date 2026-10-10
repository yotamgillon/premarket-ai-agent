"""One record per run: the unit of observability. Logged, appended to runs.jsonl, pushed."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class RunRecord:
    report_date: str
    started_at: datetime
    status: str = "failed"  # "success" | "failed" | "skipped"
    duration_s: float = 0.0
    model: str | None = None
    iterations: int = 0
    tool_calls: list[str] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    report_path: str | None = None
    error: str | None = None
    notifications: dict[str, bool] = field(default_factory=dict)

    @property
    def success(self) -> int:
        return int(self.status == "success")

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


def append_run_log(record: RunRecord, path: Path) -> None:
    """Append-only history: `jq -s 'map(.cost_usd) | add' runs.jsonl` = total spend."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.to_json() + "\n")
