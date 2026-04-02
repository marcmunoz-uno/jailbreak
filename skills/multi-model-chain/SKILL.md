---
name: multi-model-chain
description: Progressive refinement pipeline — chain haiku→sonnet→opus for escalating analysis depth
level: 5
triggers:
  - chain
  - multi-model
  - progressive
user-invocable: true
aliases:
  - mmc
---

# Multi-Model Chain Skill

## Purpose
Route work through progressively more capable models, where each tier refines the output of the previous one. This is not "ask three models the same question" (that's `ccg`). This is a pipeline where each model builds on the last, with explicit quality gates between tiers.

## When to Use
- Complex analysis where you want fast triage before deep analysis
- Large codebases where haiku can filter/narrow before sonnet/opus dig in
- Cost optimization — use cheap models for broad sweeps, expensive models only for what matters
- When you need both speed (haiku) and depth (opus) on the same problem

## Architecture

```
┌─────────┐     ┌──────────┐     ┌─────────┐
│  HAIKU   │────→│  SONNET   │────→│  OPUS   │
│  Sweep   │     │  Analyze  │     │  Judge  │
│          │     │           │     │         │
│ Broad    │     │ Focused   │     │ Deep    │
│ Fast     │     │ Thorough  │     │ Final   │
│ Filter   │     │ Refine    │     │ Verdict │
└─────────┘     └──────────┘     └─────────┘
    Gate 1           Gate 2          Output
  (relevance)     (substance)      (decision)
```

## Execution Policy
- **Mode**: Sequential with quality gates
- **Early exit**: If Gate 1 finds nothing relevant, stop (don't waste sonnet/opus tokens)
- **Bypass**: User can specify `--start-at sonnet` or `--start-at opus` to skip tiers
- **Max context forwarded**: Each tier passes a structured summary to the next, not raw output

## Workflow

### Phase 1: Haiku Sweep (model=haiku)
Spawn `explore` agent (haiku) with the broad task:
- Scan for all potentially relevant files, patterns, or data points
- Produce a ranked shortlist with confidence scores
- Flag anything ambiguous for sonnet to investigate

**Gate 1**: If shortlist is empty → report "nothing found" and stop.
If shortlist has items with confidence > 0.8 → pass only those to sonnet.
If all items < 0.5 confidence → pass all with a note to re-evaluate.

**Output format to pass forward:**
```markdown
## Haiku Sweep Results
- **Query**: [original task]
- **Files scanned**: [count]
- **Shortlist**: 
  1. [file:line] — [reason] (confidence: X)
  2. ...
- **Ambiguous**: [items needing deeper look]
```

### Phase 2: Sonnet Analysis (model=sonnet)
Spawn appropriate agent (executor, debugger, architect, etc.) with:
- The haiku shortlist as input context
- Task: analyze each shortlisted item in depth
- Produce findings with evidence (file:line, code snippets, test results)
- Rate each finding: CRITICAL / MAJOR / MINOR / INFO

**Gate 2**: If no CRITICAL or MAJOR findings → report findings and stop (don't escalate to opus).
If CRITICAL findings exist → pass to opus for final judgment.

**Output format to pass forward:**
```markdown
## Sonnet Analysis
- **Findings**:
  1. [CRITICAL] [description] — evidence: [file:line]
  2. [MAJOR] [description] — evidence: [file:line]
  3. ...
- **Recommendations**: [specific actions]
- **Needs opus judgment**: [yes/no + why]
```

### Phase 3: Opus Judgment (model=opus)
Spawn `architect` or `critic` agent (opus) with:
- Sonnet's findings as input
- Task: render final judgment — validate findings, assess trade-offs, decide action
- Produce a decision with reasoning

**Output: Final verdict with actionable next steps.**

## Configuration

### Chain Profiles
Users can invoke with a profile that pre-configures the chain:

- `--profile security`: haiku(grep secrets) → sonnet(security-reviewer) → opus(critic)
- `--profile refactor`: haiku(explore patterns) → sonnet(code-simplifier) → opus(architect)  
- `--profile debug`: haiku(grep errors) → sonnet(debugger) → opus(tracer)
- `--profile review`: haiku(explore changes) → sonnet(code-reviewer) → opus(critic)

### Custom Chains
```
/multi-model-chain "find and fix N+1 queries" --agents explore,debugger,architect
```
Maps agents to tiers in order: first=haiku, second=sonnet, third=opus.

## Stop Conditions
- Gate 1 filters everything out (nothing relevant)
- Gate 2 finds nothing critical (sonnet output is sufficient)
- Opus renders final verdict
- User cancels

## Examples

### Good: Progressive narrowing
```
Task: "Find security vulnerabilities in the auth module"
Haiku: Scans 847 files, shortlists 12 files in auth/
Sonnet: Analyzes 12 files, finds 2 CRITICAL (SQL injection, missing CSRF), 3 MINOR
Opus: Validates both CRITICALs, recommends fix order, notes the CSRF is actually mitigated by framework
```

### Good: Early exit saves tokens
```
Task: "Check if we have any hardcoded API keys"
Haiku: Greps all files, finds 0 matches for key patterns
→ Gate 1: Empty shortlist → STOP. Report: "No hardcoded keys found."
(Saved sonnet + opus tokens)
```

### Bad: Using this for simple tasks
```
Task: "What's in package.json?"
→ Don't use multi-model-chain. Just read the file.
```
