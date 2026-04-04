#!/usr/bin/env bash
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog.plist 2>/dev/null
launchctl unload ~/Library/LaunchAgents/com.openclaw.watchdog-daily.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/com.openclaw.watchdog.plist
rm -f ~/Library/LaunchAgents/com.openclaw.watchdog-daily.plist
echo "✓ Watchdog uninstalled"
