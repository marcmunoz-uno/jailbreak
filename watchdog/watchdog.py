#!/usr/bin/env python3
"""
OpenClaw Health Watchdog
========================
Cron-ready script that checks services, configs, cron jobs, resources,
and data pipelines. Sends Telegram alerts on failures with cooldown
to avoid spam.

Usage:
    python3 watchdog.py          # run all checks
    python3 watchdog.py --dry    # print results, skip Telegram

Schedule: */5 * * * * /usr/bin/python3 /Users/marcmunoz/.openclaw/watchdog/watchdog.py
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE = Path("/Users/marcmunoz/.openclaw")
STATE_FILE = BASE / "watchdog" / "state.json"
ALERT_COOLDOWN_MINUTES = 30

SERVICES = [
    {"name": "OpenClaw Gateway", "port": 18789, "health_url": "http://127.0.0.1:18789/health"},
    {"name": "Mission Control", "port": 3000, "health_url": "http://127.0.0.1:3000/health"},
    {"name": "Hermes Gateway", "port": 8642, "process": "hermes"},
    {"name": "Godmode API", "port": 7860, "process": "godmode"},
    {"name": "Agent Memory Server", "process": "agent-memory-server",
     "log": str(BASE / "logs" / "agent-memory-server.log")},
]

CONFIGS = [
    {
        "path": str(BASE / "openclaw.json"),
        "required_keys": ["meta", "env", "agents", "tools", "hooks", "session",
                          "channels", "gateway", "plugins"],
    },
    {
        "path": str(BASE / "cron" / "jobs.json"),
        "check": "valid_json",
    },
    {
        "path": str(Path.home() / ".mcp.json"),
        "required_keys": ["agent-memory", "task-dispatcher", "godmode"],
    },
]

DISK_FREE_MIN_GB = 10
LOG_DIR = BASE / "logs"
LOG_SIZE_MAX_MB = 500
HERMES_WAL_PATH = Path.home() / "hermes" / "state.db-wal"
HERMES_WAL_MAX_GB = 5

LEAD_PIPELINE_DIR = BASE / "workspace" / "lead_pipeline" / "daily_leads"
MEMECOIN_SCAN = BASE / "workspace" / "memecoin_strategy" / "scan_results.json"

CRON_RUNS_DIR = BASE / "cron" / "runs"
CRON_JOBS_FILE = BASE / "cron" / "jobs.json"

# ---------------------------------------------------------------------------
# State management (alert cooldown)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def should_alert(check_name: str, cooldown_minutes: int = ALERT_COOLDOWN_MINUTES) -> bool:
    """Returns True if we haven't alerted for this check recently."""
    state = _load_state()
    last = state.get(check_name)
    if last is None:
        return True
    try:
        last_ts = datetime.fromisoformat(last)
        return datetime.now() - last_ts > timedelta(minutes=cooldown_minutes)
    except Exception:
        return True


def record_alert(check_name: str):
    """Record that we just alerted for this check."""
    state = _load_state()
    state[check_name] = datetime.now().isoformat()
    _save_state(state)


def clear_alert(check_name: str):
    """Clear a previously recorded alert (issue resolved)."""
    state = _load_state()
    if check_name in state:
        del state[check_name]
        _save_state(state)

# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

