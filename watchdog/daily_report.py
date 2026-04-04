#!/usr/bin/env python3
"""
OpenClaw Daily Health Report
=============================
Generates a comprehensive daily summary and sends it via Telegram.

Schedule: 0 8 * * * /usr/bin/python3 /Users/marcmunoz/.openclaw/watchdog/daily_report.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure imports work from the watchdog directory
sys.path.insert(0, str(Path(__file__).parent))

from watchdog import (
    SERVICES, CONFIGS, LOG_DIR, LEAD_PIPELINE_DIR, MEMECOIN_SCAN,
    CRON_JOBS_FILE,
    check_port, check_health_url, check_process_running,
    get_disk_free_gb, file_size_mb, file_size_gb, file_age_hours,
)
from telegram import send_daily_report

BASE = Path("/Users/marcmunoz/.openclaw")
CRON_RUNS_DIR = BASE / "cron" / "runs"


def section_services() -> str:
    """Report on all monitored services."""
    lines = ["*Services*"]
    for svc in SERVICES:
        name = svc["name"]
        statuses = []

        proc = svc.get("process")
        if proc:
            statuses.append("proc:" + ("\u2705" if check_process_running(proc) else "\u274c"))

        port = svc.get("port")
        if port:
            statuses.append(f"port {port}:" + ("\u2705" if check_port(port) else "\u274c"))

        url = svc.get("health_url")
        if url:
            statuses.append("health:" + ("\u2705" if check_health_url(url) else "\u274c"))

        lines.append(f"  {name}: {' | '.join(statuses)}")
    return "\n".join(lines)


def section_configs() -> str:
    """Report on config file validity."""
    lines = ["*Configs*"]
    for cfg in CONFIGS:
        path = cfg["path"]
        basename = os.path.basename(path)
        try:
            data = json.loads(Path(path).read_text())
            required = cfg.get("required_keys", [])
            if required:
                missing = [k for k in required if k not in data]
                if missing:
                    lines.append(f"  {basename}: \u26a0\ufe0f missing keys: {', '.join(missing)}")
                else:
                    lines.append(f"  {basename}: \u2705 valid ({len(data)} keys)")
            else:
                lines.append(f"  {basename}: \u2705 valid JSON")
        except FileNotFoundError:
            lines.append(f"  {basename}: \u274c not found")
        except json.JSONDecodeError:
            lines.append(f"  {basename}: \u274c invalid JSON")
    return "\n".join(lines)


def section_cron_jobs() -> str:
    """Report on cron job activity in the last 24h."""
    lines = ["*Cron Jobs (24h)*"]

    try:
        jobs_data = json.loads(CRON_JOBS_FILE.read_text())
        jobs = jobs_data.get("jobs", [])
    except Exception:
        lines.append("  Could not read jobs.json")
        return "\n".join(lines)

    now_ms = time.time() * 1000
    cutoff_ms = now_ms - 86_400_000  # 24h ago

    for job in jobs:
        name = job.get("name", job.get("id", "unknown")[:20])
        enabled = job.get("enabled", False)
        state = job.get("state", {})

        if not enabled:
            lines.append(f"  {name}: disabled")
            continue

        last_run_ms = state.get("lastRunAtMs", 0)
        last_status = state.get("lastRunStatus", state.get("lastStatus", "n/a"))
        consec_errors = state.get("consecutiveErrors", 0)
        duration_ms = state.get("lastDurationMs", 0)

        if last_run_ms > cutoff_ms:
            ago_h = (now_ms - last_run_ms) / 3_600_000
            status_icon = "\u2705" if last_status in ("ok", "success") else "\u274c"
            dur_s = duration_ms / 1000 if duration_ms else 0
            lines.append(f"  {status_icon} {name}: {last_status} ({ago_h:.1f}h ago, {dur_s:.0f}s)")
        else:
            lines.append(f"  \u23f3 {name}: no run in 24h")

        if consec_errors > 0:
            lines.append(f"     \u26a0\ufe0f {consec_errors} consecutive errors")

    return "\n".join(lines)


def section_resources() -> str:
    """Report on disk, logs, etc."""
    lines = ["*Resources*"]

    # Disk
    free_gb = get_disk_free_gb()
    icon = "\u2705" if free_gb >= 10 else "\u274c"
    lines.append(f"  {icon} Disk free: {free_gb:.1f}GB")

    # Large logs
    big_logs = []
    if LOG_DIR.is_dir():
        for f in sorted(LOG_DIR.iterdir()):
            if f.is_file():
                size = file_size_mb(f)
                if size > 100:  # report anything > 100MB in daily report
                    big_logs.append((f.name, size))

    if big_logs:
        lines.append("  Large logs:")
        for name, size in big_logs:
            icon = "\u274c" if size > 500 else "\u26a0\ufe0f"
            lines.append(f"    {icon} {name}: {size:.0f}MB")
    else:
        lines.append("  \u2705 No oversized logs")

    # Hermes WAL
    wal_paths = [
        Path.home() / "hermes" / "state.db-wal",
        Path.home() / ".hermes" / "state.db-wal",
        BASE / "data" / "hermes" / "state.db-wal",
    ]
    for wal in wal_paths:
        if wal.exists():
            size = file_size_gb(wal)
            icon = "\u274c" if size > 5 else ("\u26a0\ufe0f" if size > 3 else "\u2705")
            lines.append(f"  {icon} Hermes WAL: {size:.1f}GB")
            break

    return "\n".join(lines)


def section_pipelines() -> str:
    """Report on data pipeline freshness."""
    lines = ["*Data Pipelines*"]

    # Daily leads
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_csv = LEAD_PIPELINE_DIR / f"{today_str}.csv"
    if today_csv.exists():
        size_kb = today_csv.stat().st_size / 1024
        lines.append(f"  \u2705 Daily leads ({today_str}): {size_kb:.0f}KB")
    else:
        # Check recent files
        recent = sorted(LEAD_PIPELINE_DIR.glob("*.csv"), reverse=True)
        if recent:
            last = recent[0].stem
            lines.append(f"  \u26a0\ufe0f No leads today; last: {last}")
        else:
            lines.append(f"  \u274c No lead CSVs found")

    # Memecoin scan
    if MEMECOIN_SCAN.exists():
        age_h = file_age_hours(MEMECOIN_SCAN)
        icon = "\u2705" if age_h < 24 else "\u274c"
        lines.append(f"  {icon} Memecoin scan: {age_h:.1f}h old")
    else:
        lines.append(f"  \u274c Memecoin scan: not found")

    return "\n".join(lines)


def generate_report() -> str:
    """Build the full daily report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    sections = [
        f"*{now}*\n",
        section_services(),
        "",
        section_configs(),
        "",
        section_cron_jobs(),
        "",
        section_resources(),
        "",
        section_pipelines(),
    ]
    return "\n".join(sections)


def main():
    dry_run = "--dry" in sys.argv
    report = generate_report()

    print(report)
    print()

    if dry_run:
        print("[dry-run] Skipping Telegram send.")
        return

    ok = send_daily_report(report)
    print("Daily report sent." if ok else "Failed to send daily report.")


if __name__ == "__main__":
    main()
