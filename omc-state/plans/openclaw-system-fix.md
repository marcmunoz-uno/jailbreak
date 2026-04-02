# OpenClaw System Fix — Prioritized Execution Plan

**Created:** 2026-03-30
**Scope:** 10 issues across ~15 files, 3 phases
**Estimated complexity:** HIGH (system-wide, multi-service)

---

## Phase 1: TODAY — Quick Wins & Critical Fixes

### Task 1.1: Reset Paper Portfolio & Verify Risk Limits (CRITICAL)

**Problem:** 425 open positions, $9,999 deployed, 97.2% drawdown — but `check_risk_limits()` IS wired into all 3 trade executors. The portfolio was already bloated before risk limits were added on Mar 25.

**Root Cause:** The risk limits code was added AFTER the system already had 434 trades. The check gates new trades but never cleans up existing violations. The portfolio needs a hard reset.

**Files:**
- `/Users/marcmunoz/mission-control/paper_portfolio.json` (425 open positions)
- `/Users/marcmunoz/n8n-workflows/risk_limits.py` (limits module — verified working)
- `/Users/marcmunoz/n8n-workflows/paper_trader.py` (has risk check at line 160-172 — VERIFIED)
- `/Users/marcmunoz/.openclaw/workspace/polymarket_bot/place_paper_trades.py` (has risk check at line 113 — VERIFIED)
- `/Users/marcmunoz/.openclaw/workspace/skills/quant-research/kalshi_executor.py` (has risk check at line 221 — VERIFIED)

**Steps:**
1. **Back up the current portfolio:**
   ```bash
   cp /Users/marcmunoz/mission-control/paper_portfolio.json /Users/marcmunoz/mission-control/paper_portfolio_BACKUP_20260330.json
   ```

2. **Force-resolve all 425 open positions as EXPIRED** — write a one-time script that:
   - Iterates `open_positions`, sets `status: "force_closed"`, `resolution.outcome: "EXPIRED_RESET"`, `resolution.resolved_at: "2026-03-30T00:00:00Z"`
   - Moves each to `closed_positions`
   - Resets `balance` to `10000`, `total_invested` to `0`
   - Clears `open_positions` to `[]`

3. **Verify risk limits gate after reset:**
   ```bash
   cd /Users/marcmunoz/n8n-workflows
   python3 -c "
   from risk_limits import check_risk_limits
   ok, reason = check_risk_limits('/Users/marcmunoz/mission-control/paper_portfolio.json', 50.0, 'test trade')
   print(f'Allowed: {ok}, Reason: {reason}')
   "
   ```

**Acceptance Criteria:**
- [ ] Portfolio has 0 open positions, $10,000 balance
- [ ] `check_risk_limits()` returns `(True, "ok")` for a $50 test trade
- [ ] `check_risk_limits()` returns `(False, ...)` for a $600 trade (exceeds $500 limit)
- [ ] Backup exists at `paper_portfolio_BACKUP_20260330.json`

---

### Task 1.2: Kill RAM-Hungry Processes (CRITICAL)

**Problem:** 95 MB free of 16 GB. System is thrashing.

**Steps:**
1. **Kill the Agent Memory Server (76.8% CPU since Mar 25):**
   ```bash
   kill 31157  # Agent Memory Server — been running 5 days at 76.8% CPU
   ```

2. **Kill unnecessary long-running processes:**
   ```bash
   # Kill the 9-day-old http.server on port 8080 (likely leftover debug)
   lsof -ti:8080 | xargs kill 2>/dev/null

   # Kill the 15-day-old offer webhook (will be restarted by cron when needed)
   pkill -f "offer_webhook_system.js"

   # Kill stale Chrome browser automation (14 days running)
   pkill -f "chrome.*headless" 2>/dev/null
   pkill -f "chromium" 2>/dev/null
   ```

