# Open Questions

## openclaw-system-fix — 2026-03-30
- [ ] BatchData API: Are both keys (`WngdkIgQGF99yvduZXoXyV9ZlNeU1SnJp3HBqrNe` and `FNxURktbRKujUAks6vAasbvM12XnO7tk81yudkDi`) from the same account? One may be revoked while the other works. — Determines whether this is a quick fix or requires dashboard login.
- [ ] Mailgun domain: Is the sending domain `munoz.ltd` or a subdomain like `mg.munoz.ltd`? — Affects which DNS records to create.
- [ ] Duplicate lead pipeline jobs: "Daily DSCR Lead Generation" (id 6dd0958b, runs batchdata_pipeline.py) vs "DSCR Lead Pipeline (Daily)" (id 6b250f66, runs dscr_lead_scraper.py) — are both needed or is one a legacy duplicate? They run at overlapping times (both 3PM).
- [ ] Agent Memory Server (PID 31157): Was this intentionally long-running or did it hang? Should it be restarted after RAM cleanup? — Affects whether we just kill it or restart it.
- [ ] Godmode node processes (5 running): Which are actively serving requests vs orphaned? — Need to identify before killing.
- [ ] Paper portfolio reset: Should closed/resolved trades be preserved for outcome analysis, or full wipe to fresh start? — Affects the reset script logic.
- [ ] Chrome headless processes: Are any of these actively used by the zillow_for_sale.py scraper or other scrapers? — Killing them could break active scraping jobs.
