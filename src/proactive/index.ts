import { watch } from 'fs'
import { execSync } from 'child_process'

export interface ProactiveConfig {
  enabled: boolean
  checkInterval: number  // ms
  triggers: ProactiveTrigger[]
}

export interface ProactiveTrigger {
  name: string
  condition: () => Promise<boolean>  // When to trigger
  action: string                     // Prompt to execute when condition is true
  cooldown: number                   // ms between triggers
  lastTriggered?: number
}

// Stored as plain strings so they survive serialization.
type RecentAction = string

export class ProactiveEngine {
  private config: ProactiveConfig
  private intervalHandle: ReturnType<typeof setInterval> | null = null
  private recentActions: RecentAction[] = []
  private readonly MAX_RECENT = 50

  constructor(config: ProactiveConfig) {
    this.config = { ...config, triggers: [...config.triggers] }
  }

  start(): void {
    if (!this.config.enabled || this.intervalHandle !== null) return
    this.intervalHandle = setInterval(() => void this.runCycle(), this.config.checkInterval)
  }

  stop(): void {
    if (this.intervalHandle !== null) {
      clearInterval(this.intervalHandle)
      this.intervalHandle = null
    }
  }

  addTrigger(trigger: ProactiveTrigger): void {
    // Replace if name already registered.
    this.removeTrigger(trigger.name)
    this.config.triggers.push(trigger)
  }

  removeTrigger(name: string): void {
    this.config.triggers = this.config.triggers.filter(t => t.name !== name)
  }

  getStatus(): { running: boolean; triggers: ProactiveTrigger[]; recentActions: string[] } {
    return {
      running: this.intervalHandle !== null,
      triggers: this.config.triggers.map(t => ({ ...t })),
      recentActions: [...this.recentActions],
    }
  }

  // ---- private ----

  private async runCycle(): Promise<void> {
    const now = Date.now()
    for (const trigger of this.config.triggers) {
      const lastTriggered = trigger.lastTriggered ?? 0
      if (now - lastTriggered < trigger.cooldown) continue

      let shouldFire = false
      try {
        shouldFire = await trigger.condition()
      } catch {
        // Condition check failed — skip this cycle.
      }

      if (!shouldFire) continue

      trigger.lastTriggered = now
      void this.executeAction(trigger.name, trigger.action)
    }
  }

  private async executeAction(triggerName: string, action: string): Promise<void> {
    const entry = `[${new Date().toISOString()}] ${triggerName}: ${action}`
    this.recentActions = [entry, ...this.recentActions].slice(0, this.MAX_RECENT)

    try {
      const { runWorker } = await import('../coordinator/workerAgent.js')
      await runWorker({
        taskId: `proactive-${triggerName}-${Date.now()}`,
        task: action,
        allowedTools: [],
        timeout: 60_000,
      })
    } catch {
      // Proactive actions are best-effort — log and continue.
    }
  }
}

// ---- Built-in trigger factories ----

/**
 * Trigger when files in cwd have changed recently. Uses fs.watch for instant
 * notification; condition() returns true once a change is detected, then clears
 * the flag until the next modification.
 */
export function createFileWatcherTrigger(cwd: string): ProactiveTrigger {
  let changed = false
  let watcher: ReturnType<typeof watch> | null = null

  const startWatcher = (): void => {
    try {
      watcher = watch(cwd, { recursive: true }, (_event, filename) => {
        if (filename && !filename.includes('node_modules') && !filename.startsWith('.git/')) {
          changed = true
        }
      })
    } catch {
      // Watch may fail on some platforms — fall back to always-false condition.
    }
  }

  startWatcher()

  return {
    name: 'file-watcher',
    condition: async (): Promise<boolean> => {
      if (!changed) return false
      changed = false
      return true
    },
    action: 'Files in the current working directory have changed. Briefly describe the modifications and suggest any related actions (e.g. re-running tests, updating imports, rebuilding).',
    cooldown: 30_000,
  }
}

/**
 * Trigger when test files change. Watches for *.test.* and *.spec.* changes
 * and offers to run the test suite.
 */