3. **Trim godmode processes — identify which are needed:**
   ```bash
   ps aux | grep "godmode" | grep -v grep
   # Kill any that aren't actively serving requests
   ```

4. **Verify RAM recovered:**
   ```bash
   vm_stat | head -5
   top -l 1 | head -10
   ```

**Acceptance Criteria:**
- [ ] At least 2 GB free RAM after cleanup
- [ ] No processes running longer than 24 hours that aren't intentional daemons
- [ ] Agent Memory Server restarted cleanly (if still needed)

---

### Task 1.3: Fix Cron Timeout Failures (HIGH)

**Problem:** 3 jobs timing out — Morning Briefing (120s), Memory Maintenance (900s), Daily Cash-Flowing Deals Email (900s).

**File:** `/Users/marcmunoz/.openclaw/cron/jobs.json`

**Steps — edit the jobs.json directly:**

1. **Morning Briefing** (job id `90521a45`): Change `timeoutSeconds` from `120` to `300`
2. **Memory Maintenance** (job id `8757ac19`): Change `timeoutSeconds` from `900` to `1200`
3. **Daily Cash-Flowing Deals Email** (job id `70e90372`): Change `timeoutSeconds` from `900` to `1800`

**Commands:**
```bash
# After editing jobs.json, trigger gateway reload:
python3 -c "
import json, time
cfg = '/Users/marcmunoz/.openclaw/openclaw.json'
with open(cfg) as f: data = json.load(f)
data['meta'] = data.get('meta', {})
data['meta']['lastTouchedAt'] = int(time.time() * 1000)
with open(cfg, 'w') as f: json.dump(data, f, indent=2)
print('Gateway reload triggered')
"
```

**Acceptance Criteria:**
- [ ] Morning Briefing timeout = 300s
- [ ] Memory Maintenance timeout = 1200s
- [ ] Daily Cash-Flowing Deals Email timeout = 1800s
- [ ] Gateway reloaded (next cron runs complete without timeout)

---

### Task 1.4: Fix Cron Config Issues (MEDIUM)

**File:** `/Users/marcmunoz/.openclaw/cron/jobs.json`

**Specific edits:**

1. **Skill Optimizer** (line ~1768): Change `"kind": "interval"` to `"kind": "every"`. Currently never runs because `interval` is not a valid schedule kind.

2. **daily-dashboard-refresh** (job id `054d21e5`): Add `"model": "claude-haiku-4-5-20251001"` to payload. Currently missing model field.

3. **3PM scheduling conflict:** Three lead pipeline jobs all fire at `0 15 * * *`:
   - `Daily DSCR Lead Generation` (id `6dd0958b`) — keep at 15:00
   - `DSCR Lead Pipeline (Daily)` (id `6b250f66`) — move to `"expr": "30 14 * * 1-5"` (2:30 PM)
   - Check if both are needed or if one is redundant (they appear to do similar scraping)

4. **Stale disabled jobs to clean up** (set `"enabled": false` if not already, or delete):
   - `Hourly Contact Enrichment` (id `f3ecc37b`) — disabled, last ran Feb 21
   - `Dashboard Data Refresh` (id `d8c864f2`) — disabled, last ran Feb 21
   - `whale-tracker-refresh` (id `96e23af1`) — disabled, last ran Feb 21
   - `dashboard-keepalive-fixed` (id `ed4e366f`) — disabled, last ran Mar 22

**Acceptance Criteria:**
- [ ] Skill Optimizer schedule kind = "every"
- [ ] daily-dashboard-refresh has model field
- [ ] No 3PM scheduling collision
- [ ] Stale jobs cleaned up

---

### Task 1.5: Start Mission Control (HIGH)

**Problem:** Port 3000 not listening, server.py not running.

**File:** `/Users/marcmunoz/mission-control/server.py`

