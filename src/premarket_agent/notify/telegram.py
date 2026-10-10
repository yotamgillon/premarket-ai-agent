"""Send the report summary + HTML file to a Telegram chat via the Bot API."""

from html import escape
from pathlib import Path

import httpx

from premarket_agent.report.render import RenderedReport

API = "https://api.telegram.org/bot{token}/{method}"


def summary_text(rendered: RenderedReport) -> str:
    """Short message for the phone screen. Uses Telegram's HTML parse mode."""
    r = rendered.report
    lines = [
        f"<b>Pre-Market — {rendered.report_date:%a %b %d}</b>",
        escape(r.tldr),
        "",
        f"<b>Bias:</b> {r.bias} · <b>Sentiment:</b> {r.sentiment}",
    ]
    for s in rendered.snapshots:
        lines.append(f"<code>{escape(s.symbol):6}</code> {s.last:,.2f} ({s.change_pct:+.2f}%)")
    if r.scheduled_events:
        lines += ["", "<b>Events (ET)</b>"]
        lines += [f"{e.time_et} {escape(e.event)} [{e.impact}]" for e in r.scheduled_events]
    return "\n".join(lines)


def send_telegram(
    client: httpx.Client, token: str, chat_id: str, rendered: RenderedReport, html_path: Path
) -> None:
    resp = client.post(
        API.format(token=token, method="sendMessage"),
        data={"chat_id": chat_id, "text": summary_text(rendered), "parse_mode": "HTML"},
    )
    resp.raise_for_status()
    with html_path.open("rb") as f:
        resp = client.post(
            API.format(token=token, method="sendDocument"),
            data={"chat_id": chat_id},
            files={"document": (f"premarket-{rendered.report_date}.html", f, "text/html")},
        )
    resp.raise_for_status()
