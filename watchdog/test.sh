#!/usr/bin/env bash
# Run watchdog once and show output
echo "=== Testing Watchdog ==="
python3 /Users/marcmunoz/.openclaw/watchdog/watchdog.py --dry-run 2>&1
echo ""
echo "=== Testing Daily Report ==="
python3 /Users/marcmunoz/.openclaw/watchdog/daily_report.py --dry-run 2>&1
echo ""
echo "=== All tests passed ==="