**Steps:**
```bash
# Check if anything else is on port 3000
lsof -ti:3000 | xargs kill 2>/dev/null

# Start Mission Control
cd /Users/marcmunoz/mission-control
nohup python3 server.py > /tmp/mission_control.log 2>&1 &

# Verify
sleep 2
curl -s http://localhost:3000/api/status | python3 -m json.tool
```

**Acceptance Criteria:**
- [ ] `curl http://localhost:3000/api/status` returns JSON with `"status": "online"`
- [ ] Process stays running after 60 seconds

---

### Task 1.6: Rotate Oversized Logs (MEDIUM)

**Steps:**
```bash
# Rotate gateway logs
cd /Users/marcmunoz/.openclaw/logs
mv gateway.log gateway.log.$(date +%Y%m%d) 2>/dev/null
mv gateway.err.log gateway.err.log.$(date +%Y%m%d) 2>/dev/null
gzip gateway.log.$(date +%Y%m%d) 2>/dev/null
gzip gateway.err.log.$(date +%Y%m%d) 2>/dev/null

# Clean up accumulated glint/kalshi JSON files older than 7 days
find /tmp -name "glint_*.json" -mtime +7 -delete 2>/dev/null
find /tmp -name "kalshi_*.json" -mtime +7 -delete 2>/dev/null
```

**Acceptance Criteria:**
- [ ] gateway.log < 1 MB after rotation
- [ ] Stale /tmp JSON files cleaned

---

## Phase 2: THIS WEEK — Structural Fixes

### Task 2.1: Fix DSCR Enrichment Pipeline (CRITICAL)

**Problem:** BatchData API returning 403 Forbidden. Token `WngdkIgQGF99yvduZXoXyV9ZlNeU1SnJp3HBqrNe` is disabled. The cron job also references a DIFFERENT token: `FNxURktbRKujUAks6vAasbvM12XnO7tk81yudkDi` (in batchdata_pipeline.py line 21).

**Discovery:** Two different BatchData API keys exist:
- Cron job prompt: `WngdkIgQGF99yvduZXoXyV9ZlNeU1SnJp3HBqrNe`
- batchdata_pipeline.py: `FNxURktbRKujUAks6vAasbvM12XnO7tk81yudkDi`

**Files:**
- `/Users/marcmunoz/.openclaw/workspace/lead_pipeline/batchdata_pipeline.py` (line 21 — hardcoded key)
- `/Users/marcmunoz/.openclaw/cron/jobs.json` (Daily DSCR Lead Generation job — key in prompt)
- Enrichment scraper producing `owner_name = "at DuckDuckGo"` (scraper hitting search page instead of property record)

**Steps:**
1. **Test both BatchData API keys to see which (if any) still works:**
   ```bash
   # Test key from batchdata_pipeline.py
   curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.batchdata.com/api/v1/property/skip-trace" \
     -H "Authorization: Bearer FNxURktbRKujUAks6vAasbvM12XnO7tk81yudkDi" \
     -H "Content-Type: application/json" \
     -d '{"requests":[{"propertyAddress":{"street":"123 Main St","city":"Miami","state":"FL","zip":"33101"}}]}'

   # Test key from cron prompt
   curl -s -o /dev/null -w "%{http_code}" -X POST "https://api.batchdata.com/api/v1/property/skip-trace" \
     -H "Authorization: Bearer WngdkIgQGF99yvduZXoXyV9ZlNeU1SnJp3HBqrNe" \
     -H "Content-Type: application/json" \
     -d '{"requests":[{"propertyAddress":{"street":"123 Main St","city":"Miami","state":"FL","zip":"33101"}}]}'
   ```

2. **If both return 403:** Marc needs to log into BatchData dashboard and reactivate/get a new token. This is a HUMAN ACTION required.

3. **If one works:** Standardize on the working key across all files. Move key to environment variable:
   ```bash
   # Add to .env or openclaw config
   export BATCHDATA_API_KEY="<working_key>"
   ```
   Update `batchdata_pipeline.py` line 21 to use `os.environ.get("BATCHDATA_API_KEY")` only (remove hardcoded fallback).

