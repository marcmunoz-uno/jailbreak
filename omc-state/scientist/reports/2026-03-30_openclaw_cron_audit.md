# OpenClaw Cron System Audit
**Date**: 2026-03-30  
**Source**: `/Users/marcmunoz/.openclaw/cron/jobs.json`  
**Total Jobs**: 38  
**Run Logs**: 60 files in `/Users/marcmunoz/.openclaw/cron/runs/`

---

## Summary Counts

| Category | Count |
|---|---|
| Total jobs | 38 |
| Enabled (active) | 22 |
| Disabled | 16 |
| Last status: ok | 33 |
| Last status: error | 4 |
| Never run / no state | 1 |
| Schedule errors | 1 |

---

## Full Job Table

| # | Job Name | ID (short) | Enabled | Schedule | Model | Last Status | Consecutive Errors | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Daily DSCR Lead Generation | 6dd0958b | YES | 3PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 2 | DSCR Lead Outreach - Pilot (25/day) | 6f95b138 | YES | 4PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 3 | Polymarket Opportunity Scanner | 2a843f2b | NO | hourly | (no model set) | ok | 0 | DISABLED. No model field. Last run Feb 23. |
| 4 | Hourly Contact Enrichment | f3ecc37b | NO | :15 past every hour | (no model set) | ok | 0 | DISABLED. No model field. |
| 5 | Glint Market Monitor | 5197ca32 | YES | every 1hr | haiku-4-5-20251001 | ok | 0 | — |
| 6 | Morning Briefing | 90521a45 | YES | 8AM daily | haiku-4-5-20251001 | ERROR | 1 | TIMED OUT (120s limit too low for complexity) |
| 7 | DSCR Lead Pipeline (Daily) | 6b250f66 | YES | 3PM M-F | haiku-4-5-20251001 | ok | 0 | Overlaps with Daily DSCR Lead Generation at same time |
| 8 | Memory Maintenance | 8757ac19 | YES | 3AM daily | haiku-4-5-20251001 | ERROR | 1 | TIMED OUT (900s limit but ran 996s) |
| 9 | Evening Revenue Report | 00196062 | YES | 9PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 10 | Dashboard Data Refresh | d8c864f2 | NO | every 15min | sonnet-4-20250514 | ok | 0 | DISABLED. Last run Feb 23. |
| 11 | Kalshi Arbitrage Scanner | 7fa5f3c3 | YES | every 1hr | haiku-4-5-20251001 | ok | 0 | — |
| 12 | Paper Trading Monitor | 49e0e7d4 | YES | every 1hr | haiku-4-5-20251001 | ok | 0 | — |
| 13 | Situation Monitor — Geopolitical Edge Scanner | 03ca9343 | YES | every 30min | haiku-4-5-20251001 | ok | 0 | — |
| 14 | Twitter Auto-Post (Morning) | e497d110 | NO | 8:15AM daily | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 15 | Twitter Auto-Post (Midday) | bc4d120c | NO | 12:30PM daily | sonnet-4-20250514 | ERROR | 1 | DISABLED. Last error: timeout. |
| 16 | Twitter Auto-Post (Evening + Thread) | e7bd23a6 | NO | 6PM daily | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 17 | Twitter RE Engagement (15-20 replies/day) | 06bb958f | NO | 9,11,1,3,5PM | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 18 | Twitter Viral Trend Analysis | df7c2da2 | NO | 7AM daily | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 19 | Daily Instagram Reel Package | 5ed39d9b | NO | 12PM daily | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 20 | Daily Lead CSV for PropStream Skip Trace | 92b70c7f | YES | 9PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 21 | Daily Cash-Flowing Deals Email (25%+ CoC) | 70e90372 | YES | 12PM daily | sonnet-4-20250514 | ERROR | 1 | TIMED OUT (900s limit, ran 1034s) |
| 22 | Memecoin Scanner | bac2e969 | YES | 9,11,1,3,5,7,9,11PM | haiku-4-5-20251001 | ok | 0 | — |
| 23 | whale-tracker-refresh | 96e23af1 | NO | every 1hr | (no model set) | ok | 0 | DISABLED. No model field. |
| 24 | daily-dashboard-refresh | 054d21e5 | YES | 11PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 25 | SMS Health Check | d183d7f5 | NO | every 2hr | (no model set) | ok | 0 | DISABLED. No model field. |
| 26 | Enhanced Universal Autoresearch - 6 Hour Cycles | dc4fe4a0 | NO | every 2hr | sonnet-4-20250514 | ok | 0 | DISABLED. Last run Mar 19. |
| 27 | EVOLVE MODE - Skill Enhancement Cycle | faa2d26a | NO | every 6hr | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 28 | dashboard-keepalive-fixed | ed4e366f | NO | :20 past every hr | (no model set) | ok | 0 | DISABLED. No model. Superseded by daily-dashboard-refresh? |
| 29 | Total Recall Observer | e3ec5538 | YES | every 2hr | haiku-4-5-20251001 | ok | 0 | — |
| 30 | Total Recall Reflector | d99d8609 | YES | every 2hr | haiku-4-5-20251001 | ok | 0 | — |
| 31 | Critical Job Health Monitor | 01c296e1 | NO | every 30min | haiku-4-5-20251001 | ok | 0 | DISABLED. Overlaps with Agent Coordinator. |
| 32 | Polymarket Scanner | 7b848435 | YES | every 1hr | haiku-4-5-20251001 | ok | 0 | — |
| 33 | Quantitative Trading Research Agent | 0b31fe76 | YES | every 2hr | sonnet-4-20250514 | ok | 0 | — |
| 34 | LinkedIn DSCR Content Automation | 72245d9e | NO | 8AM M/W/F | sonnet-4-20250514 | ok | 0 | DISABLED. |
| 35 | Twitter DSCR Content Automation | 10052adb | NO | every 6hr | haiku-4-5-20251001 | ok | 0 | DISABLED. |
| 36 | Weekly Content Strategy Optimization | a882ce1f | YES | 10AM Monday | haiku-4-5-20251001 | ok | 0 | — |
| 37 | Parse.bot Daily Scraper | 0b0e436c | YES | 3PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 38 | MiroFish Simulation Engine | f936909c | YES | every 4hr | haiku-4-5-20251001 | ok | 0 | Missing sessionKey field. |
| 39 | Enhanced Knowledge Graph Maintenance | d0661b0c | YES | every 6hr | haiku-4-5-20251001 | ok | 0 | Uses systemEvent payload (not agentTurn). sessionTarget=main. |
| 40 | LinkedIn Post Engagement Monitor - March 23 | 4c8d2ee8 | NO | every 30min | (no model set) | ok | 0 | DISABLED. Stale one-off job. Should be deleted. |
| 41 | Pattern Detection Scanner | e7b7c843 | YES | every 2hr | haiku-4-5-20251001 | ok | 0 | Missing agentId/sessionKey. |
| 42 | Escalation Alerter | 5d5b058f | NO | :15 past every 2hr | haiku-4-5-20251001 | ok | 0 | DISABLED. |
| 43 | Memory Server Health Monitor | f17dbe9d | NO | every 30min | haiku-4-5-20251001 | ok | 0 | DISABLED. |
| 44 | Daily System Health Report | 5c33e967 | YES | 8:05AM daily | haiku-4-5-20251001 | ok | 0 | — |
| 45 | Weekly Metrics Rotation | 1aa3ca97 | YES | 3:30AM Sunday | haiku-4-5-20251001 | ok | 0 | — |
| 46 | Weekly Outcome Analysis | cb5eac16 | YES | 10AM Sunday | haiku-4-5-20251001 | ok | 0 | — |
| 47 | Fix Verification Checker | c00bbf2c | NO | :30 past every hr | haiku-4-5-20251001 | ok | 0 | DISABLED. |
| 48 | Tax Deed Property Scanner | 2a210f51 | YES | 2PM daily | haiku-4-5-20251001 | ok | 0 | Missing agentId/sessionKey. |
| 49 | Generate Parse.bot API Key | 939abf4b | NO | one-shot (Mar 26) | sonnet-4-20250514 | ERROR | 1 | DISABLED. deleteAfterRun=true but still present. Timed out. Stale. |
| 50 | Trade Resolution Pipeline | 7829c43a | YES | every 2hr | haiku-4-5-20251001 | ok | 0 | — |
| 51 | Daily Trading Digest | 129d2bd6 | YES | 9PM daily | haiku-4-5-20251001 | ok | 0 | — |
| 52 | DSCR Multi-Touch Outreach Sequence | daca8f37 | YES | 4PM M-F | haiku-4-5-20251001 | ok | 0 | No lastRunAtMs (never run yet) |
| 53 | Skill Optimizer | 2685f598 | NO | every 12hr | sonnet-4-20250514 | null | 0 | SCHEDULE ERROR — kind=interval not supported. 3 schedule errors logged. Never run. |
| 54 | Agent Coordinator (Nervous System) | 78961fb4 | YES | every 30min | haiku-4-5-20251001 | ok | 0 | — |
| 55 | Trading System Watchdog | 0770b44c | YES | every 1hr | haiku-4-5-20251001 | ok | 0 | — |

