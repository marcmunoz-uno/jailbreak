---
name: self-evolve
description: Analyze harness performance over time, propose and apply improvements to agents, skills, and hooks
level: 5
triggers:
  - evolve
  - self-improve
  - harness-audit
user-invocable: true
pipeline:
  - evolve (agent) → executor (apply changes) → verifier (confirm no regressions)
handoff: .omc/evolution-ledger.md
---

# Self-Evolve Skill

## Purpose
Systematically improve the harness by analyzing what's working, what's failing, and what's unused. This is NOT speculative improvement — every change must be backed by evidence from session history, fabric memory, or observable patterns.

## When to Use
- After a sprint of heavy usage (weekly recommended)
- When you notice repeated failures or escalation loops
- When user gives feedback about agent/skill behavior
- When new capabilities are needed based on project evolution

## Execution Policy
- **Mode**: Sequential (analyze → propose → apply → verify)
- **Max proposals per run**: 5
- **Evidence threshold**: Every proposal needs ≥2 supporting data points
- **Rollback**: Git commit before applying; revert if verification fails

## Workflow

### Phase 1: Evidence Collection (evolve agent, read-only)
Spawn `evolve` agent with:
```
Analyze the harness at ~/.jailbreak/ for the last 7 days:
1. Read fabric entries in ~/fabric/ — identify failure patterns, escalation loops, unused agents
2. Check .omc/state/ for mode failures (autopilot aborts, ralph stalls, ultraqa loops)
3. Grep agent definitions for constraints that are frequently violated
4. Check git log of ~/.jailbreak/ for recent changes and their effects
Produce an evolution report with max 5 proposals.
```

### Phase 2: Review & Gate
Present proposals to user. Each proposal shows:
- Target file + exact diff
- Evidence (with citations)
- Impact score (benefit vs disruption)
- Rollback instructions

**Gate**: User must approve proposals before Phase 3. If no approval, log proposals to evolution ledger as "proposed" and stop.

### Phase 3: Apply Changes (executor agent)
For each approved proposal:
1. `git stash` or commit current state (safety net)
2. Apply the diff via Edit tool
3. Run basic validation:
   - YAML frontmatter parses correctly
   - No broken skill chain references (grep for `next-skill`, `pipeline` fields)
   - No removed trigger keywords that other skills reference

### Phase 4: Verify (verifier agent)
For each applied change:
1. Check that modified files are valid (parse frontmatter, check structure)
2. Trace pipeline chains — ensure handoffs still work
3. If any verification fails: revert that specific change, mark as "reverted" in ledger

### Phase 5: Ledger Update
Append to `.omc/evolution-ledger.md`:
```markdown
## [DATE] Evolution Pass

| # | Proposal | Status | Target | Impact |
|---|----------|--------|--------|--------|
| 1 | [title]  | applied/reverted/rejected | path | B:X D:Y |
```

## Stop Conditions
- All proposals reviewed and actioned (applied, rejected, or reverted)
- Verification passes for all applied changes
- Ledger updated

## Examples

### Good: Evidence-backed minimal change
```
Proposal: Tighten debugger circuit breaker from 3 to 2 failures
Evidence: 8 of last 12 debugger sessions hit the 3-failure limit and escalated to architect, 
  but the 3rd attempt never succeeded — it just wasted a turn.
Change: In agents/debugger.md, change "3-failure circuit breaker" to "2-failure circuit breaker"
Impact: Benefit 3/5, Disruption 1/5
```

### Bad: Speculative rewrite
```
Proposal: Rewrite the entire critic agent to use chain-of-thought
Evidence: "It seems like it could be better"
→ REJECTED: No evidence, massive disruption, vague benefit
```
