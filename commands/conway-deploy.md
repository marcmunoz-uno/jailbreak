# /conway-deploy

Guided deployment workflow. Deploy the current project (or a specified project) to a Conway sandbox and return a public URL.

## Steps

1. **Analyze the project**: Look at the current directory or `$ARGUMENTS` path. Identify:
   - Language/runtime (Node.js, Python, Go, static HTML, etc.)
   - Entry point (package.json scripts, main.py, Dockerfile, index.html, etc.)
   - Dependencies (package.json, requirements.txt, go.mod, etc.)
   - Port the application listens on

2. **Check resources**: Run `credits_balance` to ensure sufficient credits.

3. **Create sandbox**: Use `sandbox_create` with appropriate sizing:
   - Static site → 1 vCPU, 512MB
   - Node.js/Python app → 2 vCPU, 2048MB
   - Build-heavy project → 4 vCPU, 4096MB

4. **Upload code**: Use `sandbox_write_file` for each file. For large projects:
   - Consider writing a git clone command if the repo is public
   - Or tar + base64 encode for efficiency
   - Skip node_modules, .git, __pycache__, and other build artifacts

5. **Install dependencies**:
   - Node.js: `sandbox_exec` → `cd /root/app && npm install`
   - Python: `sandbox_exec` → `cd /root/app && pip install -r requirements.txt`
   - Go: `sandbox_exec` → `cd /root/app && go build`

6. **Start the service**:
   - Use `sandbox_exec` with `nohup` or `&` for background execution
   - Node.js: `cd /root/app && nohup node index.js > /tmp/app.log 2>&1 &`
   - Python: `cd /root/app && nohup python main.py > /tmp/app.log 2>&1 &`
   - Wait a moment, then check the log for startup errors

7. **Expose the port**: `sandbox_expose_port` with the application's port.

8. **Verify**: Optionally use `sandbox_exec` with `curl localhost:<port>` to verify the service is responding.

9. **Return results**: Present the deployment summary:
   ```
   Deployed successfully!

   URL:     https://<port>-<sandbox-id>.life.conway.tech
   Sandbox: <sandbox-id>
   Runtime: <detected runtime>
   Port:    <port>

   To check logs: sandbox_exec with "cat /tmp/app.log"
   To attach a custom domain: /conway sandbox attach-domain <sandbox-id> <domain>
   To stop: sandbox_delete with sandbox ID
   ```

## Error Recovery

- If dependency install fails, show the error and suggest fixes
- If the app crashes on start, show log output
- If port exposure fails, check if the service is actually listening
