"""Send the report as an HTML email (with a Markdown plain-text fallback) over SMTP."""

import smtplib
from email.message import EmailMessage

from premarket_agent.report.render import RenderedReport


def build_message(rendered: RenderedReport, sender: str, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = (
        f"Pre-Market {rendered.report_date:%a %b %d}: {rendered.report.bias.upper()} — "
        f"{rendered.report.tldr[:80]}"
    )
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(rendered.markdown())
    msg.add_alternative(rendered.html(), subtype="html")
    return msg


def send_email(
    rendered: RenderedReport,
    host: str,
    port: int,
    user: str | None,
    password: str | None,
    to: str,
    timeout: float = 20.0,
) -> None:
    msg = build_message(rendered, sender=user or "premarket-agent@localhost", to=to)
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
