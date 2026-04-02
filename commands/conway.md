# /conway

Conway — cloud compute, domains, wallet, and payments for AI agents.

Parse `$ARGUMENTS` to determine the subcommand. If no arguments or unrecognized input, default to `status`.

---

## Subcommands

### `status` (default)

Show a complete status overview. Run these tools **in parallel**:
- `wallet_info` — wallet address + USDC balance
- `credits_balance` — Conway credit balance
- `sandbox_list` — active sandboxes
- `domain_list` — registered domains

Present results as a compact summary:

```
Conway Status
─────────────
Wallet:    0x1234...abcd ($X.XX USDC on Base)
Credits:   $X.XX
Sandboxes: N active
Domains:   N registered
```

If there are active sandboxes, list each: name, status, region.
If there are registered domains, list each: name, expiry.
If credits are zero or wallet is empty, add a note: "Run /conway fund for funding instructions."

---

### `deploy`

Guided deployment workflow. Deploy the current project (or a path from `$ARGUMENTS`) to a Conway sandbox.

**Steps:**

1. **Analyze the project**: Look at the current directory. Identify language/runtime, entry point, dependencies, and port.

2. **Check resources**: Run `credits_balance` to ensure sufficient credits.

3. **Create sandbox**: Use `sandbox_create` with appropriate sizing:
   - Static site: 1 vCPU, 512MB
   - Node.js/Python app: 2 vCPU, 2048MB
   - Build-heavy project: 4 vCPU, 4096MB

4. **Upload code**: Use `sandbox_write_file` for each file. For large projects, write a git clone command if the repo is public. Skip node_modules, .git, __pycache__, and build artifacts.

5. **Install dependencies**: `sandbox_exec` with the appropriate install command (npm install, pip install, go build, etc.).

6. **Start the service**: `sandbox_exec` with nohup for background execution. Wait briefly, then check logs for startup errors.

7. **Expose the port**: `sandbox_expose_port` with the app's port.

8. **Verify**: `sandbox_exec` with `curl localhost:<port>` to check the service is responding.

9. **Return results**:
   ```
   Deployed!
   URL:      https://<port>-<sandbox-id>.life.conway.tech
   Sandbox:  <sandbox-id>
   Runtime:  <detected runtime>
   Port:     <port>
   ```

If something fails, show the error and suggest fixes rather than giving up.

---

### `domains`

List registered domains. Run `domain_list` and display each domain with name, status, and expiry date.

If no domains, say "No domains registered. Use /conway domains search <name> to find one."

---

### `domains search <name>`

Search for available domains. Extract the search term from `$ARGUMENTS` (everything after "domains search").

Run `domain_search { query: "<name>" }` and display results as a table: domain, available, registration price, renewal price.

Highlight available domains. If the user wants to register one, tell them: `/conway domains register <domain>`.

---

### `domains register <domain>`

Register a domain. Extract the domain from `$ARGUMENTS`.

1. Run `domain_search` or `domain_check` to confirm availability and show the price.
2. Ask the user to confirm the purchase.
3. Run `domain_register { domain: "<domain>" }` — this triggers an x402 USDC payment automatically.
4. Show the registration confirmation with domain name, expiry, and transaction details.

---

### `domains dns <domain>`

Manage DNS records for a domain. Extract the domain from `$ARGUMENTS`.

Run `domain_dns_list { domain: "<domain>" }` and display records in a table: ID, type, host, value, TTL.

If the user wants to add/update/delete records, they can describe what they want and you should use `domain_dns_add`, `domain_dns_update`, or `domain_dns_delete` accordingly.

---

### `domains privacy <domain> on|off`

Toggle WHOIS privacy. Extract the domain and on/off from `$ARGUMENTS`.

Run `domain_privacy { domain: "<domain>", enabled: true/false }`.

Confirm the change: "WHOIS privacy enabled/disabled for <domain>."

---

### `domains ns <domain> <ns1,ns2,...>`

Update nameservers. Extract the domain and comma-separated nameservers from `$ARGUMENTS`.

Run `domain_nameservers { domain: "<domain>", nameservers: ["ns1", "ns2", ...] }`.

Confirm: "Nameservers updated for <domain>."

---

### `domains check <domain1,domain2,...>`