---

## Issues Found

### CRITICAL — Jobs Currently Failing (consecutiveErrors > 0)

| Job | Error | Root Cause | Recommendation |
|---|---|---|---|
| Morning Briefing (90521a45) | cron: job execution timed out | 120s timeout too short for multi-step briefing that reads files + sends Telegram | Increase timeoutSeconds to 300 |
| Memory Maintenance (8757ac19) | cron: job execution timed out | Ran 996s vs 900s limit | Increase timeoutSeconds to 1200 |
| Daily Cash-Flowing Deals Email (70e90372) | cron: job execution timed out | Ran 1034s vs 900s limit; photo screening via image tool is slow | Increase timeoutSeconds to 1800 or simplify photo step |
| Generate Parse.bot API Key (939abf4b) | cron: job execution timed out | One-shot job that ran Mar 26, timed out, deleteAfterRun=true but NOT deleted | Delete this job manually |

### WARNING — Schedule Configuration Issues

| Job | Issue |
|---|---|
| Skill Optimizer (2685f598) | Uses `kind: "interval"` which is not a valid schedule type (valid: cron, every, at). Has 3 accumulated schedule errors. Job has never run. Fix to `kind: "every"` with `everyMs: 43200000`. |
| MiroFish Simulation Engine (f936909c) | Missing `sessionKey` and `agentId` fields (others have these). Works currently but non-standard. |
| Pattern Detection Scanner (e7b7c843) | Missing `agentId` and `sessionKey` fields. |
| Tax Deed Property Scanner (2a210f51) | Missing `agentId` and `sessionKey` fields. |

