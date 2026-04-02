#!/usr/bin/env bash
# on-stop.sh -- Claude Code Stop hook.
# Only writes to fabric when the session produced something worth remembering:
# decisions, code changes, fixes, handoffs. Skips greetings and Q&A.

set -euo pipefail

FABRIC_DIR="${FABRIC_DIR:-$HOME/fabric}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INPUT=$(cat)

# Don't loop on re-run
ACTIVE=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))" 2>/dev/null || echo "false")
[ "$ACTIVE" = "true" ] || [ "$ACTIVE" = "True" ] && exit 0

RESPONSE=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','')[:2000])" 2>/dev/null || echo "")
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('session_id','unknown'))" 2>/dev/null || echo "unknown")
CWD=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cwd',''))" 2>/dev/null || echo "")

# --- GATE 1: minimum length ---
[ ${#RESPONSE} -lt 200 ] && exit 0

# --- GATE 2: must contain a signal of real work ---
# Look for evidence of: tool use, code changes, decisions, fixes, handoffs, errors found
SIGNAL=$(echo "$RESPONSE" | grep -ciE \
    'created|edited|fixed|deployed|built|refactored|implemented|installed|configured|handoff|error|bug|commit|wrote|updated file|write tool|edit tool|changed.*to|moved.*to|deleted|removed' \
    2>/dev/null || echo "0")
[ "$SIGNAL" -lt 1 ] && exit 0

# --- GATE 3: skip if it's just explaining/answering ---
EXPLAIN_ONLY=$(echo "$RESPONSE" | grep -ciE \
    '^(here|the|this|that|it|you|sure|yes|no|ok|basically|essentially|in summary)' \
    2>/dev/null || echo "0")
# If high explain ratio and low signal, skip
[ "$EXPLAIN_ONLY" -gt 3 ] && [ "$SIGNAL" -lt 2 ] && exit 0

# Determine entry type from content
TYPE="session"
echo "$RESPONSE" | grep -qiE 'decided|will do|plan is|committed to|conclusion' && TYPE="decision"
echo "$RESPONSE" | grep -qiE 'fixed|resolved|bug|error.*fixed|patched' && TYPE="resolution"
echo "$RESPONSE" | grep -qiE 'handoff|needs.*attention|action.needed|blocked.*by' && TYPE="handoff"

source "$SCRIPT_DIR/../fabric-adapter.sh"

PROJECT=$(basename "$CWD" 2>/dev/null || echo "unknown")

# Build a compact summary (first meaningful line, not a greeting)
SUMMARY=$(echo "$RESPONSE" | grep -iE 'created|edited|fixed|built|deployed|implemented|configured|changed|updated|wrote|error|bug|commit|handoff' | head -1 | cut -c1-80)
[ -z "$SUMMARY" ] && SUMMARY="claude-code $TYPE in $PROJECT"

fabric_write \
    "claude-code" \
    "cli" \
    "$TYPE" \
    "$RESPONSE" \
    "hot" \
    "" \
    "$PROJECT" \
    "$SUMMARY" \
    "" > /dev/null 2>&1

exit 0
