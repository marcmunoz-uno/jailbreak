#!/usr/bin/env bash
# Installs the watchdog as a launchd service running every 5 minutes
# and the daily report as a separate service running at 8 AM

set -euo pipefail

WATCHDOG_DIR="/Users/marcmunoz/.openclaw/watchdog"
PLIST_DIR="$HOME/Library/LaunchAgents"

# Create log directory
mkdir -p "$WATCHDOG_DIR/logs"

# Create the 5-minute watchdog plist
cat > "$PLIST_DIR/com.openclaw.watchdog.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/marcmunoz/.openclaw/watchdog/watchdog.py</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>/Users/marcmunoz/.openclaw/watchdog/logs/watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/marcmunoz/.openclaw/watchdog/logs/watchdog.err.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST

# Create the daily report plist (runs at 8 AM)
cat > "$PLIST_DIR/com.openclaw.watchdog-daily.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.watchdog-daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/marcmunoz/.openclaw/watchdog/daily_report.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/marcmunoz/.openclaw/watchdog/logs/daily.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/marcmunoz/.openclaw/watchdog/logs/daily.err.log</string>
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