### WARNING — Missing Model Fields (uses system default)

Jobs with no `model` field set in payload — they will use whatever the system default is:

| Job | Enabled | Impact |
|---|---|---|
| Polymarket Opportunity Scanner (2a843f2b) | NO | Low (disabled) |
| Hourly Contact Enrichment (f3ecc37b) | NO | Low (disabled) |
| whale-tracker-refresh (96e23af1) | NO | Low (disabled) |
| SMS Health Check (d183d7f5) | NO | Low (disabled) |
| dashboard-keepalive-fixed (ed4e366f) | NO | Low (disabled) |
| LinkedIn Post Engagement Monitor (4c8d2ee8) | NO | Low (disabled) |
| daily-dashboard-refresh (054d21e5) | YES | ACTIVE — no model set. Will use system default. Recommend adding `model: "claude-haiku-4-5-20251001"` |

### WARNING — Potential Scheduling Conflicts (3PM slot)

Three separate jobs fire at exactly 3:00 PM ET daily:

| Job | Schedule | Notes |
|---|---|---|
| Daily DSCR Lead Generation (6dd0958b) | `0 15 * * *` | Runs every day |
| DSCR Lead Pipeline (Daily) (6b250f66) | `0 15 * * 1-5` | Runs M-F only |
| Parse.bot Daily Scraper (0b0e436c) | `0 15 * * *` | Runs every day |

All three scrape property/lead data at the same time, potentially competing for API rate limits (Zillow, BatchData). Consider staggering by 10-15 minutes.

### INFO — Stale / Orphaned Jobs

| Job | Reason |
|---|---|
| LinkedIn Post Engagement Monitor - March 23 (4c8d2ee8) | Disabled one-off job for a specific post from March 23. Should be deleted. |
| Generate Parse.bot API Key (939abf4b) | Had `deleteAfterRun: true`, ran once (timed out), still in jobs.json. Should be deleted. |
| dashboard-keepalive-fixed (ed4e366f) | Disabled. Its function (keepalive) is now covered by daily-dashboard-refresh. Last ran Mar 25. |
| Critical Job Health Monitor (01c296e1) | Disabled. Functionality covered by Agent Coordinator. |

### INFO — Gateway Errors (from gateway.err.log)

- `Channel is required when multiple channels are configured: telegram, whatsapp` — Two occurrences on Mar 29 at 4:18PM and 4:25PM. Some job fired a `message` tool call without specifying `channel=telegram`. The Evening Revenue Report (9PM) reads `/tmp/dscr_traced.json` and `/tmp/dscr_emails.json` which did not exist on Mar 29 at 9PM (read errors logged).

