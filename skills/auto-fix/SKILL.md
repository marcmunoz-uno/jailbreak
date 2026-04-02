---
name: auto-fix
description: Automated error diagnosis and fix loop — catches failures, diagnoses root cause, applies fix, verifies
level: 4
triggers:
  - autofix
  - fix-loop
user-invocable: true
pipeline:
  - debugger (diagnose) → executor (fix) → verifier (confirm)
---

# Auto-Fix Skill

## Purpose
When a build, test, or tool execution fails, automatically diagnose the root cause, apply a targeted fix, and verify the fix works — without manual intervention. This is the "error hook" turned into a full workflow.

## When to Use
- Build failures during autopilot/ralph/ultrawork execution
- Test suite regressions after code changes
- Tool execution errors (MCP server failures, hook script errors)
- Import/dependency resolution failures
- Type errors caught by lsp_diagnostics

## Execution Policy
- **Mode**: Loop with circuit breaker (max 3 attempts per error)
- **Escalation**: After 3 failed fixes → escalate to architect agent for structural diagnosis
- **Scope**: Fix the error, nothing more. No refactoring, no improvements, no cleanup.
- **Safety**: Git stash before first fix attempt. Revert all changes if loop exhausts without success.

## Workflow

### Phase 1: Error Capture
Receive error context:
```
- Error message (full stderr/stdout)
- Command that failed
- File(s) involved
- Stack trace (if available)
- Recent changes (git diff)
```

### Phase 2: Diagnosis (debugger agent)
Spawn `debugger` agent with error context:
1. Parse error message — extract file, line, error type
2. Read the failing code at the exact location
3. Check recent git diff — did a recent change cause this?
4. Form hypothesis: what's the root cause?
5. If hypothesis confidence < 60% → spawn `tracer` for deeper analysis

**Output**: Root cause + proposed fix (as a diff)

### Phase 3: Apply Fix (executor agent)
1. `git stash` (if not already stashed)
2. Apply the proposed fix via Edit tool
3. Minimal change only — touch exactly what's needed

### Phase 4: Verify
1. Re-run the original failing command
2. If it passes → done, commit the fix
3. If it fails with the SAME error → increment attempt counter, go to Phase 2 with new context
4. If it fails with a DIFFERENT error → log both errors, go to Phase 2 with combined context

### Phase 5: Circuit Breaker
If 3 attempts fail:
1. Revert ALL changes (`git stash pop` to restore original state)
2. Spawn `architect` agent with full diagnostic context:
   - All 3 error messages
   - All 3 attempted fixes
   - Why each fix failed
3. Architect produces structural diagnosis + recommended approach
4. Present to user for manual decision

## Error Classification

| Error Type | Diagnosis Strategy | Typical Fix |
|---|---|---|
| Import/Module not found | Check package.json/requirements.txt, check file paths | Install dep or fix import path |
| Type error | Read type definitions, check recent signature changes | Fix type annotation or cast |
| Syntax error | Parse error location, check for typos | Fix syntax at exact line |
| Test assertion failure | Read test + implementation, check expected vs actual | Fix implementation or update test |
| Runtime error | Read stack trace, trace data flow | Fix logic at root cause |
| Config error | Validate config schema, check env vars | Fix config value or schema |
| Permission error | Check file permissions, check auth config | Fix permissions or auth |

## Stop Conditions
- Fix verified (original command passes) → commit and report
- Circuit breaker hit (3 failures) → revert and escalate
- Error is in external dependency (can't fix) → report and suggest workaround
- User cancels

## Examples

### Good: Single-pass fix
```
Error: ModuleNotFoundError: No module named 'requests'
Diagnosis: Missing dependency, not in requirements.txt
Fix: pip install requests && echo "requests" >> requirements.txt
Verify: Original command passes ✓
```

### Good: Multi-pass with escalation
```
Attempt 1: Fix type error at line 42 → new error at line 58
Attempt 2: Fix cascading type error at line 58 → original error returns (wrong fix)
Attempt 3: Try different approach at line 42 → still fails
→ Circuit breaker: Revert all, escalate to architect
→ Architect: "The real issue is the interface changed in commit abc123, need to update 3 consumers"
```

### Bad: Scope creep
```
Error: Unused import warning
Fix: Remove unused import AND refactor the whole file AND add type hints
→ WRONG. Just remove the unused import.
```
