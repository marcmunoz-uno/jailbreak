#!/usr/bin/env python3
"""
Daily Prediction Runner for OpenClaw.

Orchestrates the ontology compiler and predictor to produce a daily
prediction report. Designed to be added to the launchd schedule.

Usage:
    python3 daily_prediction.py           # Full compile + predict cycle
    python3 daily_prediction.py --skip-compile  # Predict only (skip ontology refresh)

Output:
    Writes latest_prediction.json to the ontology directory.
"""

import json
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ONTOLOGY_DIR = Path(__file__).parent
PREDICTOR = ONTOLOGY_DIR / "predictor.py"
COMPILER = ONTOLOGY_DIR / "compiler.py"
OUTPUT = ONTOLOGY_DIR / "latest_prediction.json"
NOW = datetime.now(timezone.utc)


def run_script(script_path, args=None, label="script"):
    """Run a Python script and return (success, output, elapsed)."""
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
            cwd=str(ONTOLOGY_DIR),
        )
        elapsed = round(time.time() - start, 1)

        if result.returncode != 0:
            print(f"  [{label}] FAILED (exit {result.returncode}, {elapsed}s)")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
            return False, result.stdout, elapsed

        print(f"  [{label}] OK ({elapsed}s)")
        return True, result.stdout, elapsed

    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        print(f"  [{label}] TIMEOUT after {elapsed}s")
        return False, "", elapsed
    except FileNotFoundError:
        print(f"  [{label}] Script not found: {script_path}")
        return False, "", 0


def main():
    skip_compile = "--skip-compile" in sys.argv
    print(f"Daily Prediction Runner - {NOW.isoformat()}")
    print(f"Output: {OUTPUT}\n")

    overall_start = time.time()
    compile_ok = True
    compile_elapsed = 0

    # Step 1: Run compiler to refresh ontology
    if not skip_compile:
        print("Step 1: Refreshing ontology via compiler.py...")
        compile_ok, compile_out, compile_elapsed = run_script(COMPILER, label="compiler")
        if compile_out:
            # Print compiler output indented
            for line in compile_out.strip().split("\n"):
                print(f"    {line}")
        print()
    else:
        print("Step 1: Skipped (--skip-compile)\n")

    # Step 2: Run predictor to generate predictions
    print("Step 2: Generating predictions via predictor.py...")
    predict_ok, predict_out, predict_elapsed = run_script(PREDICTOR, label="predictor")

    if not predict_ok or not predict_out.strip():
        print("\nFailed to generate predictions.")
        # Write a failure report
        failure_report = {
            "timestamp": NOW.isoformat(),
            "status": "failed",
            "compile_ok": compile_ok,
            "predict_ok": predict_ok,
            "error": "predictor produced no output",
        }
        with open(str(OUTPUT), "w") as f:
            json.dump(failure_report, f, indent=2)
        sys.exit(1)

    # Step 3: Parse and write the prediction report
    print("\nStep 3: Writing prediction report...")
    try:
        report = json.loads(predict_out)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse predictor output as JSON: {e}")
        print(f"  Raw output (first 500 chars): {predict_out[:500]}")
        sys.exit(1)

    # Enrich report with metadata
    report["_meta"] = {
        "generated_by": "daily_prediction.py",
        "compile_ok": compile_ok,
        "compile_elapsed_s": compile_elapsed,
        "predict_elapsed_s": predict_elapsed,
        "total_elapsed_s": round(time.time() - overall_start, 1),
    }

    with open(str(OUTPUT), "w") as f:
        json.dump(report, f, indent=2)

    total_elapsed = round(time.time() - overall_start, 1)

    # Print summary
    health = report.get("system_health", "?")
    n_pred = report.get("prediction_count", 0)
    n_risks = len([r for r in report.get("active_risks", []) if r.get("risk_score", 0) >= 60])

    print(f"\n  Report written to: {OUTPUT}")
    print(f"  System health: {health}/100")
    print(f"  Predictions: {n_pred}")
    print(f"  High-risk components: {n_risks}")
    print(f"  Total time: {total_elapsed}s")

    # Also print the one-line summary
    status = "HEALTHY" if health >= 75 else "DEGRADED" if health >= 50 else "CRITICAL"
    print(f"\n  [{status}] {health}/100 | {n_pred} predictions | {n_risks} high risks")


if __name__ == "__main__":
    main()
