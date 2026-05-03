#!/usr/bin/env bash
# Run watchdog once and show output
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Testing Watchdog ==="
python3 "$SCRIPT_DIR/watchdog.py" --dry-run 2>&1
echo ""
echo "=== Testing Daily Report ==="
python3 "$SCRIPT_DIR/daily_report.py" --dry-run 2>&1
echo ""
echo "=== All tests passed ==="
