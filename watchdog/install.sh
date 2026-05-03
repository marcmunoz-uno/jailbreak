#!/usr/bin/env bash
# Installs the watchdog scheduler.
# macOS uses launchd; Linux falls back to user crontab entries.

set -euo pipefail

WATCHDOG_DIR="${OPENCLAW_BASE:-$HOME/.openclaw}/watchdog"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

# Create log directory
mkdir -p "$WATCHDOG_DIR/logs"

if [ "$OS" = "Darwin" ]; then
PLIST_DIR="$HOME/Library/LaunchAgents"

# Create the 5-minute watchdog plist
cat > "$PLIST_DIR/com.openclaw.watchdog.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DIR}/watchdog.py</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>${WATCHDOG_DIR}/logs/watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>${WATCHDOG_DIR}/logs/watchdog.err.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST

# Create the daily report plist (runs at 8 AM)
cat > "$PLIST_DIR/com.openclaw.watchdog-daily.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.watchdog-daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DIR}/daily_report.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${WATCHDOG_DIR}/logs/daily.log</string>
    <key>StandardErrorPath</key>
    <string>${WATCHDOG_DIR}/logs/daily.err.log</string>
</dict>
</plist>
PLIST

# Load the services
launchctl unload "$PLIST_DIR/com.openclaw.watchdog.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.openclaw.watchdog.plist"

launchctl unload "$PLIST_DIR/com.openclaw.watchdog-daily.plist" 2>/dev/null || true
launchctl load "$PLIST_DIR/com.openclaw.watchdog-daily.plist"

echo "✓ Watchdog installed and running (every 5 min)"
echo "✓ Daily report scheduled (8 AM daily)"
echo "  Logs: $WATCHDOG_DIR/logs/"
echo "  To check status: launchctl list | grep watchdog"
echo "  To stop: launchctl unload $PLIST_DIR/com.openclaw.watchdog.plist"
else
    WATCHDOG_CMD="*/5 * * * * OPENCLAW_BASE=${OPENCLAW_BASE:-$HOME/.openclaw} /usr/bin/python3 ${SCRIPT_DIR}/watchdog.py >> ${WATCHDOG_DIR}/logs/watchdog.log 2>> ${WATCHDOG_DIR}/logs/watchdog.err.log"
    DAILY_CMD="0 8 * * * OPENCLAW_BASE=${OPENCLAW_BASE:-$HOME/.openclaw} /usr/bin/python3 ${SCRIPT_DIR}/daily_report.py >> ${WATCHDOG_DIR}/logs/daily.log 2>> ${WATCHDOG_DIR}/logs/daily.err.log"
    TMP_CRON="$(mktemp)"

    crontab -l 2>/dev/null | grep -v 'watchdog.py' | grep -v 'daily_report.py' > "$TMP_CRON" || true
    {
        echo "$WATCHDOG_CMD"
        echo "$DAILY_CMD"
    } >> "$TMP_CRON"
    crontab "$TMP_CRON"
    rm -f "$TMP_CRON"

    echo "✓ Watchdog installed via user crontab"
    echo "✓ Daily report scheduled via user crontab"
    echo "  Logs: $WATCHDOG_DIR/logs/"
    echo "  To check status: crontab -l | grep openclaw"
fi