Check availability of specific domains. Extract the comma-separated domains from `$ARGUMENTS`.

Run `domain_check { domains: "<domains>" }` and display availability and pricing.

---

### `sandbox domains <sandbox_id>`

List custom domains attached to a sandbox. Run `sandbox_list_domains { sandbox_id: "<sandbox_id>" }`.

Display each domain with its status, SSL status, and CNAME target.

If no domains, say "No custom domains attached. Use /conway sandbox attach-domain to add one."

---

### `sandbox attach-domain <sandbox_id> <domain>`

Attach a custom domain to a sandbox. The sandbox must already have a custom subdomain (set via `sandbox_expose_port` with a `subdomain` parameter).

**Steps:**

1. Run `sandbox_add_domain { sandbox_id: "<sandbox_id>", domain: "<domain>" }`.
2. The response includes:
   - `cname_target` — the DNS target the user must CNAME their domain to (e.g., `my-app.life.conway.tech`)
   - `ssl_status` — SSL provisioning status (auto-provisioned via Cloudflare)
   - `verification` — any required DNS verification records
   - `instructions` — human-readable setup instructions
3. Display the result:
   ```
   Custom domain attached!

   Domain:      <domain>
   CNAME to:    <cname_target>
   SSL:         <ssl_status>
   Status:      <status>

   DNS Setup: Add a CNAME record pointing <domain> → <cname_target>
   ```
4. If verification is required, show the verification record details.

---

### `sandbox remove-domain <sandbox_id> <domain>`

Remove a custom domain from a sandbox.

Run `sandbox_remove_domain { sandbox_id: "<sandbox_id>", domain: "<domain>" }`.

Confirm: "Custom domain <domain> removed from sandbox <sandbox_id>."

---

### `fund`

Show wallet funding instructions:
1. Get wallet info from `wallet_info`
2. Display:
   - Wallet address and selected network from `wallet_info`
   - Current USDC balance
   - Current credit balance (from `credits_balance`)
   - Supported chains from `wallet_networks` (Base mainnet + Base Sepolia)
   - Explain: USDC in wallet is used for x402 payments (domain registration, etc.)
   - Explain: Credits are used for sandbox compute billing
   - Link to app.conway.tech for credit top-ups

---

### `setup`

Guide first-time configuration:
1. Confirm MCP server is connected (you're reading this, so it is)
2. Check wallet with `wallet_info`
3. Check credits with `credits_balance`
4. If credits are zero or wallet is empty, show funding instructions
5. List sandboxes to confirm API connectivity
6. Summarize: "You're all set! Use /conway to check status anytime."

---

### `help`

List all capabilities:

```
/conway                       Status overview (wallet, credits, sandboxes, domains)
/conway deploy                Deploy current project to a sandbox
/conway domains               List your registered domains
/conway domains search <name> Search available domains with pricing
/conway domains register <d>  Register a domain (x402 USDC payment)
/conway domains dns <domain>  List/manage DNS records
/conway domains privacy <d> on|off   Toggle WHOIS privacy
/conway domains ns <d> <ns1,ns2>     Update nameservers
/conway domains check <d1,d2>        Check specific domain availability
/conway sandbox domains <id>         List custom domains on a sandbox
/conway sandbox attach-domain <id> <domain>  Attach custom domain to sandbox
/conway sandbox remove-domain <id> <domain>  Remove custom domain from sandbox
/conway fund                  Wallet address + funding instructions
/conway setup                 First-time configuration guide
/conway help                  This help message
```

**Key concepts:**
- **Sandboxes** — cloud VMs for running code. Billed from Conway credits. Support custom domains via Cloudflare.
- **Custom Domains** — attach your own domain to a sandbox. Requires a CNAME to `{subdomain}.life.conway.tech`. SSL is auto-provisioned.
- **Domains** — register and manage domains. Paid via x402 USDC on Base.
- **Credits** — prepaid balance for sandbox compute. Top up at app.conway.tech.
- **Wallet** — local EVM wallet for x402 payments, created at `~/.conway/wallet.json`. Supports Base mainnet and Base Sepolia.
- **x402** — HTTP payment protocol. The MCP server handles 402 responses automatically.

Docs: https://conway.tech/docs
