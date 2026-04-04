#!/usr/bin/env python3
"""
Ontology Compiler for OpenClaw.

Refreshes ontology files with current system data. Keeps the ontology alive
by re-scanning cron logs, configs, data freshness, and risk scores.

Usage:
    python3 compiler.py          # Refresh all ontology files (~10 seconds)
    python3 compiler.py --dry    # Show what would be updated, don't write
"""

import json
import os
import sys
import socket
import time
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).parent
OPENCLAW_DIR = Path(os.path.expanduser("~/.openclaw"))
NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    """Load JSON from a path, return None on failure."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def save_json(path, data):
    """Atomically write JSON to a file."""
    tmp = str(path) + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(tmp, str(path))
        return True
    except (OSError, PermissionError) as e:
        print(f"  [ERROR] Failed to write {path}: {e}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def check_port(port, host="127.0.0.1", timeout=1.0):
    """Return True if TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def file_age_hours(path):
    """Return file age in hours, or None."""
    try:
        mtime = os.path.getmtime(str(path))
        return round((time.time() - mtime) / 3600.0, 1)
    except (FileNotFoundError, OSError):
        return None


def check_json_valid(path):
    """Return True if file is valid JSON."""
    try:
        with open(path, "r") as f:
            json.load(f)
        return True
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# 1. Refresh Cron Health Timeline
# ---------------------------------------------------------------------------

def refresh_cron_health():
    """Re-scan cron run logs and update cron_health_timeline.json."""
    print("  [1/5] Refreshing cron health timeline...")

    existing = load_json(ONTOLOGY_DIR / "cron_health_timeline.json")
    if not existing:
        print("    Skipped: no existing cron_health_timeline.json to update")
        return False

    runs_dir = OPENCLAW_DIR / "cron" / "runs"
    if not runs_dir.exists():
        print(f"    Skipped: {runs_dir} not found")
        return False

    # Scan run files for latest job statuses
    job_stats = {}  # job_name -> {successes, errors, durations, last_run}

    run_files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]

    for rf in run_files:
        data = load_json(rf)
        if not data:
            continue

        runs = data if isinstance(data, list) else data.get("runs", [data])
        for run in runs:
            if not isinstance(run, dict):
                continue
            name = run.get("jobName", run.get("name", ""))
            if not name:
                continue

            if name not in job_stats:
                job_stats[name] = {"successes": 0, "errors": 0, "durations": [], "last_run": None}

            status = run.get("status", "")
            duration = run.get("durationSeconds", run.get("duration_seconds", 0))

            if status in ("completed", "success", "ok"):
                job_stats[name]["successes"] += 1
            elif status in ("error", "failed", "timeout"):
                job_stats[name]["errors"] += 1

            if duration and isinstance(duration, (int, float)):
                job_stats[name]["durations"].append(duration)

            ts = run.get("completedAt", run.get("timestamp", ""))
            if ts and (job_stats[name]["last_run"] is None or ts > job_stats[name]["last_run"]):
                job_stats[name]["last_run"] = ts

    # Update existing jobs with fresh stats where available
    updated_count = 0
    for job in existing.get("jobs", []):
        name = job.get("name", "")
        if name in job_stats:
            stats = job_stats[name]
            total = stats["successes"] + stats["errors"]
            if total > 0:
                new_error_rate = round(stats["errors"] / total, 2)
                old_error_rate = job.get("error_rate", 0)

                if new_error_rate > old_error_rate:
                    job["error_trend"] = "increasing"
                elif new_error_rate < old_error_rate:
                    job["error_trend"] = "decreasing"
                else:
                    job["error_trend"] = "stable"

                job["error_rate"] = new_error_rate
                job["total_runs"] = total

                if stats["durations"]:
                    new_avg = round(sum(stats["durations"]) / len(stats["durations"]), 1)
                    old_avg = job.get("avg_duration_seconds", new_avg)
                    if new_avg > old_avg * 1.1:
                        job["duration_trend"] = "increasing"
                    elif new_avg < old_avg * 0.9:
                        job["duration_trend"] = "decreasing"
                    else:
                        job["duration_trend"] = "stable"
                    job["avg_duration_seconds"] = new_avg

                # Recalculate health score: 10 * (1 - error_rate) adjusted by trend
                hs = round(10 * (1 - new_error_rate), 1)
                if job.get("error_trend") == "increasing":
                    hs = max(hs - 1.0, 1.0)
                if job.get("duration_trend") == "increasing":
                    hs = max(hs - 0.5, 1.0)
                job["health_score"] = round(hs, 1)

                updated_count += 1

    existing["generated_at"] = NOW.isoformat()
    existing["summary"]["avg_system_health"] = round(
        sum(j.get("health_score", 10) for j in existing.get("jobs", [])) / max(len(existing.get("jobs", [])), 1), 1
    )

    save_json(ONTOLOGY_DIR / "cron_health_timeline.json", existing)
    print(f"    Updated {updated_count} jobs from {len(run_files)} run files")
    return True