---

## Enabled Active Jobs — Clean Summary

22 jobs currently enabled and running:

| Job | Schedule | Model | Status |
|---|---|---|---|
| Daily DSCR Lead Generation | 3PM daily | haiku-4-5-20251001 | ok |
| DSCR Lead Outreach - Pilot | 4PM daily | haiku-4-5-20251001 | ok |
| Glint Market Monitor | every 1hr | haiku-4-5-20251001 | ok |
| Morning Briefing | 8AM daily | haiku-4-5-20251001 | **ERROR - timeout** |
| DSCR Lead Pipeline (Daily) | 3PM M-F | haiku-4-5-20251001 | ok |
| Memory Maintenance | 3AM daily | haiku-4-5-20251001 | **ERROR - timeout** |
| Evening Revenue Report | 9PM daily | haiku-4-5-20251001 | ok |
| Kalshi Arbitrage Scanner | every 1hr | haiku-4-5-20251001 | ok |
| Paper Trading Monitor | every 1hr | haiku-4-5-20251001 | ok |
| Situation Monitor | every 30min | haiku-4-5-20251001 | ok |
| Daily Lead CSV for PropStream | 9PM daily | haiku-4-5-20251001 | ok |
| Daily Cash-Flowing Deals Email | 12PM daily | sonnet-4-20250514 | **ERROR - timeout** |
| Memecoin Scanner | 8x daily | haiku-4-5-20251001 | ok |
| daily-dashboard-refresh | 11PM daily | haiku-4-5-20251001 | ok |
| Total Recall Observer | every 2hr | haiku-4-5-20251001 | ok |
| Total Recall Reflector | every 2hr | haiku-4-5-20251001 | ok |
| Polymarket Scanner | every 1hr | haiku-4-5-20251001 | ok |
| Quantitative Trading Research Agent | every 2hr | sonnet-4-20250514 | ok |
| Weekly Content Strategy Optimization | 10AM Monday | haiku-4-5-20251001 | ok |
| Parse.bot Daily Scraper | 3PM daily | haiku-4-5-20251001 | ok |
| MiroFish Simulation Engine | every 4hr | haiku-4-5-20251001 | ok |
| Enhanced Knowledge Graph Maintenance | every 6hr | haiku-4-5-20251001 | ok |
| Pattern Detection Scanner | every 2hr | haiku-4-5-20251001 | ok |
| Daily System Health Report | 8:05AM daily | haiku-4-5-20251001 | ok |
| Weekly Metrics Rotation | 3:30AM Sunday | haiku-4-5-20251001 | ok |
| Weekly Outcome Analysis | 10AM Sunday | haiku-4-5-20251001 | ok |
| Tax Deed Property Scanner | 2PM daily | haiku-4-5-20251001 | ok |
| Trade Resolution Pipeline | every 2hr | haiku-4-5-20251001 | ok |
| Daily Trading Digest | 9PM daily | haiku-4-5-20251001 | ok |
| DSCR Multi-Touch Outreach Sequence | 4PM M-F | haiku-4-5-20251001 | ok (never run yet) |
| Agent Coordinator (Nervous System) | every 30min | haiku-4-5-20251001 | ok |
| Trading System Watchdog | every 1hr | haiku-4-5-20251001 | ok |

---

## Recommended Actions (Priority Order)

1. **Fix timeout on Morning Briefing** — increase `timeoutSeconds` from 120 to 300.
2. **Fix timeout on Memory Maintenance** — increase `timeoutSeconds` from 900 to 1200.
3. **Fix timeout on Daily Cash-Flowing Deals Email** — increase `timeoutSeconds` from 900 to 1800, or simplify the photo screening step.
4. **Delete stale jobs** — Remove `939abf4b` (Generate Parse.bot API Key) and `4c8d2ee8` (LinkedIn Post Engagement Monitor - March 23).
5. **Fix Skill Optimizer schedule** — Change `kind: "interval"` to `kind: "every"` to clear 3 accumulated schedule errors.
6. **Add model to daily-dashboard-refresh** — Only active job missing a model field.
7. **Stagger 3PM jobs** — Offset DSCR Lead Pipeline or Parse.bot Scraper by 10-15 minutes to avoid concurrent API contention.
8. **Investigate channel error** — Two `message` tool calls on Mar 29 at ~4PM did not specify `channel`. Likely from a job that calls the message tool directly in its prompt without specifying channel=telegram. Review Evening Revenue Report or DSCR Outreach Pilot prompts.

