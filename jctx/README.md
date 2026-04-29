# jctx — Jailbreak Context Overlay

Additive context cold-storage, search, and Marc-stack indexing for Jailbreak.

JCTX is intentionally an overlay, not a foundation change. It does not modify Jailbreak startup hooks, MCP routing, model config, permissions, or core harness behavior. Use it when raw tool output would be too large for the conversation context.

## What it provides

- Store large files, command outputs, URLs, and pasted text outside the model context.
- Index artifacts with SQLite FTS5 for fast local search.
- Return compact summaries/search hits instead of dumping full raw output.
- Collect Marc-stack context from fabric handoffs, Jailbreak artifacts, OpenClaw logs, Obsidian bootstrap notes, and System Brain snapshots when those sources exist locally.

## Usage

From the repository root:

```bash
bun jctx/jctx.ts doctor
bun jctx/jctx.ts index README.md --tags repo,docs
bun jctx/jctx.ts add --title "large paste" < /tmp/output.txt
bun jctx/jctx.ts run -- git status --short
bun jctx/jctx.ts search "OpenClaw failure" --limit 5
bun jctx/jctx.ts show 1
bun jctx/jctx.ts stats
bun jctx/jctx.ts collect marc --limit 25
```

Optional shell aliases:

```bash
alias jctx='bun /Users/marcmunoz/free-code/jctx/jctx.ts'
alias speculate='bun /Users/marcmunoz/free-code/jctx/speculate.ts'
alias jailbreak-os='bun /Users/marcmunoz/free-code/jctx/jailbreak-os.ts'
```

Or symlink the shims in `jctx/bin/` onto your PATH.

## Agent-OS overlays

### Speculative execution worktrees

```bash
speculate start "improve context compaction" --repo /Users/marcmunoz/free-code
speculate list
speculate show <slug>
speculate cleanup <slug> --yes
```

Default mode creates isolated worktrees plus `JCTX_SPECULATION.md` instructions. Add `--execute '<command>'` to run a command in each variant.

### Context-aware tool router

```bash
jailbreak-os route "read a 200KB log and find failures" --bytes 200000
```

Returns a routing recommendation and records it in JCTX.

### Live blackboard

```bash
jailbreak-os board add --agent explorer --task "Map auth flow"
jailbreak-os board list
jailbreak-os board update 1 --status done --evidence "Found entrypoint in src/auth.ts"
```

### Verification-first mode

```bash
jailbreak-os verify create "fix login regression"
jailbreak-os verify evidence 1 "bun test auth passed"
jailbreak-os verify list
```

### Skill miner

```bash
jailbreak-os skill mine --name "County portal replay" --trigger "county portal replay" --from 12
jailbreak-os skill list
```

Draft skills are written to `~/.jailbreak/jctx/skills/` for review before promotion.

### Agent immune system

```bash
jailbreak-os immune scan --recent 100
```

Flags repeated errors, huge artifacts, and possible sensitive-context metadata.

## Storage

Default location:

```text
~/.jailbreak/jctx/jctx.sqlite
~/.jailbreak/jctx/artifacts/
```

Override with:

```bash
JCTX_HOME=/path/to/store bun jctx/jctx.ts stats
```

## Design constraints

- Additive only: no global hooks or config edits.
- Local first: SQLite + artifact files under `~/.jailbreak/jctx`.
- Explicit collection: Marc-stack sources are indexed only when `jctx collect marc` is run.
- Safe summaries: full content remains available via `jctx show <id>`.

## Branch description

**Jailbreak with JCTX - Jailbreak Context Overlay** adds an opt-in context sidecar for cold-storing bulky outputs and searching Marc-stack context without changing the core Jailbreak harness foundation.