# ---------------------------------------------------------------------------
# 2. Refresh Config Drift
# ---------------------------------------------------------------------------

def refresh_config_drift():
    """Re-check config files and update config_drift.json."""
    print("  [2/5] Refreshing config drift analysis...")

    existing = load_json(ONTOLOGY_DIR / "config_drift.json")
    if not existing:
        print("    Skipped: no existing config_drift.json")
        return False

    for cfg in existing.get("configs", []):
        path = cfg.get("path", "")
        if not path:
            continue

        # Check current state
        exists = os.path.exists(path)
        valid = check_json_valid(path) if exists else False

        # Count backup files
        bak_count = 0
        p = Path(path)
        for bak in p.parent.glob(f"{p.name}.bak*"):
            bak_count += 1

        cfg["backup_count"] = bak_count

        # Check for drift by comparing mtime to last known time
        if exists:
            age_h = file_age_hours(path)
            if age_h is not None and age_h < 1:
                cfg["drift_detected"] = True
                cfg["notes"] = cfg.get("notes", "") + f" [compiler: modified {age_h}h ago]"

        # Compute file hash for comparison
        if exists:
            try:
                with open(path, "rb") as f:
                    cfg["_hash"] = hashlib.md5(f.read()).hexdigest()[:12]
            except (OSError, PermissionError):
                pass

    existing["analysis_timestamp"] = NOW.isoformat()
    save_json(ONTOLOGY_DIR / "config_drift.json", existing)
    print(f"    Checked {len(existing.get('configs', []))} configs")
    return True


# ---------------------------------------------------------------------------
# 3. Refresh Risk Scores
# ---------------------------------------------------------------------------

