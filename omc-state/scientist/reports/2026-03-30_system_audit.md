# System Audit Report — 2026-03-30

[OBJECTIVE] Audit trading, lead generation, and outreach systems. Identify what is working, what is broken, key metrics, and actionable blockers.

---

## 1. TRADING SYSTEM

### Glint Monitor

[FINDING] Glint monitor is running and producing signals but has a persistent AI analysis failure rate of ~9%.
[STAT:n] n = 351 total runs logged
[STAT:effect_size] 319 OK (90.9%) / 32 failed (9.1%)
- Failure cause: JSON parse errors + OpenAI import conflicts when godmode_client is available
- Last successful run: 2026-03-30T01:24:18 (latest glint data timestamped 2026-03-30T01:24)
- Latest signal: Tension Level 100 (CRITICAL) — Fed emergency rate signal + Iran/Hormuz oil surge +4.2%
- Status in system_brain: **healthy** (0 consecutive failures as of 03:11)

[LIMITATION] The glint_latest.json has a timestamp of "2023-04-21T08:48:00.000Z" in its source field — this appears to be a placeholder/test timestamp, not a real scrape time. The actual data content references 2026-03-29 events, so the timestamp field is unreliable.

### Kalshi Scanner

[FINDING] Kalshi scanner is running but finding zero arbitrage opportunities.
[STAT:n] Latest scan: 1,000 markets scanned, 0 opportunities found
- Status in system_brain: **degraded** (stale by 124 min as of 03:11)
- Arb scan file reported MISSING in paper trading monitor
- Volume spikes: 0 found in latest scan

[FINDING] The arb_scan_deep.py file exists but its output (/tmp/arb_scan_latest.json) is missing, suggesting the script either isn't running or failing silently.

### Paper Trader

[FINDING] Paper portfolio has effectively lost all capital.
[STAT:effect_size] Starting balance: $10,000 → Current balance: $0.00002 (~$0.00)
[STAT:n] 434 open positions, 0 closed positions
- Total invested: $9,999.99
- Total returned: $275.00
- Realized P&L: +$189.00 (but this represents positions that returned value, not overall performance)
- Net loss on deployed capital: $9,724.99 (97.2% drawdown)
- Last updated: 2026-03-30T05:09 (active)

[LIMITATION] The portfolio shows 434 open positions with $0 cash remaining. The $189 realized P&L figure likely represents partial wins on small tranches while the bulk of capital is locked in open (unrealized) losing positions. Without closed position data, true win rate cannot be computed. This mirrors the prior -$78K live loss event (noted in system_brain corrections).

### Risk Limits

- `risk_limits.py` is integrated into paper_trader.py (hard gate imported at top)
- Limits set: max 20 positions, $500 max exposure, $150/day loss halt
- [FINDING] Risk limits appear to have been **bypassed or ineffective**: 434 open positions far exceeds the 20-position limit, and $9,999 deployed far exceeds $500 max exposure.

[LIMITATION] Cannot confirm whether risk_limits.py checks are actually enforced at runtime without executing the code. The limits may have been added after the positions were placed, or the check logic may have a bug.

### outcome_config.json

- Last analysis: 2026-03-29T14:16 — active
- All signal weights = 1.0 (no tuning applied)
- Min confidence to trade: "medium" — relatively permissive threshold
- No blacklisted tickers

---

## 2. LEAD PIPELINE

### Daily Lead Generation

[FINDING] Lead pipeline is generating consistent daily output, running every weekday since Feb 22.
[STAT:n] 24 CSV files, date range 2026-02-22 to 2026-03-29
- Most recent: 2026-03-29 — 59 leads
- Peak output: 2026-02-23 — 2,468 leads (anomaly, likely a data dump)
- Typical daily range: 13–229 leads
- Markets covered: Miami FL, Houston TX, Dallas TX, Atlanta GA, Phoenix AZ

[FINDING] Lead enrichment pipeline is failing to enrich owner contact data.
- enrichment_progress.json shows owner_name = "at DuckDuckGo" for all sampled entries
- emails_found: [] (empty) on all sampled enriched leads
- enrichment_methods: [] (no methods succeeded)

### BatchData API

- system_brain health: **healthy** (0 consecutive failures)
- API key hardcoded in enhanced_batchdata_pipeline.py: `WngdkIgQGF99yvduZXoXyV9ZlNeU1SnJp3HBqrNe`
- Earlier reports of 403 errors are NOT reflected in current system_brain health — status shows healthy as of 2026-03-30T02:52
- system_brain correction logged: "Pipeline returns 0 leads when /tmp is stale" (unverified fix)
- system_brain correction logged: "Enriched leads not flowing to outreach" (unverified fix)
- system_brain correction logged: "Institutional investors (REITs) in enriched leads" (unverified fix)

[FINDING] Three BatchData pipeline corrections are logged but none are marked fix_verified=1.

[LIMITATION] Cannot confirm current BatchData API 403 status without a live API call. system_brain self-reports healthy but corrections suggest the enrichment output is not flowing correctly.

### DSCR Pipeline

- dscr_leads data: **degraded** — stale by 3,365 minutes (~56 hours) as of 03:11
- dscr_emails data: **down** (4 consecutive failures, "No data")
- dscr_traced data: **down** (4 consecutive failures, "No data")
- Latest dscr_leads JSON files in /data: 2026-03-27 (last run)

[FINDING] DSCR skip-trace and email enrichment pipelines are down. No owner contact data is being produced.
[STAT:n] 4 consecutive failures, last success unknown

---

## 3. OUTREACH SYSTEM

