#!/usr/bin/env bash
# pre-commit.sh — Smart commit message suggestion from fabric context
# Lifecycle: Can be wired to a PreToolCall hook matching git commit,
# or called manually before committing.
#
# Usage: echo '{"cwd":"/path/to/repo"}' | ./pre-commit.sh
# Output: Suggested commit message based on diff + fabric context

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FABRIC_DIR="${FABRIC_DIR:-$HOME/fabric}"
LOG_FILE="${REPO_DIR}/hooks.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] pre-commit: $*" >> "$LOG_FILE"; }

# Parse input
INPUT=$(cat 2>/dev/null || echo '{}')
CWD=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('cwd', ''))
" 2>/dev/null || pwd)

cd "$CWD" 2>/dev/null || exit 0

# Gate: Must be a git repo with staged changes
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    exit 0
fi

STAGED=$(git diff --cached --stat 2>/dev/null)
if [ -z "$STAGED" ]; then
    exit 0  # Nothing staged
fi

PROJECT=$(basename "$(git rev-parse --show-toplevel)")

# Get the actual diff (limited to avoid huge diffs)
DIFF=$(git diff --cached --no-color 2>/dev/null | head -200)

# Get recent commit style (for format matching)
RECENT_STYLE=$(git log --oneline -5 2>/dev/null || echo "")

# Check fabric for recent decisions/context about this project
FABRIC_CONTEXT=""
if [ -d "$FABRIC_DIR" ]; then
    FABRIC_CONTEXT=$(grep -rl "$PROJECT" "$FABRIC_DIR" --include="*.md" 2>/dev/null | \
        sort -t'-' -k3 -r | head -3 | while read f; do
            grep -E "^(summary:|type:)" "$f" 2>/dev/null | head -2
        done)
fi

# Output context for commit message generation
cat <<EOF
## Pre-Commit Context

### Staged Changes
\`\`\`
$STAGED
\`\`\`

### Diff Summary
\`\`\`diff
$(echo "$DIFF" | head -100)
\`\`\`

### Recent Commit Style
\`\`\`
$RECENT_STYLE
\`\`\`

### Related Fabric Context
$FABRIC_CONTEXT

### Suggestion
Based on the staged changes, match the project's commit message style shown above.
EOF

log "Pre-commit context generated for $PROJECT ($(echo "$STAGED" | wc -l) files staged)"
