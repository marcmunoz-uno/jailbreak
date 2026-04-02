# /conway-status

Quick Conway Terminal status check. Run all three in parallel:
- `wallet_info` — wallet address + USDC balance
- `credits_balance` — Conway credit balance
- `sandbox_list` — active sandboxes

Present as a compact summary. Keep it short — this is meant to be a fast glance:

```
Wallet:    0x1234...abcd ($X.XX USDC)
Credits:   $X.XX
Sandboxes: N active
```

If any sandboxes are running, add a one-line summary per sandbox: name, status, region.

If there are issues (no credits, no wallet balance), add a brief note about what to do (e.g., "Run /conway fund for funding instructions").