### Sequences Database

[FINDING] Outreach sequences launched for the first time on 2026-03-29, with 265 leads loaded.
[STAT:n] 265 total sequences
- Touch 1 (iMessage): 19 sent (7.2%), 241 pending (90.9%), 5 failed (1.9%)
- Touch 2 (email): 265 pending (all)
- Replies: 0 (0% response rate — too early, batch sent <2 hours before data snapshot)
- Date range: 2026-03-29T22:02 to 23:54 (all created in ~2 hour window)

[FINDING] Top markets in outreach sequences do NOT match the priority markets in outcome_config.json.
- Sequences: Detroit MI (68), Milwaukee WI (50), Toledo OH (24), Cleveland OH (22)
- Config priority markets: Miami FL, Houston TX, Dallas TX, Atlanta GA, Phoenix AZ

[LIMITATION] The mismatch suggests the outreach batch was sourced from a different lead set than the daily DSCR pipeline, or the pipeline is pulling from a different market config.

### Blooio API

- system_brain health: **healthy** (0 consecutive failures)
- API key: `api_ENNd854QgvpMMjT1uGZBX` (hardcoded in blooio.py)
- Blooio phone: +1 (801) 897-0049
- 5 touch1 failures logged — likely phone number formatting issues (some phones stored without country code)

### Mailgun (Email)

- Status: **degraded** — SPF/DKIM DNS records pending, emails may hit spam
- This will affect Touch 2 email delivery for all 265 pending sequences

### Twitter API

- Status: **down** — API credits exhausted since 2026-02-25 (33 days)

---

## 4. INFRASTRUCTURE

| Component | Status | Failures |
|---|---|---|
| openclaw_gateway | healthy | 0 |
| coordinator | healthy | 0 |
| telegram_bot | healthy | 0 |
| glint_monitor | healthy | 0 |
| outcome_tracker | healthy | 0 |
| blooio_api | healthy | 0 |
| batchdata_api | healthy | 0 |
| activecampaign_api | healthy | 0 |
| parse_bot_scraper | healthy | 0 |
| agent_memory_server | healthy | 0 |
| mission_control | healthy | 0 |
| kalshi_scan data | degraded | 1 |
| dscr_leads data | degraded | 4 |
| mailgun | degraded | 1 |
| dscr_emails | down | 4 |
| dscr_traced | down | 4 |
| twitter_api | down | 1 |

---

## 5. SUMMARY: WORKING vs BROKEN

### Working
- Glint monitor: scraping signals every 30 min, active critical signals (Iran/oil/Fed)
- Kalshi scanner: running every hour, scanning 1,000 markets
- Coordinator: running every 5 min, 9-14 rules evaluated
- Daily lead CSV generation: producing ~50-60 leads/day consistently
- Outreach sequences: launched successfully, 19 iMessages sent
- Blooio iMessage API: operational
- Core infrastructure: gateway, telegram, activecampaign all healthy

### Broken / Degraded
1. **Paper portfolio**: $9,999.99 deployed, $0.00 cash, 434 open positions — risk limits not working
2. **DSCR enrichment pipeline** (dscr_emails, dscr_traced): down for ~56 hours, no contact data flowing
3. **Mailgun DNS**: SPF/DKIM pending — Touch 2 emails will hit spam
4. **Enrichment quality**: owner_name = "at DuckDuckGo", empty email lists — enrichment producing garbage
5. **Arb scan**: output file missing, arbitrage detection not operational
6. **Market mismatch**: outreach targeting Detroit/Milwaukee, config priorities Miami/Houston/Dallas
7. **Glint analysis errors**: 9.1% failure rate (JSON parse + OpenAI import conflict)
8. **Twitter API**: down 33 days, no path to resume without credits

---

## 6. ACTIONABLE BLOCKERS (Priority Order)

1. **[CRITICAL] Fix risk limits in paper_trader.py** — 434 positions, $0 cash. Audit why check_risk_limits() allowed >20 positions and >$500 exposure. Do NOT go live until verified.
2. **[HIGH] Restart DSCR enrichment pipeline** — dscr_emails and dscr_traced both down. Run dscr_skip_trace.py manually and check for errors. 56-hour gap means lead contact data is stale.
3. **[HIGH] Fix Mailgun SPF/DKIM DNS records** — add SPF/DKIM TXT records to domain DNS before Touch 2 emails send. All 265 pending emails will be spam otherwise.
4. **[HIGH] Fix glint analysis JSON parse error** — the godmode_client conflict causes ~9% failure rate. The error pattern "JSON parse + OpenAI import errors" suggests godmode_client returns non-JSON that falls through to OpenAI which isn't importable.
5. **[MEDIUM] Reconcile outreach market targeting** — sequences.db has Detroit/Milwaukee leads but outcome_config.json prioritizes Miami/Houston/Dallas/Atlanta/Phoenix. Align these.
6. **[MEDIUM] Fix enrichment quality** — owner_name "at DuckDuckGo" indicates web scraping is hitting DuckDuckGo search pages instead of actual owner records. Review dscr_lead_scraper.py.
7. **[MEDIUM] Investigate arb scan** — arb_scan_deep.py exists but no output file. Either schedule it or determine if it's intentionally disabled.
8. **[LOW] Twitter API** — 33 days down. Either purchase credits or remove from active monitoring to stop failure noise.

[LIMITATION] All health statuses from system_brain are self-reported by the coordinator, not independently verified. The BatchData "healthy" status may not reflect whether enrichment output is actually flowing to outreach — three unverified corrections suggest otherwise.