4. **Fix "at DuckDuckGo" enrichment bug:** The scraper is hitting DuckDuckGo search results instead of property records. Investigate the scraper in `/Users/marcmunoz/.openclaw/workspace/lead_pipeline/` — likely a URL or user-agent issue causing redirects.

5. **Reset consecutive error counters** in the cron state for `dscr_traced` and `dscr_emails` jobs after fix.

**Acceptance Criteria:**
- [ ] BatchData API returns 200 on a test skip trace call
- [ ] `batchdata_pipeline.py --dry-run` completes without 403 errors
- [ ] Owner names in enrichment output are real names, not "at DuckDuckGo"
- [ ] Single API key source of truth (env var, not hardcoded in multiple places)

---

### Task 2.2: Configure Mailgun DNS (CRITICAL for outreach)

**Problem:** SPF/DKIM not configured. 265 Touch 2 emails queued that will hit spam.

**Steps:**
1. **Identify the Mailgun domain and required records:**
   ```bash
   # Search for Mailgun config
   grep -r "mailgun" /Users/marcmunoz/n8n-workflows/ /Users/marcmunoz/.openclaw/workspace/ --include="*.py" --include="*.json" -l
   ```

2. **Marc must configure DNS records** at his domain registrar:
   - SPF: `v=spf1 include:mailgun.org ~all`
   - DKIM: Copy the TXT record from Mailgun dashboard
   - MX records for receiving (if needed)

3. **Verify DNS propagation:**
   ```bash
   dig TXT munoz.ltd +short  # Check SPF
   dig TXT <selector>._domainkey.munoz.ltd +short  # Check DKIM
   ```

4. **Test email delivery:**
   ```bash
   # Send test via Mailgun API and check delivery
   ```

**Dependencies:** Requires Marc's Mailgun credentials and DNS registrar access. This is a HUMAN ACTION.

**Acceptance Criteria:**
- [ ] SPF record resolves correctly
- [ ] DKIM record resolves correctly
- [ ] Test email to marc@munoz.ltd arrives in inbox (not spam)

---

### Task 2.3: Fix Self-Heal Loop (HIGH — Autonomy Gap)

**Problem:** Coordinator creates handoffs in `/Users/marcmunoz/fabric/` but nothing picks them up.

**Files:**
- `/Users/marcmunoz/n8n-workflows/coordinator.py` (creates handoffs via `fabric_handoff.py`)
- `/Users/marcmunoz/n8n-workflows/fabric_handoff.py` (handoff CRUD — writes to `~/fabric/`)
- Cron jobs (need a "handoff executor" job)

**Root Cause:** The coordinator writes handoffs but there is no cron job or daemon that reads `~/fabric/*.md` files marked `status: open` and dispatches them to an agent for execution.

**Steps:**
1. **Create a handoff executor cron job** that runs every 15 minutes:
   - Reads all `~/fabric/*-handoff-*.md` files with `status: open`
   - Groups by priority (high first)
   - For each handoff: dispatches to the appropriate agent session
   - Marks handoff as `status: in_progress`
   - On completion: calls `complete_handoff()` with outcome

2. **Add the job to cron/jobs.json:**
   ```json
   {
     "name": "Self-Heal Executor",
     "enabled": true,
     "schedule": { "kind": "every", "everyMs": 900000 },
     "payload": {
       "kind": "agentTurn",
       "message": "Execute open handoffs from ~/fabric/. Read all *-handoff-*.md files with status: open. For each: attempt the action_needed, then mark complete with outcome. Prioritize 'high' priority handoffs first. If a handoff requires human action, skip it and note why.",
       "model": "claude-haiku-4-5-20251001",
       "timeoutSeconds": 300
     }
   }
   ```