def check_port(port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def check_health_url(url: str, timeout: float = 5.0) -> bool:
    """HTTP GET to a health endpoint; any 2xx is healthy."""
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return 200 <= resp.status < 300
    except Exception:
        return False


def check_process_running(name: str) -> bool:
    """Check if a process matching `name` is running (pgrep)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", name],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_disk_free_gb() -> float:
    """Return free disk space in GB for the root volume."""
    try:
        st = os.statvfs("/")
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except Exception:
        return -1


def file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 ** 2)
    except Exception:
        return 0


def file_size_gb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 ** 3)
    except Exception:
        return 0


def file_age_hours(path: Path) -> float:
    """Hours since last modification."""
    try:
        return (time.time() - path.stat().st_mtime) / 3600
    except Exception:
        return float("inf")

# ---------------------------------------------------------------------------
# Individual check functions — each returns (ok: bool, detail: str)
# ---------------------------------------------------------------------------

def check_services() -> list:
    """Check each service: process running, port open, health endpoint."""
    results = []
    for svc in SERVICES:
        name = svc["name"]
        issues = []

        # Process check
        proc = svc.get("process")
        if proc and not check_process_running(proc):
            issues.append(f"process '{proc}' not found")

        # Port check
        port = svc.get("port")
        if port and not check_port(port):
            issues.append(f"port {port} not responding")

        # Health URL check
        url = svc.get("health_url")
        if url and not issues:  # skip HTTP if port is already down
            if not check_health_url(url):
                issues.append(f"health endpoint {url} failed")

        ok = len(issues) == 0
        detail = f"{name}: " + (", ".join(issues) if issues else "OK")
        results.append(("service:" + name, ok, detail, "CRITICAL" if not ok else "INFO"))
    return results


def check_configs() -> list:
    results = []
    for cfg in CONFIGS:
        path = cfg["path"]
        name = f"config:{os.path.basename(path)}"
        try:
            data = json.loads(Path(path).read_text())
        except FileNotFoundError:
            results.append((name, False, f"{path}: file not found", "CRITICAL"))
            continue
        except json.JSONDecodeError as e:
            results.append((name, False, f"{path}: invalid JSON — {e}", "CRITICAL"))
            continue

        required = cfg.get("required_keys", [])
        if required:
            missing = [k for k in required if k not in data]
            if missing:
                results.append((name, False,
                    f"{path}: missing keys: {', '.join(missing)}", "WARNING"))
                continue

        results.append((name, True, f"{path}: valid", "INFO"))
    return results


def check_cron_jobs() -> list:
    """Check cron job freshness and exit codes."""
    results = []

    # Load job definitions for schedule info
    try:
        jobs_data = json.loads(CRON_JOBS_FILE.read_text())
        jobs = {j["id"]: j for j in jobs_data.get("jobs", [])}
    except Exception:
        jobs = {}

    if not CRON_RUNS_DIR.is_dir():
        results.append(("cron:runs_dir", False,
            "Cron runs directory not found", "WARNING"))
        return results

    for run_dir in sorted(CRON_RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            # Could be a .jsonl log file — check those too
            if run_dir.suffix == ".jsonl":
                job_id = run_dir.stem
                job_name = jobs.get(job_id, {}).get("name", job_id[:12])
                check_name = f"cron:{job_id[:12]}"
                try:
                    lines = run_dir.read_text().strip().split("\n")
                    if lines:
                        last_entry = json.loads(lines[-1])
                        status = last_entry.get("status", "unknown")
                        ts = last_entry.get("timestamp", last_entry.get("ts", ""))
                        if status not in ("ok", "success", "completed"):
                            results.append((check_name, False,
                                f"Cron '{job_name}': last status={status}", "WARNING"))
                        else:
                            results.append((check_name, True,
                                f"Cron '{job_name}': OK", "INFO"))
                except Exception:
                    pass
            continue

    # Also check job state from jobs.json itself
    for job_id, job in jobs.items():
        job_name = job.get("name", job_id[:12])
        check_name = f"cron:state:{job_id[:12]}"
        state = job.get("state", {})
        enabled = job.get("enabled", False)
        if not enabled:
            continue

        last_run_ms = state.get("lastRunAtMs", 0)
        last_status = state.get("lastRunStatus", state.get("lastStatus", "unknown"))
        consec_errors = state.get("consecutiveErrors", 0)

        if consec_errors >= 3:
            results.append((check_name, False,
                f"Cron '{job_name}': {consec_errors} consecutive errors", "CRITICAL"))
        elif last_status not in ("ok", "success"):
            results.append((check_name, False,
                f"Cron '{job_name}': lastStatus={last_status}", "WARNING"))
        else:
            # Check staleness: has it run in a reasonable window?
            if last_run_ms > 0:
                hours_ago = (time.time() * 1000 - last_run_ms) / 3_600_000
                if hours_ago > 48:
                    results.append((check_name, False,
                        f"Cron '{job_name}': last ran {hours_ago:.0f}h ago", "WARNING"))
                else:
                    results.append((check_name, True,
                        f"Cron '{job_name}': OK ({hours_ago:.1f}h ago)", "INFO"))
            else:
                results.append((check_name, True,
                    f"Cron '{job_name}': never run yet", "INFO"))

    return results


def check_resources() -> list:
    results = []

    # Disk space
    free_gb = get_disk_free_gb()
    check_name = "resource:disk"
    if free_gb >= 0 and free_gb < DISK_FREE_MIN_GB:
        results.append((check_name, False,
            f"Low disk space: {free_gb:.1f}GB free (min {DISK_FREE_MIN_GB}GB)", "CRITICAL"))
    else:
        results.append((check_name, True,
            f"Disk: {free_gb:.1f}GB free", "INFO"))

    # Large log files
    if LOG_DIR.is_dir():
        for logfile in LOG_DIR.iterdir():
            if logfile.is_file():
                size = file_size_mb(logfile)
                if size > LOG_SIZE_MAX_MB:
                    cname = f"resource:log:{logfile.name}"
                    results.append((cname, False,
                        f"Log {logfile.name} is {size:.0f}MB (max {LOG_SIZE_MAX_MB}MB)",
                        "WARNING"))

    # Hermes WAL file
    # Check multiple possible locations
    wal_paths = [
        HERMES_WAL_PATH,
        Path.home() / ".hermes" / "state.db-wal",
        BASE / "data" / "hermes" / "state.db-wal",
    ]
    for wal in wal_paths:
        if wal.exists():
            size = file_size_gb(wal)
            if size > HERMES_WAL_MAX_GB:
                results.append(("resource:hermes_wal", False,
                    f"Hermes WAL is {size:.1f}GB (max {HERMES_WAL_MAX_GB}GB)", "CRITICAL"))
            else:
                results.append(("resource:hermes_wal", True,
                    f"Hermes WAL: {size:.1f}GB", "INFO"))
            break

    return results


def check_data_pipelines() -> list:
    results = []

    # Today's leads CSV
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_csv = LEAD_PIPELINE_DIR / f"{today_str}.csv"
    cname = "pipeline:daily_leads"
    if today_csv.exists():
        results.append((cname, True, f"Daily leads CSV present ({today_str})", "INFO"))
    else:
        # Check if yesterday's exists (pipeline may not have run yet today)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_csv = LEAD_PIPELINE_DIR / f"{yesterday}.csv"
        if yesterday_csv.exists():
            results.append((cname, True,
                f"Today's leads CSV not yet present; yesterday's exists", "INFO"))
        else:
            results.append((cname, False,
                f"No leads CSV for today ({today_str}) or yesterday", "WARNING"))

    # Memecoin scan freshness
    cname = "pipeline:memecoin_scan"
    if MEMECOIN_SCAN.exists():
        age_h = file_age_hours(MEMECOIN_SCAN)
        if age_h > 24:
            results.append((cname, False,
                f"Memecoin scan is {age_h:.0f}h old (>24h stale)", "WARNING"))
        else:
            results.append((cname, True,
                f"Memecoin scan: {age_h:.1f}h old", "INFO"))
    else:
        results.append((cname, False,
            f"Memecoin scan file not found", "WARNING"))

    return results

# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_all_checks() -> list:
    """Run all checks. Returns list of (check_name, ok, detail, severity)."""
    all_results = []
    all_results.extend(check_services())
    all_results.extend(check_configs())
    all_results.extend(check_cron_jobs())
    all_results.extend(check_resources())
    all_results.extend(check_data_pipelines())
    return all_results


def main():
    dry_run = "--dry" in sys.argv

    start = time.time()
    results = run_all_checks()
    elapsed = time.time() - start

    failures = [(name, ok, detail, sev) for name, ok, detail, sev in results if not ok]
    passes = [(name, ok, detail, sev) for name, ok, detail, sev in results if ok]

    # Print summary
    print(f"[watchdog] {len(results)} checks in {elapsed:.1f}s — "
          f"{len(passes)} OK, {len(failures)} FAILED")

    for name, ok, detail, sev in results:
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {detail}")

    if dry_run:
        print("\n[dry-run] Skipping Telegram alerts.")
        return

    if not failures:
        # All healthy — nothing to send
        return

    # Import telegram module (same directory)
    sys.path.insert(0, str(Path(__file__).parent))
    from telegram import send_alert

    # Group alerts by severity for a single message if multiple
    critical = [f for f in failures if f[3] == "CRITICAL"]
    warnings = [f for f in failures if f[3] == "WARNING"]

    # Send critical alerts immediately (with cooldown)
    for name, _, detail, sev in critical:
        if should_alert(name):
            sent = send_alert(detail, "CRITICAL")
            if sent:
                record_alert(name)
                print(f"  [ALERT] Sent CRITICAL: {name}")
            else:
                print(f"  [ALERT] Failed to send: {name}")
        else:
            print(f"  [COOLDOWN] Skipping {name} (recently alerted)")

    # Batch warnings into a single message
    warn_to_send = [(n, d) for n, _, d, _ in warnings if should_alert(n)]
    if warn_to_send:
        msg_lines = ["*Warnings detected:*\n"]
        for name, detail in warn_to_send:
            msg_lines.append(f"- {detail}")
        sent = send_alert("\n".join(msg_lines), "WARNING")
        if sent:
            for name, _ in warn_to_send:
                record_alert(name)
            print(f"  [ALERT] Sent {len(warn_to_send)} warnings")

    # Clear alerts for checks that are now passing
    state = _load_state()
    for name, ok, _, _ in passes:
        if name in state:
            clear_alert(name)


if __name__ == "__main__":
    main()
