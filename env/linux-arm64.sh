#!/usr/bin/env bash
# Source this on Linux ARM hosts before using Git or the OpenClaw/Jailbreak hooks.

OPENCLAW_BASE="${OPENCLAW_BASE:-$HOME/.openclaw}"
WORKFLOWS_DIR="${WORKFLOWS_DIR:-$HOME/n8n-workflows}"
FABRIC_DIR="${FABRIC_DIR:-$HOME/fabric}"

if [ -x /snap/codex/35/usr/bin/git ] && [ -d /snap/codex/35/usr/lib/git-core ]; then
    export GIT_EXEC_PATH="${GIT_EXEC_PATH:-/snap/codex/35/usr/lib/git-core}"
    export GIT_TEMPLATE_DIR="${GIT_TEMPLATE_DIR:-/snap/codex/35/usr/share/git-core/templates}"
fi

export OPENCLAW_BASE
export WORKFLOWS_DIR
export FABRIC_DIR
