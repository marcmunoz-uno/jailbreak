---
name: ender
description: Spawn recursive agent armies — swarms that spawn swarms, sandbox armadas, full lifecycle assault
level: 5
triggers:
  - ender
  - army
  - swarm
  - send the fleet
  - all agents
user-invocable: true
pipeline:
  - ender (command) → fleets × N (execute) → sandbox-armada (verify) → deployer (ship)
aliases:
  - swarm
---

# Ender — Recursive Swarm Command

## Purpose
Take any mission and throw an army at it. Ender decomposes the mission into fleets, fleets into squads, squads into soldiers. Swarms spawn swarms. Every agent in the harness is a weapon Ender can deploy.

## When to Use
- Any task too large for a single agent
- "Build and deploy a complete service"
- "Fix everything that's broken"
- "Test this across every possible scenario"
- "I want 20 sandboxes running in parallel"
- When you want maximum aggression and parallelism

## The Arsenal (30 agents available)

### Strike Agents (build things)
`executor` `api-builder` `db-engineer` `scaffolder` `designer` `pipeline-builder`

### Ops Agents (ship and fix things)
`deployer` `firefighter` `connector` `monitor`

### Intel Agents (understand things)
`explore` `architect` `analyst` `scientist` `tracer` `integrator` `document-specialist`

### Quality Agents (verify things)
`code-reviewer` `security-reviewer` `test-engineer` `qa-tester` `verifier` `critic`

### Support Agents (enable things)
`debugger` `code-simplifier` `git-master` `writer` `planner` `evolve`

## Execution Policy
- **Maximize parallelism** — If two tasks don't depend on each other, they run simultaneously
- **Recursive command** — Ender can spawn sub-Enders as fleet commanders (sonnet model)
- **Sandbox everything** — Before shipping, the sandbox armada validates in 15-20 isolated environments
- **Background execution** — All fleets run in background (`run_in_background: true`)
- **Worktree isolation** — All code-writing agents get their own worktree
- **Max depth**: 3 levels (Ender → Fleet → Squad)
- **Max agents**: 50 total across all levels

## Workflow

### Phase 1: Mission Briefing
Ender reads the full mission and produces a battle plan:

```markdown
## Battle Plan: [MISSION NAME]

### Objective
[What must exist when we're done]

### Fleets
1. Fleet Alpha (Build): [what it builds, which agents]
2. Fleet Beta (Test): [what it tests, which agents]
3. Fleet Gamma (Deploy): [where it ships, which agents]
4. Sandbox Armada: [how many sandboxes, which scenarios]

### Dependencies
Alpha must finish before Beta starts.
Beta and Gamma can run in parallel after Alpha.
Sandbox Armada runs after Gamma.

### Estimated Agent Count: [N]
```

### Phase 2: Fleet Launch
For each fleet, Ender spawns a background agent:

```
# Simple fleet (single agent type, no sub-decomposition needed)
Agent(
  prompt="You are Fleet Commander Alpha. Build [X]. Use executor agents.",
  model=sonnet,
  run_in_background=true,
  isolation=worktree  # if writing code
)

# Complex fleet (needs its own decomposition)
Agent(
  prompt="You are Fleet Commander Beta. You are a sub-Ender. "
         "Decompose this into squads and execute in parallel: [task]. "
         "Available agents: [roster]. Report results.",
  model=sonnet,
  run_in_background=true
)

# Sandbox armada fleet
Agent(
  prompt="You are the Sandbox Armada Commander. "
         "Create 20 Conway sandboxes via mcp__conway__sandbox_create. "
         "Deploy [artifact] to each. Run these scenarios: [list]. "
         "Report pass/fail for each. Delete sandboxes when done.",
  model=sonnet,
  run_in_background=true
)
```

### Phase 3: Monitor & Reinforce
As fleets report back:
- **Fleet succeeds** → Log result, check if dependent fleets can launch
- **Fleet fails** → Diagnose. Either:
  - Reinforce: spawn additional agents to help
  - Reassign: kill fleet, try different approach
  - Escalate: report to user if truly stuck
- **Fleet silent > 5 min** → Spawn duplicate fleet, race condition is fine

### Phase 4: Sandbox Armada
After build + deploy fleets complete, launch the armada:

