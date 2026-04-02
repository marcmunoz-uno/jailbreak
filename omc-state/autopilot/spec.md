# Autonomous Multi-Agent Loop — Specification

## Problem
Today's system has all the pieces (system_brain, coordinator, task_dispatcher, event_bus, fabric, godmode, MCP servers) but they're loosely coupled and mostly reactive. The coordinator runs rules every 5 min but can't deeply reason. Claude Code can reason deeply but can't wake itself. Hermes can schedule cron jobs and reach any platform but doesn't participate in the code loop. There's no proactive improvement-seeking or autonomous feature development.

## Goal
Build a unified autonomous loop where:
1. **Scout Loop** — Proactively finds issues, improvements, and feature opportunities
2. **Debug Loop** — Detects failures and autonomously fixes them
3. **Build Loop** — Implements approved improvements/features
4. **Review Loop** — Tracks outcomes and finds ways to improve

## Architecture

### The Nexus (new: `/Users/marcmunoz/n8n-workflows/nexus.py`)
Central orchestrator that replaces the dumb coordinator rules with an LLM-powered decision engine.

**Every 5 minutes (via OpenClaw cron):**
1. Read system_brain briefing (agent states, corrections, health, learnings)
2. Read event_bus for unprocessed events
3. Read task_dispatcher for stalled/failed tasks
4. Read outcome_tracker for recent results
5. Read fabric for open handoffs
6. Feed all context to Godmode (gemini-2.5-flash via godmode_client.ask())
7. LLM decides: what needs attention? what should be improved? what's broken?
8. LLM outputs structured actions: submit_task, create_handoff, publish_event, alert
9. Execute actions

### Agent Roles

**Hermes (Scout + Comms)**
- Cron: every 30 min, reviews system health + logs + outcomes
- Identifies: stale patterns, degraded components, missing capabilities
- Proposes improvements via task_submit(type="feature") or task_submit(type="improvement")
- Sends status reports to Telegram
- Can do web research for solutions (browser, web_search tools)

**Claude Code (Builder + Debugger)**
- Triggered by: task_executor.py polling, or direct OpenClaw cron wakeup
- Picks up: code, debug, refactor, architecture, build tasks
- Has full OMC toolkit (autopilot, ralph, ultrawork for nested execution)
- Reports results via task_complete + fabric write

**OpenClaw (Executor + Scheduler)**
- Runs nexus.py every 5 min (replaces coordinator.py)
- Runs task_executor.py continuously (polls queue, executes via openclaw CLI)
- Manages cron schedules
- Handles non-code tasks: send messages, run scripts, monitor health

### New Components

1. **nexus.py** — LLM-powered coordinator (replaces dumb rule matching)
2. **scout.py** — Proactive improvement finder (called by Hermes cron)
3. **auto_debugger.py** — Failure detection + auto-fix pipeline
4. **improvement_tracker.py** — Tracks proposed improvements, approvals, outcomes

### Data Flow

```
System State (brain, events, tasks, outcomes, fabric)
  → nexus.py (every 5 min, LLM reasoning)
  → Decisions (tasks, handoffs, alerts)
  → Agents execute (Claude Code builds, Hermes scouts, OpenClaw runs)
  → Results recorded (brain, outcomes, fabric)
  → Loop
```

### Safety Rails
- All feature proposals require human approval via Telegram before building
- Debug fixes for known patterns auto-execute (correction lookup)
- New/unknown fixes require approval
- Daily cost cap via godmode_client ($20/day)
- Max 5 auto-fix attempts per component per day
- Kill switch: NEXUS_DISABLED env var or system_brain health "down"