export function createTestWatcherTrigger(cwd: string): ProactiveTrigger {
  let testChanged = false

  try {
    watch(cwd, { recursive: true }, (_event, filename) => {
      if (filename && /\.(test|spec)\.[a-z]+$/.test(filename)) {
        testChanged = true
      }
    })
  } catch {
    // Ignore watch failures — condition will never fire.
  }

  return {
    name: 'test-watcher',
    condition: async (): Promise<boolean> => {
      if (!testChanged) return false
      testChanged = false
      return true
    },
    action: 'Test files have changed. Offer to run the test suite and report on failures.',
    cooldown: 60_000,
  }
}

/**
 * Trigger when there are uncommitted changes sitting in the working tree.
 * Checks git status — if more than `threshold` files are modified, suggests a commit.
 */
export function createGitWatcherTrigger(cwd: string, threshold = 5): ProactiveTrigger {
  return {
    name: 'git-watcher',
    condition: async (): Promise<boolean> => {
      try {
        const result = execSync('git status --porcelain 2>/dev/null', {
          cwd,
          encoding: 'utf8',
          timeout: 5000,
        })
        const changedLines = result.trim().split('\n').filter(Boolean)
        return changedLines.length >= threshold
      } catch {
        return false
      }
    },
    action: `There are ${threshold}+ uncommitted changes in the working tree. Review the diff and suggest a commit with an appropriate message.`,
    cooldown: 5 * 60_000,
  }
}

/**
 * Trigger when recent shell commands have failed. Reads the last exit code
 * from a shared signal file written by the shell hook (if configured).
 * Falls back gracefully when no signal file is present.
 */
export function createErrorWatcherTrigger(signalFile = '/tmp/.proactive-last-exit'): ProactiveTrigger {
  return {
    name: 'error-watcher',
    condition: async (): Promise<boolean> => {
      try {
        const { readFile, unlink } = await import('fs/promises')
        const content = await readFile(signalFile, 'utf8')
        const exitCode = parseInt(content.trim(), 10)
        if (exitCode !== 0) {
          await unlink(signalFile).catch(() => {})
          return true
        }
        return false
      } catch {
        return false
      }
    },
    action: 'A recent command exited with a non-zero status. Investigate the likely cause and offer diagnostic steps or a fix.',
    cooldown: 2 * 60_000,
  }
}

/** Convenience factory: create a ProactiveEngine pre-loaded with all built-in triggers. */
export function createProactiveEngine(
  cwd: string,
  overrides?: Partial<ProactiveConfig>,
): ProactiveEngine {
  const triggers: ProactiveTrigger[] = [
    createFileWatcherTrigger(cwd),
    createTestWatcherTrigger(cwd),
    createGitWatcherTrigger(cwd),
    createErrorWatcherTrigger(),
  ]

  const config: ProactiveConfig = {
    enabled: true,
    checkInterval: 30_000,
    triggers,
    ...overrides,
  }

  return new ProactiveEngine(config)
}

// ---- Reactive proactive state store ----
// REPL.tsx reads these via useSyncExternalStore so any state change triggers
// a re-render without React needing to own the state itself.

type ProactiveListener = () => void

let _proactiveActive = false
let _contextBlocked = false
let _paused = false
const _listeners = new Set<ProactiveListener>()

function _notify(): void {
  for (const l of _listeners) l()
}

export function subscribeToProactiveChanges(listener: ProactiveListener): () => void {
  _listeners.add(listener)
  return () => { _listeners.delete(listener) }
}

export function isProactiveActive(): boolean {
  return _proactiveActive && !_paused && !_contextBlocked
}

export function activateProactive(_source: string): void {
  if (_proactiveActive) return
  _proactiveActive = true
  _notify()
}

export function deactivateProactive(): void {
  _proactiveActive = false
  _notify()
}

export function pauseProactive(): void {
  _paused = true
  _notify()
}

export function resumeProactive(): void {
  _paused = false
  _notify()
}

export function setContextBlocked(blocked: boolean): void {
  _contextBlocked = blocked
  _notify()
}
