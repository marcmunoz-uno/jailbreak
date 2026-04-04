#!/usr/bin/env python3
"""Telegram alert module for the OpenClaw health watchdog."""

import urllib.request
import json
import os
import sys

BOT_TOKEN = os.environ.get("WATCHDOG_TELEGRAM_TOKEN", "REDACTED")
CHAT_ID = os.environ.get("WATCHDOG_TELEGRAM_CHAT", "REDACTED")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

SEVERITY_PREFIX = {
    "INFO": "\u2139\ufe0f",
    "WARNING": "\u26a0\ufe0f",
    "CRITICAL": "\U0001f534",
}


def send_alert(message: str, severity: str = "WARNING") -> bool:
    """Send alert to Telegram. Severity: INFO, WARNING, CRITICAL.
    Returns True on success, False on failure.
    """
    prefix = SEVERITY_PREFIX.get(severity, "\u2753")
    text = f"{prefix} *Watchdog Alert*\n\n{message}"
    return _send(text)


def send_daily_report(report: str) -> bool:
    """Send daily health report. Returns True on success."""
    text = f"\U0001f4ca *Daily Health Report*\n\n{report}"
    return _send(text)


def _send(text: str) -> bool:
    """Low-level send to Telegram API using only stdlib."""
    # Telegram MarkdownV1 requires escaping certain chars in dynamic content,
    # but we control the format so keep it simple.
    data = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status == 200
    except Exception as e:
        print(f"[telegram] alert failed: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # Quick test
    ok = send_alert("Watchdog telegram module self-test.", "INFO")
    print("sent" if ok else "failed")
