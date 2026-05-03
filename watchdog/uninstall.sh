#!/usr/bin/env bash
set -euo pipefail

if [ "$(uname -s)" = "Darwin" ]; then
    launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist 2>/dev/null || true
    launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog-daily.plist 2>/dev/null || true
    rm -f ~/Library/LaunchAgents/com.openclaw.watchdog.plist
    rm -f ~/Library/LaunchAgents/com.openclaw.watchdog-daily.plist
else
    TMP_CRON="$(mktemp)"
    crontab -l 2>/dev/null | grep -v 'watchdog.py' | grep -v 'daily_report.py' > "$TMP_CRON" || true
    crontab "$TMP_CRON"
    rm -f "$TMP_CRON"
fi

echo "✓ Watchdog uninstalled"
