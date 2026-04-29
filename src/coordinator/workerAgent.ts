import { ASYNC_AGENT_ALLOWED_TOOLS, COORDINATOR_MODE_ALLOWED_TOOLS } from '../constants/tools.js'

// Active worker registry — module-level so getActiveWorkers() and killWorker() work
// across concurrent callers without shared object references.
const activeWorkers = new Map<string, ActiveWorker>()

type ActiveWorker = WorkerConfig & { abortController: AbortController }

export interface WorkerConfig {
  taskId: string
  task: string
  allowedTools: string[]
  timeout?: number
}

export interface WorkerResult {
  taskId: string
  status: 'completed' | 'failed' | 'timeout'
  result: string
  toolsUsed: string[]
  duration: number
}

/**
 * Pluggable execution backend. The coordinator passes this in from its session
 * context (e.g. a bound `runForkedAgent` call). Defaults to a no-op stub so
 * the module can be imported and tested without a live session.
 *
 * Concrete implementation comes from the AgentTool dispatch path in QueryEngine.
 */
export type WorkerExecutor = (task: string, allowedTools: string[], signal: AbortSignal) => Promise<{ text: string; toolsUsed: string[] }>

let globalExecutor: WorkerExecutor | null = null

/**
 * Register the session-level executor. Called by QueryEngine / coordinator
 * bootstrap once a session is live.
 */
export function registerExecutor(executor: WorkerExecutor): void {
  globalExecutor = executor
}

/**
 * Default allowed tools for coordinator workers — the async agent set minus
 * any coordinator-only tools (AgentTool, SendMessage, etc.).
 */
function resolveAllowedTools(requested: string[]): string[] {
  if (requested.length > 0) {
    // Caller supplied an explicit allowlist — filter against known safe tools.
    const safe = new Set([
      ...ASYNC_AGENT_ALLOWED_TOOLS,
      ...COORDINATOR_MODE_ALLOWED_TOOLS,
    ])
    return requested.filter(t => safe.has(t))
  }
  return Array.from(ASYNC_AGENT_ALLOWED_TOOLS)
}

/**
 * Run an isolated worker for the given task. The worker has access only to
 * `config.allowedTools` (or the default async-agent set if empty). Concurrent
 * callers each get their own AbortController so killWorker() is selective.
 *
 * Requires a session-level executor to have been registered via `registerExecutor`,
 * or passed directly as `config.executor`. Throws if neither is available.
 */
export async function runWorker(
  config: WorkerConfig & { executor?: WorkerExecutor },
): Promise<WorkerResult> {
  const startTime = Date.now()
  const abortController = new AbortController()
  const resolvedTools = resolveAllowedTools(config.allowedTools)
  const executor = config.executor ?? globalExecutor

  if (!executor) {
    return {
      taskId: config.taskId,
      status: 'failed',
      result: 'No worker executor registered. Call registerExecutor() from the active session context before dispatching workers.',
      toolsUsed: [],
      duration: Date.now() - startTime,
    }
  }

  activeWorkers.set(config.taskId, { ...config, abortController })

  try {
    const timeoutMs = config.timeout ?? 5 * 60_000 // 5 min default

    const timeoutId = setTimeout(() => abortController.abort(), timeoutMs)
    abortController.signal.addEventListener('abort', () => clearTimeout(timeoutId))

    const resultPromise = executor(config.task, resolvedTools, abortController.signal)

    let timedOut = false
    const timeoutRace = new Promise<never>((_, reject) => {
      abortController.signal.addEventListener('abort', () => {
        timedOut = true
        reject(new Error('timeout'))
      })
    })

    const { text, toolsUsed } = await Promise.race([resultPromise, timeoutRace])

    return {
      taskId: config.taskId,
      status: 'completed',
      result: text,
      toolsUsed,
      duration: Date.now() - startTime,
    }
  } catch (err: unknown) {
    const isTimeout = err instanceof Error && err.message === 'timeout'
    return {
      taskId: config.taskId,
      status: isTimeout ? 'timeout' : 'failed',
      result: err instanceof Error ? err.message : String(err),
      toolsUsed: [],
      duration: Date.now() - startTime,
    }
  } finally {
    activeWorkers.delete(config.taskId)
  }
}

/**
 * Return a snapshot of currently running workers. Safe to call from any
 * concurrent context — returns copies, not live references.
 */
export function getActiveWorkers(): WorkerConfig[] {
  return Array.from(activeWorkers.values()).map(
    ({ abortController: _ac, executor: _ex, ...config }: ActiveWorker & { executor?: WorkerExecutor }) => config,
  )
}

/**
 * Abort a running worker by taskId. Returns true if the worker existed and
 * was aborted, false if it was not found (already finished or never started).
 */
export function killWorker(taskId: string): boolean {
  const worker = activeWorkers.get(taskId)
  if (!worker) {
    return false
  }
  worker.abortController.abort()
  activeWorkers.delete(taskId)
  return true
}
