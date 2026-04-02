---
name: incident
description: Production incident response — triage, diagnose, fix, restore, document
level: 4
triggers:
  - incident
  - production down
  - service down
  - on fire
  - everything is broken
user-invocable: true
pipeline:
  - firefighter (triage + fix) → monitor (verify recovery) → architect (permanent fix plan)
---

# Incident Skill

## Purpose
When something is down in production, this skill coordinates a rapid response: triage the severity, diagnose the root cause, apply the fastest safe fix, verify recovery, and document everything.

## When to Use
- "The API is down"
- "Cron jobs are failing"
- "Users are seeing errors"
- "The config is broken again" (looking at you, openclaw.json)
- Any production service degradation

## Execution Policy
- **Speed over elegance** — Restore service first, clean up later
- **Communicate** — Send status updates to Telegram if available
- **Document as you go** — Timeline is critical for post-mortems
- **Escalate if stuck** — If firefighter can't fix in 10 min, bring in architect

## Workflow

### Phase 1: Triage (< 1 minute)
Spawn `firefighter` agent:
1. What's the symptom?
2. What's the blast radius?
3. When did it start?
4. What changed recently? (git log, deploy history, config changes)
5. Classify: SEV1 (down) / SEV2 (degraded) / SEV3 (non-critical) / SEV4 (warning)

### Phase 2: Diagnose (< 5 minutes for SEV1-2)
Firefighter continues:
1. Check logs for errors
2. Check processes (running? crashed? zombie?)
3. Check resources (disk, memory, CPU, connections)
4. Check dependencies (DB, APIs, DNS)
5. Check config files (valid? corrupted? permissions?)
6. Identify root cause or best hypothesis

### Phase 3: Fix
Apply the fastest safe fix:
- Bad deploy → rollback
- Config corruption → restore from backup
- Process crashed → restart
- Resource exhaustion → clear + restart
- Dependency down → failover/cache

### Phase 4: Verify Recovery
Spawn `monitor` agent:
1. Health check passes
2. Core functionality works
3. No cascading failures
4. Dependent services recovered

### Phase 5: Document
Write incident report:
```markdown
## Incident: [TITLE]
- **Severity**: SEV[X]
- **Duration**: [X minutes]
- **Root cause**: [one sentence]
- **Fix**: [what was done]
- **Needs permanent fix**: [yes/no]
- **Timeline**: [timestamped events]
```

### Phase 6: Permanent Fix (if needed)
If the fix was a bandaid:
- Spawn `architect` to design proper fix
- Create a task for the proper fix
- Document in evolution ledger

## Stop Conditions
- Service restored and verified → document and done
- Can't diagnose in 15 minutes → escalate to user with full diagnostic context
- Fix applied but side effects detected → keep firefighter engaged until stable