3. **Verify the 7 existing corrections in system_brain:**
   ```bash
   cd /Users/marcmunoz/n8n-workflows
   python3 -c "
   from system_brain import get_unhealthy
   print(get_unhealthy())
   "
   ```

**Acceptance Criteria:**
- [ ] Handoff executor cron job exists and runs every 15 minutes
- [ ] At least 1 existing open handoff gets picked up and acted on
- [ ] Handoffs that require human action are skipped with a logged reason

---

## Phase 3: NEXT WEEK — Autonomy & Resilience

### Task 3.1: Outreach Market Alignment

**Problem:** sequences.db targets Detroit/Milwaukee/Toledo but outcome_config.json priorities are Miami/Houston/Dallas/Atlanta/Phoenix.

**Files:**
- `/Users/marcmunoz/n8n-workflows/outcome_config.json` (source of truth for market priorities)
- `sequences.db` (outreach sequence targets)
- `/Users/marcmunoz/n8n-workflows/dscr_lead_scraper.py`

**Steps:**
1. Read current `outcome_config.json` market priorities
2. Update outreach sequences to target priority markets
3. Add market alignment check to coordinator rules

**Acceptance Criteria:**
- [ ] Active outreach sequences target markets with priority > 0.5 in outcome_config.json
- [ ] No outreach to markets with priority < 0.5

---

### Task 3.2: Log Rotation Automation

**Steps:**
1. Create a weekly cron job that rotates and compresses:
   - `~/.openclaw/logs/gateway.log`
   - `~/.openclaw/logs/gateway.err.log`
   - `/tmp/glint_*.json` older than 7 days
   - `/tmp/kalshi_*.json` older than 7 days
2. Add workspace size monitoring to coordinator rules (alert if > 5 GB)

**Acceptance Criteria:**
- [ ] Log rotation cron job exists
- [ ] Workspace size alerting in coordinator

---

### Task 3.3: Process Watchdog

**Problem:** Long-running processes accumulate without supervision.

**Steps:**
1. Add a coordinator rule that checks for processes running > 24 hours
2. Auto-kill known-safe processes (http.server, offer_webhook_system.js) after staleness threshold
3. Alert Marc for unknown long-running processes

**Acceptance Criteria:**
- [ ] Coordinator detects stale processes
- [ ] Auto-cleanup for known temporary processes

---

## Execution Order (Dependency-Aware)

```
TODAY (parallel where possible):
  [1.2 Kill RAM processes] ──> [1.5 Start Mission Control]
  [1.1 Reset portfolio]    ──> (independent)
  [1.3 Fix cron timeouts]  ──> [1.4 Fix cron config] ──> Gateway reload
  [1.6 Rotate logs]        ──> (independent)

THIS WEEK (sequential):
  [2.1 BatchData API fix]  ──> requires testing, possibly human action
  [2.2 Mailgun DNS]        ──> requires human action (DNS config)
  [2.3 Self-heal loop]     ──> requires new cron job + testing

NEXT WEEK:
  [3.1 Market alignment]
  [3.2 Log rotation]
  [3.3 Process watchdog]
```

## Items Requiring Human Action (Marc)

1. **BatchData API key** — May need to log into BatchData dashboard and reactivate or get new token
2. **Mailgun DNS records** — Must be configured at domain registrar for munoz.ltd
3. **Decision: Keep or remove duplicate lead pipeline jobs?** — "Daily DSCR Lead Generation" vs "DSCR Lead Pipeline (Daily)" appear to overlap

---

## Verification Checklist (Post-Execution)

- [ ] Paper portfolio: 0 open positions, $10,000 balance
- [ ] RAM: > 2 GB free
- [ ] Mission Control: http://localhost:3000/api/status returns online
- [ ] Cron: 0 timeout errors in next 24 hours
- [ ] BatchData: skip trace API returns 200
- [ ] Mailgun: test email arrives in inbox
- [ ] Self-heal: handoffs being picked up
- [ ] Outreach: targeting priority markets