def refresh_risk_scores():
    """Re-score risks for all components, update risk_scores.json."""
    print("  [3/5] Refreshing risk scores...")

    existing = load_json(ONTOLOGY_DIR / "risk_scores.json")
    if not existing:
        print("    Skipped: no existing risk_scores.json")
        return False

    graph = load_json(ONTOLOGY_DIR / "dependency_graph.json")

    for comp in existing.get("components", []):
        cid = comp["id"]
        ctype = comp.get("type", "")

        # Service: check if port is up
        if ctype == "service":
            if graph:
                for node in graph.get("nodes", []):
                    if node["id"] == cid:
                        port = node.get("port")
                        if port:
                            up = check_port(port)
                            if up:
                                # Port is up, lower risk slightly
                                comp["risk_score"] = max(comp.get("risk_score", 50) - 5, 10)
                                if "currently up" not in str(comp.get("factors", [])):
                                    comp.setdefault("factors", []).append(f"[compiler] port {port} is UP")
                            else:
                                comp["risk_score"] = min(comp.get("risk_score", 50) + 10, 100)
                                if "currently down" not in str(comp.get("factors", [])):
                                    comp.setdefault("factors", []).append(f"[compiler] port {port} is DOWN")
                        break

        # Cron: check watchdog state for consecutive errors
        if ctype == "cron":
            watchdog_state = load_json(OPENCLAW_DIR / "watchdog" / "state.json")
            if watchdog_state:
                for job_key, job_state in watchdog_state.items():
                    if isinstance(job_state, dict):
                        consec = job_state.get("consecErrors", 0)
                        if consec >= 2:
                            # Check if this state matches our component
                            name_match = cid.replace("cron:", "").replace("-", " ").lower()
                            key_match = job_key.replace("-", " ").replace("_", " ").lower()
                            if name_match in key_match or key_match in name_match:
                                comp["risk_score"] = min(comp.get("risk_score", 50) + consec * 10, 100)
                                comp["trend"] = "worsening"

        # Infrastructure: check RAM
        if cid == "system:ram":
            try:
                import subprocess
                result = subprocess.run(
                    ["vm_stat"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    free_pages = 0
                    for line in lines:
                        if "Pages free" in line:
                            free_pages = int(line.split(":")[1].strip().rstrip("."))
                            break
                    free_mb = free_pages * 4096 / (1024 * 1024)
                    if free_mb < 200:
                        comp["risk_score"] = min(comp.get("risk_score", 50) + 10, 100)
                    elif free_mb > 500:
                        comp["risk_score"] = max(comp.get("risk_score", 50) - 5, 20)
            except Exception:
                pass

    # Recalculate system health
    scores = [c.get("risk_score", 50) for c in existing.get("components", [])]
    if scores:
        avg_risk = sum(scores) / len(scores)
        existing["system_health"] = round(100 - avg_risk)

    existing["timestamp"] = NOW.isoformat()
    save_json(ONTOLOGY_DIR / "risk_scores.json", existing)
    print(f"    Scored {len(existing.get('components', []))} components, system health: {existing.get('system_health', '?')}")
    return True


# ---------------------------------------------------------------------------
# 4. Refresh Data Freshness
# ---------------------------------------------------------------------------

def refresh_data_freshness():
    """Re-check data source freshness, update data_freshness.json."""
    print("  [4/5] Refreshing data freshness...")

    existing = load_json(ONTOLOGY_DIR / "data_freshness.json")
    if not existing:
        print("    Skipped: no existing data_freshness.json")
        return False

    fresh_count = 0
    stale_count = 0

    for src in existing.get("data_sources", []):
        path = src.get("path", "")
        if not path or path.startswith("http"):
            continue

        # Handle directory paths (strip filename info in parens)
        clean_path = path.split(" (")[0].strip()

        age = file_age_hours(clean_path)
        expected = src.get("expected_freshness_hours", 24)

        if age is not None:
            src["actual_age_hours"] = age
            if age <= expected:
                src["status"] = "fresh"
                fresh_count += 1
            else:
                src["status"] = "stale"
                stale_count += 1
        else:
            # File not found - check if it's a directory
            p = Path(clean_path)
            if p.is_dir():
                # Find newest file in dir
                files = sorted(p.glob("*"), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True)
                if files and files[0].is_file():
                    age = file_age_hours(str(files[0]))
                    if age is not None:
                        src["actual_age_hours"] = age
                        src["status"] = "fresh" if age <= expected else "stale"
                        if src["status"] == "fresh":
                            fresh_count += 1
                        else:
                            stale_count += 1
                        src["path"] = f"{clean_path} (latest: {files[0].name})"
                        continue
            src["status"] = "missing"
            stale_count += 1

    total = fresh_count + stale_count
    existing["generated_at"] = NOW.isoformat()
    existing["analysis_note"] = f"Age calculated relative to {NOW.strftime('%Y-%m-%d %H:%M')} UTC by compiler.py"
    existing["freshness_summary"] = {
        "total_sources": len(existing.get("data_sources", [])),
        "fresh": fresh_count,
        "stale": stale_count,
        "stale_sources_requiring_attention": [
            f"{Path(s.get('path', '')).name} ({s.get('actual_age_hours', '?')}h old)"
            for s in existing.get("data_sources", [])
            if s.get("status") == "stale"
        ],
    }

    save_json(ONTOLOGY_DIR / "data_freshness.json", existing)
    print(f"    {fresh_count} fresh, {stale_count} stale out of {total} sources")
    return True


# ---------------------------------------------------------------------------
# 5. Write Compilation Metadata
# ---------------------------------------------------------------------------

def write_meta(results):
    """Write compilation timestamp and results to meta.json."""
    print("  [5/5] Writing compilation metadata...")

    meta = {
        "last_compiled": NOW.isoformat(),
        "compiler_version": "1.0.0",
        "compilation_results": results,
        "ontology_files": {},
    }

    # Record each ontology file's mtime and size
    for f in sorted(ONTOLOGY_DIR.glob("*.json")):
        if f.name == "meta.json":
            continue
        try:
            stat = f.stat()
            meta["ontology_files"][f.name] = {
                "size_bytes": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        except OSError:
            meta["ontology_files"][f.name] = {"error": "stat failed"}

    save_json(ONTOLOGY_DIR / "meta.json", meta)
    print(f"    Wrote meta.json with {len(meta['ontology_files'])} ontology files tracked")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    dry = "--dry" in sys.argv
    print(f"Ontology Compiler - {NOW.isoformat()}")
    print(f"Ontology dir: {ONTOLOGY_DIR}")

    if dry:
        print("[DRY RUN] Showing what would be updated:\n")
        print("  1. cron_health_timeline.json - rescan cron/runs/*.json")
        print("  2. config_drift.json - recheck config files")
        print("  3. risk_scores.json - re-score all components")
        print("  4. data_freshness.json - recheck file ages")
        print("  5. meta.json - write compilation timestamp")
        return

    start = time.time()
    print("Compiling ontology...\n")

    results = {
        "cron_health": refresh_cron_health(),
        "config_drift": refresh_config_drift(),
        "risk_scores": refresh_risk_scores(),
        "data_freshness": refresh_data_freshness(),
    }

    write_meta(results)

    elapsed = round(time.time() - start, 1)
    succeeded = sum(1 for v in results.values() if v)
    print(f"\nCompilation complete: {succeeded}/{len(results)} refreshed in {elapsed}s")


if __name__ == "__main__":
    main()
