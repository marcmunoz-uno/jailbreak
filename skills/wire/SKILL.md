---
name: wire
description: Connect any two services — webhooks, MCP tools, API adapters, data pipelines
level: 3
triggers:
  - wire
  - connect
  - integrate
  - hook up
user-invocable: true
pipeline:
  - connector (build integration) → verifier (test the connection)
---

# Wire Skill

## Purpose
Connect any two things together. Service A needs to talk to Service B? This skill builds the glue — webhook, MCP tool, API adapter, message queue, or data pipeline.

## When to Use
- "Connect the lead scorer to the email system"
- "Make an MCP server for the database"
- "Set up a webhook from GitHub to Telegram"
- "Pipe data from source A to destination B"
- Any time you need two systems to communicate

## Execution Policy
- **Detect the simplest integration pattern** — Don't use a message queue when a webhook will do
- **Test the connection** — Not done until data flows end-to-end
- **Handle failures** — Every integration needs error handling and retry logic

## Workflow

### Phase 1: Understand the Connection
1. What's the source? (API, database, file, webhook, event)
2. What's the destination? (API, database, file, notification, action)
3. What triggers the flow? (Event, schedule, manual, on-demand)
4. What data needs to flow? (Format, schema, volume)
5. What auth is needed on each side?

### Phase 2: Choose Pattern
| Source → Dest | Pattern | Implementation |
|---|---|---|
| Event → Action | Webhook | HTTP POST on event |
| Service → Claude | MCP Server | Tool definitions |
| API → API | Adapter | Translation layer |
| DB → DB | ETL Pipeline | Extract/transform/load |
| Anything → Human | Notification | Telegram/Slack/Email |
| Schedule → Action | Cron + Script | Bash/Python on timer |

### Phase 3: Build
Spawn `connector` agent:
1. Create the integration code (webhook handler, MCP server, adapter, pipeline)
2. Configure auth on both sides
3. Set up error handling and retry logic
4. Add logging for observability

### Phase 4: Test
1. Send test data through the connection
2. Verify it arrives at the destination correctly
3. Test error cases (source down, bad data, auth failure)
4. Verify retry logic works

### Phase 5: Report
```
✓ Connected [source] → [destination]
  Pattern: [webhook/MCP/adapter/pipeline]
  Trigger: [event/schedule/manual]
  Error handling: [retry 3x with backoff]
  Test: [passing]
```

## Quick Examples
```
/wire github telegram         → GitHub webhook → Telegram notifications
/wire database mcp            → Database → MCP server (Claude can query it)
/wire leads email             → Lead scorer → Email outreach via webhook
/wire api api --adapter       → Translate between two incompatible APIs
/wire csv database --schedule → Daily CSV import to database
```
