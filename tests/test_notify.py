from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from premarket_agent.collectors import NY_TZ
from premarket_agent.config import Settings
from premarket_agent.notify import email as email_mod
from premarket_agent.notify import send_notifications
from premarket_agent.notify.email import build_message
from premarket_agent.notify.telegram import summary_text
from premarket_agent.report.models import PreMarketReport
from premarket_agent.report.render import RenderedReport, write_report


@pytest.fixture
def rendered(sample_report: PreMarketReport) -> RenderedReport:
    return RenderedReport(
        report=sample_report,
        report_date=date(2026, 10, 12),
        generated_at=datetime(2026, 10, 12, 8, 5, tzinfo=NY_TZ),
        model="m",
    )


def _settings(**overrides: Any) -> Settings:
    # _env_file=None: ignore any real .env on the developer's machine.
    return Settings(_env_file=None, **overrides)


def test_telegram_summary_escapes_html(rendered: RenderedReport) -> None:
    rendered.report = rendered.report.model_copy(update={"tldr": "S&P <up>"})
    text = summary_text(rendered)
    assert "S&amp;P &lt;up&gt;" in text
    assert "08:30 CPI m/m [High]" in text


def test_send_notifications_telegram(rendered: RenderedReport, tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"ok": True})

    out = write_report(rendered, tmp_path)
    settings = _settings(telegram_bot_token="123:abc", telegram_chat_id="42")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert send_notifications(settings, rendered, out, client) == {"telegram": True}
    assert calls == ["sendMessage", "sendDocument"]


def test_telegram_failure_does_not_raise(
    rendered: RenderedReport, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    out = write_report(rendered, tmp_path)
    settings = _settings(telegram_bot_token="123:secret-token", telegram_chat_id="42")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    assert send_notifications(settings, rendered, out, client) == {"telegram": False}
    assert "secret-token" not in caplog.text


def test_no_channels_configured(rendered: RenderedReport, tmp_path: Path) -> None:
    assert send_notifications(_settings(), rendered, tmp_path, httpx.Client()) == {}


def test_email_message_has_text_and_html(rendered: RenderedReport) -> None:
    msg = build_message(rendered, sender="a@x.com", to="b@x.com")
    assert msg["Subject"].startswith("Pre-Market Mon Oct 12: BULLISH")
    types = [part.get_content_type() for part in msg.iter_parts()]
    assert types == ["text/plain", "text/html"]


def test_send_email_uses_starttls_and_login(
    rendered: RenderedReport, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            events.append(f"connect {host}:{port}")

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *_: object) -> None:
            events.append("quit")

        def starttls(self) -> None:
            events.append("starttls")

        def login(self, user: str, password: str) -> None:
            events.append(f"login {user}")

        def send_message(self, msg: object) -> None:
            events.append("send")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    settings = _settings(
        smtp_host="smtp.test", smtp_user="me@x.com", smtp_password="pw", email_to="you@x.com"
    )
    assert send_notifications(settings, rendered, tmp_path, httpx.Client()) == {"email": True}
    assert events == ["connect smtp.test:587", "starttls", "login me@x.com", "send", "quit"]
