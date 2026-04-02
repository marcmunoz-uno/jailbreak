---
name: swarm
description: Dynamic swarm orchestration — decompose any task into parallel agent waves, execute, merge results
level: 5
triggers:
  - swarm
  - army
  - parallel build
  - fan out
user-invocable: true
pipeline:
  - swarm-commander (plan) → agents × N (execute) → integrator (merge) → verifier (confirm)
---

# Swarm Skill

## Purpose
Take any task — from "build a full-stack app" to "fix 15 bugs" to "review everything in this repo" — and execute it with maximum parallelism using coordinated agent swarms.

## When to Use
- Multi-file or multi-service tasks that can be parallelized
- Large refactors touching many independent files
- Bulk operations (review 20 PRs, fix 10 bugs, scaffold 5 services)
- Any task where sequential execution is the bottleneck

## Execution Policy
- **Orchestrator**: swarm-commander (Opus) plans waves, assigns agents
- **Workers**: Appropriate agents per task, run in worktree isolation when writing code
- **Max concurrency**: 20 agents per wave
- **Conflict prevention**: Worktree isolation for writers, none needed for readers
- **Merge**: Dependency-order merge after each wave completes

## Workflow

### Phase 1: Decompose (swarm-commander)
Spawn swarm-commander with full task description:
1. Commander analyzes the task and produces a wave plan
2. Each wave has: agent assignments, isolation mode, dependencies, timeouts
3. Conflict map identifies shared files and resolution strategy

### Phase 2: Execute Waves
For each wave (sequential between waves, parallel within waves):

```
Wave 0: Research
  └─ spawn explore ×3 (parallel, no isolation)
  └─ gather results → feed into Wave 1

Wave 1: Foundation  
  └─ spawn scaffolder + db-engineer (parallel, worktree isolation)
  └─ merge worktrees → feed into Wave 2

Wave 2: Implementation
  └─ spawn executor ×N (parallel, worktree isolation per agent)
  └─ merge worktrees → feed into Wave 3

Wave 3: Integration
  └─ spawn connector + integrator (parallel)
  └─ merge → feed into Wave 4

Wave 4: Quality Gate
  └─ spawn code-reviewer + security-reviewer + test-engineer (parallel, read-only)
  └─ gather findings → fix or pass

Wave 5: Ship
  └─ spawn deployer (single agent)
  └─ spawn monitor (post-deploy verification)
```

### Phase 3: Merge & Resolve
After each wave:
1. Collect all agent outputs
2. For worktree agents: merge branches in dependency order
3. If merge conflicts: spawn executor to resolve, then re-verify
4. If quality gate failures: spawn executor to fix, re-run quality gate (max 2 retries)

### Phase 4: Report
```markdown
## Swarm Execution Report

### Task: [description]
### Result: [SUCCESS / PARTIAL / FAILED]

### Waves Executed
| Wave | Agents | Duration | Status |
|------|--------|----------|--------|
| 0: Research | explore ×3 | 12s | ✓ |
| 1: Foundation | scaffolder, db-engineer | 45s | ✓ |
| ... | ... | ... | ... |

### Artifacts Produced
- [file/service/artifact] — [description]
- ...

### Issues Encountered
- [any conflicts, failures, retries]
```

## Stop Conditions
- All waves complete successfully → report and done
- Critical failure in foundation wave → abort (can't continue without base)
- Quality gate fails 3x on same issue → report as PARTIAL, hand off remaining issues
- User cancels

## Examples

### Build a full-stack app
```
Input: "Build a lead management API with React frontend and PostgreSQL"
Wave 0: explore (check existing code, deps)
Wave 1: scaffolder (project structure), db-engineer (schema + migrations)
Wave 2: api-builder (REST endpoints), executor (React frontend) — parallel
Wave 3: connector (wire frontend to API)
Wave 4: code-reviewer, test-engineer — parallel
Wave 5: deployer (Conway sandbox)
```

### Fix all bugs from an issue list
```
Input: "Fix issues #12, #15, #18, #22, #31"
Wave 0: explore ×5 (one per issue, parallel research)
Wave 1: executor ×5 (one per issue, worktree isolation, parallel fixes)
Wave 2: verifier ×5 (parallel verification)
Wave 3: git-master (atomic commits per fix)
```
