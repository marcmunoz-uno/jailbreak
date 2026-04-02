#!/usr/bin/env bash
#
# config_healthcheck.sh - Watchdog for openclaw.json integrity
#
# Checks:
#   1. File exists and is readable
#   2. Valid JSON
#   3. Required top-level keys present
#   4. File permissions are restrictive (owner-only write)
#   5. Concurrent access detection (lsof)
#
# Exit codes: 0 = healthy, 1 = problem found
# Suitable for cron: */5 * * * * /Users/marcmunoz/.openclaw/config_healthcheck.sh >> /Users/marcmunoz/.openclaw/logs/healthcheck.log 2>&1

set -euo pipefail

CONFIG="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
REQUIRED_KEYS="meta env agents tools hooks session channels gateway plugins"
ISSUES=0
TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"

log() { echo "[$TIMESTAMP] $1"; }
fail() { log "FAIL: $1"; ISSUES=$((ISSUES + 1)); }
warn() { log "WARN: $1"; }
pass() { log "OK:   $1"; }

# 1. File exists and is readable
if [ ! -f "$CONFIG" ]; then
    fail "Config file missing: $CONFIG"
    exit 1
fi

if [ ! -r "$CONFIG" ]; then
    fail "Config file not readable: $CONFIG"
    exit 1
fi
pass "File exists and is readable"

# 2. Valid JSON
if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$CONFIG" 2>/dev/null; then
    fail "Invalid JSON in $CONFIG"
    # Attempt auto-recovery from backup
    BACKUP="$CONFIG.bak"
    if [ -f "$BACKUP" ] && python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$BACKUP" 2>/dev/null; then
        warn "Valid backup found at $BACKUP - restoring"
        cp "$BACKUP" "$CONFIG"
        pass "Restored from backup"
    else
        fail "No valid backup available for recovery"
    fi
    exit 1
fi
pass "Valid JSON"

# 3. Required keys
MISSING=""
for key in $REQUIRED_KEYS; do
    if ! python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
assert sys.argv[2] in d
" "$CONFIG" "$key" 2>/dev/null; then
        MISSING="$MISSING $key"
    fi
done

if [ -n "$MISSING" ]; then
    fail "Missing required keys:$MISSING"
else
    pass "All required keys present"
fi

# 4. File permissions
PERMS=$(stat -c '%a' "$CONFIG" 2>/dev/null || stat -f '%A' "$CONFIG" 2>/dev/null)
case "$PERMS" in
    600|640|644)
        pass "Permissions: $PERMS"
        ;;
    *)
        if [ "${PERMS:1:1}" != "0" ] 2>/dev/null || [ "${PERMS:2:1}" != "0" ] 2>/dev/null; then
            warn "Permissions may be too open: $PERMS (consider 600)"
        else
            pass "Permissions: $PERMS"
        fi
        ;;
esac

# 5. Concurrent access check
WRITERS=$(lsof "$CONFIG" 2>/dev/null | grep -c '[wW]' || true)
if [ "$WRITERS" -gt 1 ]; then
    warn "Multiple processes have config open for writing ($WRITERS)"
    lsof "$CONFIG" 2>/dev/null | head -10
else
    pass "No concurrent write contention"
fi

# Summary
if [ "$ISSUES" -gt 0 ]; then
    log "Health check completed with $ISSUES issue(s)"
    exit 1
fi
log "Health check passed - all clear"
exit 0
