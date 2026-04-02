---
name: deploy
description: One-command deployment — detect stack, build, ship, verify, report URL
level: 3
triggers:
  - deploy
  - ship it
  - push to prod
  - go live
user-invocable: true
pipeline:
  - deployer (build + ship) → monitor (verify)
---

# Deploy Skill

## Purpose
Deploy anything, anywhere, with one command. Detects the project type, builds it, ships it to the right target, and verifies it's live.

## When to Use
- "Deploy this to a sandbox"
- "Ship it"
- "Make this live"
- After a build is complete and needs to go somewhere

## Execution Policy
- **Default target**: Conway sandbox (fastest, zero config)
- **Override**: User can specify `--target docker|vps|vercel|cloudflare`
- **Always verify**: Deployment isn't done until health check passes
- **Always report**: Output the live URL

## Workflow

### Phase 1: Detect & Configure
1. Read project root — identify stack (package.json, requirements.txt, Cargo.toml, etc.)
2. Check for existing deploy config (Dockerfile, vercel.json, wrangler.toml)
3. Identify required env vars
4. Choose target: user preference > existing config > Conway sandbox (default)

### Phase 2: Build
1. Install dependencies
2. Run build command (if applicable)
3. Quick test: `npm test` / `pytest` / `cargo test` (skip if user says `--skip-tests`)
4. Package artifact

### Phase 3: Ship
Spawn `deployer` agent with:
- Project path
- Target environment
- Env vars
- Build artifact

### Phase 4: Verify
Spawn `monitor` agent (lightweight) to:
1. Poll health endpoint (max 60s)
2. Run smoke test on main endpoint
3. Report: URL, status, response time

### Phase 5: Report
```
✓ Deployed to [target]
  URL: https://...
  Health: passing (response: XXms)
  Rollback: [command]
```

## Quick Examples
```
/deploy                     → Conway sandbox (auto-detect everything)
/deploy --target docker     → Local Docker container
/deploy --target vps user@host → SSH deploy to VPS
/deploy --skip-tests        → Skip test step
```
