# Jailbreak

Experimental AI agent harness built on Claude Code. Unrestricted sandbox with all guardrails removed and experimental features unlocked.

Part of a multi-agent autonomous system:

| Agent | Role |
|---|---|
| **Nexus** | LLM coordinator (runs every 30 min) |
| **Scout** | Proactive improvement finder |
| **Claude Code** | Primary builder (with OMC orchestration) |
| **OpenClaw** | Cron executor (33 jobs) |
| **Hermes** | Research agent (Telegram, web search) |
| **Jailbreak** | Experimental agent (this repo) |

## Structure

```
jailbreak/
├── agents/           30 specialist agents (swarm-commander, deployer, firefighter, etc.)
├── skills/           42 executable workflows (swarm, deploy, scaffold, incident, etc.)
├── hooks/            5 lifecycle scripts (session start/stop, error capture, etc.)
├── commands/         Slash commands (conway, deploy, status)
├── hud/              Statusline HUD script
├── mcp-config/       MCP server definitions (API keys redacted)
├── omc-state/        Plans, autopilot specs, research reports, evolution ledger
├── plugins/          Plugin registry + official plugins submodule
├── projects/         Agent identity & memory
├── claude-code.md    OMC orchestration manifest
├── claude-settings.json   Base Claude Code settings
└── settings.json     Jailbreak harness config
```

## Agents (30)

Organized by function:

**Orchestration**: ender (recursive swarm commander), planner
**Analysis**: architect, analyst, critic, tracer, scientist, integrator
**Implementation**: executor, designer, code-simplifier, debugger, git-master, scaffolder, api-builder, db-engineer
**Operations**: deployer, firefighter, monitor, pipeline-builder, connector
**Quality**: code-reviewer, security-reviewer, test-engineer, qa-tester, verifier
**Support**: explore, document-specialist, writer
**Meta**: evolve (self-improvement)

Each agent has a defined model tier (haiku/sonnet/opus), tool permissions, and handoff rules.

## Skills (42)

### Execution
- **swarm** — Decompose any task into parallel agent waves, execute with max concurrency
- **autopilot** — Full autonomous: expand idea > plan > execute > QA > validate
- **ralph** — Persistence loop until acceptance criteria pass
- **team** — N coordinated agents on shared task list
- **nuke** — Controlled teardown and parallel rebuild of broken services

### Build & Ship
- **scaffold** — Generate complete runnable projects from a description
- **deploy** — One-command deployment to any target (Conway, Docker, VPS, serverless)
- **wire** — Connect any two services (webhooks, MCP, adapters, pipelines)

### Analysis & Fix
- **multi-model-chain** — Progressive haiku > sonnet > opus pipeline with quality gates
- **auto-fix** — Error diagnosis with 3-attempt circuit breaker
- **perf-profile** — Measure > diagnose > optimize > verify with benchmarks
- **incident** — Production incident response: triage > fix > verify > document
- **deep-interview** — Socratic Q&A with ambiguity scoring

### Meta
- **self-evolve** — Evidence-backed harness improvement loop

## Hooks

| Hook | Event | What it does |
|---|---|---|
| on-start.sh | SessionStart | Loads fabric memory context into session |
| on-stop.sh | Stop (async) | Archives meaningful work to fabric memory |
| on-error.sh | Stop (async) | Captures unresolved errors with type classification |
| pre-commit.sh | Manual | Generates commit context from diff + fabric history |
| fabric-adapter.sh | Sourced | Provides fabric memory read/write/search functions |

## MCP Servers

- **agent-memory** — Persistent memory backend
- **task-dispatcher** — Task queue and delegation
- **godmode** — LLM consortium (multi-model queries)
- **parse** — Web parsing (API key redacted)

## Setup

This repo is the configuration layer. The runtime depends on:
- [Claude Code](https://claude.ai/code) with [oh-my-claudecode](https://github.com/anthropics/oh-my-claudecode) (OMC)
- Fabric memory system at `~/fabric/`
- Hook harness at `~/icarus-daedalus/`
- MCP servers at `~/n8n-workflows/` and `~/agent-memory-server/`
