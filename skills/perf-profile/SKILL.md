---
name: perf-profile
description: Performance profiling and optimization — identify bottlenecks, measure impact, apply targeted optimizations
level: 4
triggers:
  - profile
  - perf
  - optimize
  - bottleneck
user-invocable: true
pipeline:
  - scientist (measure) → architect (diagnose) → executor (optimize) → scientist (verify)
---

# Performance Profiling Skill

## Purpose
Systematically identify performance bottlenecks, measure them with real data, apply targeted optimizations, and verify the improvement with before/after benchmarks. No premature optimization — measure first, then fix what matters.

## When to Use
- User reports slowness in a specific operation
- Build/test times have increased noticeably
- API response times exceed SLOs
- Memory usage is growing unexpectedly
- Cron jobs are taking longer than their schedule interval

## Execution Policy
- **Mode**: Sequential (measure → diagnose → optimize → verify)
- **Evidence threshold**: Every optimization must show measurable improvement (before/after numbers)
- **Scope**: Fix the top bottleneck only. Don't optimize everything at once.
- **Safety**: Benchmark before AND after. If optimization makes things worse or equal, revert.

## Workflow

### Phase 1: Baseline Measurement (scientist agent)
Spawn `scientist` agent to establish baseline:
1. Identify what to measure (runtime, memory, I/O, network)
2. Run the operation 3 times, record median
3. Profile with appropriate tool:
   - **Python**: `cProfile`, `py-spy`, `memory_profiler`
   - **Node.js**: `--prof`, `clinic.js`, `0x`
   - **Shell**: `time`, `strace -c`, `hyperfine`
   - **General**: `time` wrapper, wall clock measurement
4. Identify top 3 hotspots by cumulative time/memory

**Output**:
```markdown
## Baseline Profile
- **Operation**: [what was measured]
- **Median runtime**: X ms (n=3, stddev=Y)
- **Top hotspots**:
  1. [function/file:line] — X% of total time
  2. [function/file:line] — Y% of total time  
  3. [function/file:line] — Z% of total time
- **Memory peak**: X MB
```

### Phase 2: Root Cause Diagnosis (architect agent)
Spawn `architect` agent with baseline data:
1. Read the code at each hotspot
2. Classify the bottleneck:
   - **Algorithmic**: O(n²) where O(n) is possible
   - **I/O bound**: Blocking reads, missing caching, sequential where parallel is possible
   - **Memory**: Large allocations, missing cleanup, data structure choice
   - **Network**: N+1 queries, missing batching, synchronous calls
   - **Concurrency**: Lock contention, GIL, thread starvation
3. For the #1 hotspot, propose a specific optimization with expected improvement

### Phase 3: Apply Optimization (executor agent)
1. Git commit current state (safety checkpoint)
2. Apply the proposed optimization — minimal change
3. No premature abstractions, no "while we're here" improvements

### Phase 4: Verification (scientist agent)
1. Run the SAME benchmark from Phase 1
2. Compare before/after:
   - Runtime improvement (% and absolute)
   - Memory impact
   - Correctness check (same output?)
3. If improvement < 5% → revert (not worth the complexity)
4. If improvement ≥ 5% → keep and report

**Output**:
```markdown
## Optimization Result
- **Before**: X ms median
- **After**: Y ms median  
- **Improvement**: Z% (X-Y ms saved)
- **Memory impact**: [same/better/worse]
- **Correctness**: [verified/regression detected]
- **Verdict**: [KEEP/REVERT]
```

## Stop Conditions
- Optimization verified with measurable improvement → keep and report
- Optimization shows no improvement → revert and report findings
- Top hotspot is in external code (library, system call) → report with workaround suggestions
- User cancels

## Examples

### Good: Data-driven optimization
```
Baseline: API endpoint /leads takes 2.3s median
Hotspot: database query at models/lead.py:47 — 89% of time (N+1 query in loop)
Optimization: Batch query with SELECT ... WHERE id IN (...)
After: 180ms median
Improvement: 92% — KEEP
```

### Bad: Premature optimization
```
"Let's optimize all the imports to be lazy-loaded"
→ No baseline measurement. No evidence imports are the bottleneck. REJECT.
```