1. Spawn armada commander (sonnet) in background
2. Armada commander creates 15-20 sandboxes via Conway MCP tools
3. Each sandbox gets the built artifact deployed
4. Each sandbox runs a unique test scenario:
   - Functional: happy path, edge cases, error handling, auth
   - Infrastructure: cold start, dependency failure, resource limits
   - Integration: webhooks, MCP tools, cross-service calls
   - Chaos: kill mid-request, corrupt config, rapid restart
5. Results aggregate: X/20 pass → verdict

**Pass thresholds:**
- 20/20 → SHIP IT with confidence
- 16-19/20 → SHIP IT but fix failures next
- 11-15/20 → FIX FIRST, do not ship
- ≤10/20 → ABORT, fundamental issues

### Phase 5: Victory or Retreat
```markdown
## Mission Report: [NAME]

### Result: [COMPLETE / PARTIAL / FAILED]

### Fleets
| Fleet | Agents | Duration | Status |
|-------|--------|----------|--------|
| Alpha Build | 8 | 2m | ✓ |
| Beta Test | 5 | 1m | ✓ |
| Sandbox Armada | 20 | 3m | 18/20 ✓ |
| Gamma Deploy | 2 | 45s | ✓ |

### Sandbox Results: 18/20 PASS
[detailed results table]

### Verdict: SHIPPED
URL: https://...
```

## Swarm Patterns

### The Blitz (max speed)
Everything in parallel, merge at the end.
```
Ender → 10 agents simultaneously → merge → ship
```
Use when: Tasks are independent. Speed matters most.

### The Siege (methodical)
Sequential waves, each wave verified before next.
```
Ender → Build wave → Verify → Test wave → Verify → Deploy wave → Verify
```
Use when: Dependencies are tight. Correctness matters most.

### The Pincer (competitive)
Multiple approaches in parallel, pick the winner.
```
Ender → Approach A (3 agents) + Approach B (3 agents) → evaluate → pick winner → ship
```
Use when: Uncertain which approach is best. Budget for exploration.

### The Armada (verification)
Pure sandbox testing — 15-20 environments in parallel.
```
Ender → 20 sandbox agents → aggregate results → verdict
```
Use when: Need production confidence. Testing a new agent or service.

### The Hive (recursive)
Swarms spawning swarms for complex multi-system work.
```
Ender → Fleet A (sub-ender + 5 agents) + Fleet B (sub-ender + 5 agents) → merge → armada → ship
```
Use when: Mission is too complex for flat parallelism. Multiple interconnected workstreams.

## Stop Conditions
- All fleets report success + sandbox armada passes threshold → MISSION COMPLETE
- Critical fleet fails and can't be reinforced → MISSION FAILED (report what's done)
- User cancels → Graceful shutdown (kill background agents, clean up sandboxes)
- 50 agent limit reached → Stop spawning, work with what's running

## Examples

### "Build a lead management API and deploy it"
```
Fleet Alpha (Build): scaffolder + api-builder + db-engineer (parallel, worktree)
Fleet Beta (Wire): connector (hook up to existing lead pipeline)
Fleet Gamma (Quality): code-reviewer + security-reviewer + test-engineer (parallel)
Sandbox Armada: 20 sandboxes — functional, auth, load, chaos scenarios
Fleet Delta (Deploy): deployer → Conway sandbox with domain
Fleet Epsilon (Monitor): monitor → set up health checks + Telegram alerts
```

### "Verify the new auto-fix skill works"
```
Sandbox Armada only:
  20 sandboxes, each with a different broken scenario:
  - Sandbox 1: ImportError
  - Sandbox 2: TypeError  
  - Sandbox 3: SyntaxError
  - Sandbox 4: Config corruption
  - ...
  - Sandbox 20: Cascading failure
  
  Each sandbox: deploy auto-fix agent → inject error → verify it fixes it
  Aggregate: 17/20 pass → FIX 3 failing scenarios before shipping
```

### "Fix all 5 open bugs"
```
The Blitz:
  5 executor agents in parallel (worktree isolation each)
  Each gets one bug
  5 verifier agents in parallel (verify each fix)
  git-master merges all worktrees
  Sandbox armada: 15 sandboxes running full regression suite
```
