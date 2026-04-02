---
name: nuke
description: Full rebuild — tear down broken service, scaffold fresh, migrate data, deploy, verify
level: 5
triggers:
  - nuke
  - rebuild from scratch
  - start over
  - scorched earth
user-invocable: true
pipeline:
  - architect (plan) → swarm (parallel rebuild) → deployer (ship) → monitor (verify)
---

# Nuke Skill

## Purpose
When something is so broken that fixing it costs more than rebuilding, nuke it and start fresh. This skill orchestrates a controlled teardown and parallel rebuild — preserving data and configuration while replacing the broken implementation.

## When to Use
- A service is unfixably tangled (tech debt beyond repair)
- Config corruption keeps recurring despite fixes
- Architecture fundamentally doesn't support needed features
- "I'd rather start over than keep patching this"

## Execution Policy
- **Preserve data** — ALWAYS back up databases, configs, and state before teardown
- **Preserve interfaces** — Keep the same API contracts, URLs, and integrations
- **Parallel rebuild** — Use swarm to rebuild components simultaneously
- **Verify before cutover** — New version must pass all checks before replacing old
- **Rollback ready** — Old version stays available until new version is confirmed working

## Workflow

### Phase 1: Audit & Backup (architect + explore)
1. Map everything the current service does (endpoints, cron jobs, integrations, data flows)
2. Back up all data (database dumps, config files, state files)
3. Document all interfaces (API contracts, webhook URLs, MCP tools)
4. Identify what to KEEP vs what to REPLACE

### Phase 2: Plan the Rebuild (architect)
1. Design the new architecture (fix the root issues)
2. Decompose into parallel work units
3. Define acceptance criteria: "new version must pass these tests"
4. Create a cutover plan (how to switch from old → new with zero downtime)

### Phase 3: Parallel Rebuild (swarm)
Spawn swarm with the rebuild plan:
- scaffolder: New project structure
- db-engineer: New schema + migration from old data
- executor ×N: Build components in parallel
- connector: Wire integrations
- test-engineer: Write acceptance tests

### Phase 4: Verify (verifier + monitor)
1. Run all acceptance tests
2. Load test data and verify correctness
3. Verify all integrations work (webhooks, MCP, API clients)
4. Verify performance is equal or better

### Phase 5: Cutover
1. Put old service in maintenance mode (or keep running for comparison)
2. Deploy new service alongside old
3. Switch traffic to new service
4. Monitor for 10 minutes
5. If stable → tear down old service
6. If problems → switch back to old service, diagnose

### Phase 6: Cleanup
1. Remove old service code/configs
2. Update documentation
3. Update monitoring to point at new service
4. Archive backup data (keep for 30 days)

## Stop Conditions
- New service passes all acceptance tests and is live → done
- New service fails acceptance tests → fix or abort (old service still running)
- User cancels during rebuild → clean up partial work, old service unaffected

## Safety Rails
- NEVER delete old service before new one is verified
- NEVER lose data — backup is mandatory before ANY teardown
- ALWAYS keep rollback path until new service is confirmed stable
- Document EVERYTHING — the nuke itself is a significant event worth recording
