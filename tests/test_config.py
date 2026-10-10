from pathlib import Path

import pytest

from premarket_agent.__main__ import main
from premarket_agent.config import Settings


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run from an empty dir so a developer's real .env never leaks into tests.
    monkeypatch.chdir(tmp_path)
    for var in ("ANTHROPIC_API_KEY", "CLAUDE_MODEL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)


def test_defaults() -> None:
    s = Settings()
    assert s.claude_model == "claude-opus-5-5"
    assert s.anthropic_api_key is None
    assert s.reports_dir == Path("reports")
    assert not s.telegram_enabled


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    s = Settings()
    assert s.claude_model == "claude-sonnet-5-5"
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-test"
    assert s.telegram_enabled


def test_secret_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-super-secret")
    assert "sk-super-secret" not in repr(Settings())


def test_cli_runs() -> None:
    assert main(["--date", "2026-10-12"]) == 0
