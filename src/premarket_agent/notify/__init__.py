"""Optional delivery channels. A failed notification never fails the run."""

import logging
from pathlib import Path

import httpx

from premarket_agent.config import Settings
from premarket_agent.notify.email import send_email
from premarket_agent.notify.telegram import send_telegram
from premarket_agent.report.render import RenderedReport

log = logging.getLogger(__name__)


def send_notifications(
    settings: Settings, rendered: RenderedReport, out_dir: Path, client: httpx.Client
) -> dict[str, bool]:
    """Send to every configured channel. Returns {channel: succeeded}."""
    results: dict[str, bool] = {}

    if settings.telegram_enabled:
        assert settings.telegram_bot_token and settings.telegram_chat_id
        try:
            send_telegram(
                client,
                settings.telegram_bot_token.get_secret_value(),
                settings.telegram_chat_id,
                rendered,
                out_dir / "report.html",
            )
            results["telegram"] = True
        except httpx.HTTPError as exc:
            # Don't log the exception text: the bot token is part of the request URL.
            log.warning("telegram notification failed: %s", type(exc).__name__)
            results["telegram"] = False

    if settings.email_enabled:
        assert settings.smtp_host and settings.email_to
        try:
            send_email(
                rendered,
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                password=settings.smtp_password.get_secret_value()
                if settings.smtp_password
                else None,
                to=settings.email_to,
            )
            results["email"] = True
        except OSError as exc:  # covers socket errors and smtplib.SMTPException
            log.warning("email notification failed: %s", exc)
            results["email"] = False

    return results
