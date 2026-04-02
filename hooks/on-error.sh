#!/usr/bin/env bash
# on-error.sh — Captures tool/command failures and writes diagnostic context to fabric
# Lifecycle: Wired to Stop hook (filters for error signals in response)
# Can also be wired to a custom ToolError event if the harness supports it.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FABRIC_DIR="${FABRIC_DIR:-$HOME/fabric}"
LOG_FILE="${REPO_DIR}/hooks.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] on-error: $*" >> "$LOG_FILE"; }

# Parse input JSON from stdin
INPUT=$(cat)
RESPONSE=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('response', '')[:5000])
" 2>/dev/null || echo "")

CWD=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('cwd', ''))
" 2>/dev/null || echo "$HOME")

SESSION_ID=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('session_id', ''))
" 2>/dev/null || echo "")

PROJECT=$(basename "$CWD")

# Gate 1: Check if response contains error signals
ERROR_SIGNALS=$(echo "$RESPONSE" | grep -ciE 'error|failed|exception|traceback|fatal|panic|ENOENT|EACCES|permission denied|segfault|core dump|cannot find|not found|undefined|TypeError|SyntaxError|ImportError|ModuleNotFoundError|ConnectionRefused|timeout' 2>/dev/null || echo "0")

if [ "$ERROR_SIGNALS" -lt 1 ]; then
    exit 0  # No errors detected, nothing to do
fi

# Gate 2: Filter out errors that were already resolved in the same response
RESOLVED_SIGNALS=$(echo "$RESPONSE" | grep -ciE 'fixed|resolved|now works|passes|succeeded|✓|✅|PASS' 2>/dev/null || echo "0")

if [ "$RESOLVED_SIGNALS" -ge "$ERROR_SIGNALS" ]; then
    log "Errors detected but appear resolved in same session. Skipping."
    exit 0  # Errors were resolved within the session
fi

# Extract error context
ERROR_CONTEXT=$(echo "$RESPONSE" | grep -iE 'error|failed|exception|traceback|fatal|panic|TypeError|SyntaxError|ImportError' | head -10)

# Classify error type
if echo "$ERROR_CONTEXT" | grep -qiE 'import|module.*not found|ModuleNotFoundError'; then
    ERROR_TYPE="import-error"
elif echo "$ERROR_CONTEXT" | grep -qiE 'type.*error|TypeError|undefined is not'; then
    ERROR_TYPE="type-error"
elif echo "$ERROR_CONTEXT" | grep -qiE 'syntax|SyntaxError|unexpected token'; then
    ERROR_TYPE="syntax-error"
elif echo "$ERROR_CONTEXT" | grep -qiE 'permission|EACCES|forbidden'; then
    ERROR_TYPE="permission-error"
elif echo "$ERROR_CONTEXT" | grep -qiE 'connection|timeout|ECONNREFUSED|network'; then
    ERROR_TYPE="network-error"
elif echo "$ERROR_CONTEXT" | grep -qiE 'config|invalid.*config|JSON.*parse'; then
    ERROR_TYPE="config-error"
else
    ERROR_TYPE="runtime-error"
fi

log "Error detected: type=$ERROR_TYPE, signals=$ERROR_SIGNALS, project=$PROJECT"

# Write to fabric via adapter
if [ -f "$REPO_DIR/hooks/fabric-adapter.sh" ]; then
    source "$REPO_DIR/hooks/fabric-adapter.sh"

    SUMMARY="[$ERROR_TYPE] $(echo "$ERROR_CONTEXT" | head -1 | cut -c1-80)"

    fabric_write \
        "jailbreak" \
        "cli" \
        "error" \
        "$ERROR_CONTEXT" \
        "hot" \
        "" \
        "$PROJECT" \
        "$SUMMARY" \
        ""

    log "Error written to fabric: $SUMMARY"
elif [ -f "$HOME/icarus-daedalus/fabric-adapter.sh" ]; then
    source "$HOME/icarus-daedalus/fabric-adapter.sh"

    SUMMARY="[$ERROR_TYPE] $(echo "$ERROR_CONTEXT" | head -1 | cut -c1-80)"

    fabric_write \
        "jailbreak" \
        "cli" \
        "error" \
        "$ERROR_CONTEXT" \
        "hot" \
        "" \
        "$PROJECT" \
        "$SUMMARY" \
        ""

    log "Error written to fabric: $SUMMARY"
else
    log "WARNING: fabric-adapter.sh not found. Error not persisted."
fi
