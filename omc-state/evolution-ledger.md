# Evolution Ledger

Tracks all harness changes proposed and applied by the `self-evolve` skill.

## 2026-04-02 — v2 Harness Upgrade (Initial)

| # | Proposal | Status | Target | Impact |
|---|----------|--------|--------|--------|
| 1 | Add evolve agent for self-improvement analysis | applied | agents/evolve.md | B:4 D:1 |
| 2 | Add integrator agent for cross-system impact | applied | agents/integrator.md | B:4 D:1 |
| 3 | Add self-evolve skill (evidence-backed harness improvement) | applied | skills/self-evolve/ | B:5 D:1 |
| 4 | Add multi-model-chain skill (haiku→sonnet→opus pipeline) | applied | skills/multi-model-chain/ | B:4 D:1 |
| 5 | Add auto-fix skill (error diagnosis loop with circuit breaker) | applied | skills/auto-fix/ | B:4 D:2 |
| 6 | Add perf-profile skill (measure→diagnose→optimize→verify) | applied | skills/perf-profile/ | B:3 D:1 |
| 7 | Add on-error.sh hook (error capture to fabric) | applied | hooks/on-error.sh | B:3 D:1 |
| 8 | Add pre-commit.sh hook (smart commit context) | applied | hooks/pre-commit.sh | B:2 D:1 |

**Rationale**: Gap analysis of 19 agents, 32 skills, and 3 hooks identified: no self-improvement capability, no progressive model chaining, no automated error recovery, no performance workflow, and only 2 of ~6 useful lifecycle hooks were implemented.

## 2026-04-02 — v3 Swarm Army

| # | Proposal | Status | Target | Impact |
|---|----------|--------|--------|--------|
| 1 | Add swarm-commander agent (dynamic parallel orchestration) | applied | agents/swarm-commander.md | B:5 D:2 |
| 2 | Add deployer agent (universal deployment) | applied | agents/deployer.md | B:5 D:1 |
| 3 | Add api-builder agent (full API service generation) | applied | agents/api-builder.md | B:4 D:1 |
| 4 | Add db-engineer agent (schema, migrations, optimization) | applied | agents/db-engineer.md | B:4 D:1 |
| 5 | Add firefighter agent (production incident response) | applied | agents/firefighter.md | B:5 D:1 |
| 6 | Add scaffolder agent (project generation from descriptions) | applied | agents/scaffolder.md | B:4 D:1 |
| 7 | Add connector agent (service integration specialist) | applied | agents/connector.md | B:4 D:1 |
| 8 | Add monitor agent (observability, health checks, alerting) | applied | agents/monitor.md | B:4 D:1 |
| 9 | Add pipeline-builder agent (CI/CD, cron orchestration) | applied | agents/pipeline-builder.md | B:4 D:1 |
| 10 | Add swarm skill (parallel agent wave execution) | applied | skills/swarm/ | B:5 D:2 |
| 11 | Add deploy skill (one-command deployment) | applied | skills/deploy/ | B:5 D:1 |
| 12 | Add scaffold skill (project generation) | applied | skills/scaffold/ | B:4 D:1 |
| 13 | Add incident skill (production response workflow) | applied | skills/incident/ | B:5 D:1 |
| 14 | Add wire skill (connect any two services) | applied | skills/wire/ | B:4 D:1 |
| 15 | Add nuke skill (controlled teardown + parallel rebuild) | applied | skills/nuke/ | B:4 D:3 |

**Rationale**: The harness could analyze and review code but couldn't build, deploy, fix, or monitor services end-to-end. The swarm army fills every gap in the build→deploy→monitor→fix lifecycle and adds dynamic parallel orchestration for maximum throughput.
