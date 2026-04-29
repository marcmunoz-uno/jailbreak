import { randomUUID } from 'crypto'

export interface DreamConfig {
  enabled: boolean
  maxDuration: number    // ms — total wall-clock budget for one dream session
  maxTokenBudget: number // approximate token ceiling across all tasks
  taskQueue: DreamTask[]
}

export interface DreamTask {
  id: string
  description: string
  priority: number                                      // higher = earlier
  status: 'queued' | 'running' | 'completed' | 'failed'
  result?: string
  startedAt?: number
  completedAt?: number
}

// Rough token estimate per task used for budget accounting. The real count is
// only available after the model call, so we estimate 2 k output + read input.
const TOKENS_PER_TASK_ESTIMATE = 3_000

const DEFAULT_CONFIG: DreamConfig = {
  enabled: true,
  maxDuration: 30 * 60_000,  // 30 minutes
  maxTokenBudget: 100_000,
  taskQueue: [],
}

export class DreamEngine {
  private config: DreamConfig
  private dreaming = false
  private tokensUsed = 0
  private completedTasks: DreamTask[] = []
  private stopRequested = false
  private abortController: AbortController | null = null

  constructor(config: DreamConfig) {
    this.config = {
      ...DEFAULT_CONFIG,
      ...config,
      taskQueue: [...(config.taskQueue ?? [])],
    }
  }

  /** Begin processing the task queue in priority order. Resolves when the
   *  queue is exhausted, the token budget is spent, or stop() is called. */
  async start(): Promise<void> {
    if (!this.config.enabled || this.dreaming) return
    this.dreaming = true
    this.stopRequested = false
    this.abortController = new AbortController()

    const deadline = Date.now() + this.config.maxDuration

    try {
      while (!this.stopRequested && Date.now() < deadline) {
        const task = this.nextTask()
        if (!task) break
        if (this.tokensUsed + TOKENS_PER_TASK_ESTIMATE > this.config.maxTokenBudget) break

        task.status = 'running'
        task.startedAt = Date.now()

        try {
          const result = await this.executeTask(task, this.abortController.signal)
          task.status = 'completed'
          task.result = result
          task.completedAt = Date.now()
          this.tokensUsed += TOKENS_PER_TASK_ESTIMATE
          this.completedTasks.push(task)
        } catch (err: unknown) {
          task.status = 'failed'
          task.result = err instanceof Error ? err.message : String(err)
          task.completedAt = Date.now()
          this.completedTasks.push(task)
          if (this.stopRequested) break
        }
      }
    } finally {
      this.dreaming = false
      this.abortController = null
    }
  }

  /** Gracefully stop after the current task finishes. */
  async stop(): Promise<void> {
    this.stopRequested = true
    this.abortController?.abort()
    // Wait for the dreaming flag to clear (start() sets it to false in finally).
    const waitForIdle = (): Promise<void> =>
      new Promise(resolve => {
        const poll = (): void => {
          if (!this.dreaming) {
            resolve()
          } else {
            setTimeout(poll, 100)
          }
        }
        poll()
      })
    await waitForIdle()
  }

  /** Add a task to the queue. Higher priority tasks run first. */
  addTask(description: string, priority = 0): DreamTask {
    const task: DreamTask = {
      id: randomUUID(),
      description,
      priority,
      status: 'queued',
    }
    this.config.taskQueue.push(task)
    return task
  }

  /** All tasks currently waiting to run. */
  getQueue(): DreamTask[] {
    return this.config.taskQueue
      .filter(t => t.status === 'queued' || t.status === 'running')
      .slice()
      .sort((a, b) => b.priority - a.priority)
  }

  /** Completed and failed tasks with their results. */
  getResults(): DreamTask[] {
    return [...this.completedTasks]
  }

  getStatus(): {
    dreaming: boolean
    queue: number
    completed: number
    tokenBudget: { used: number; max: number }
  } {
    return {
      dreaming: this.dreaming,
      queue: this.config.taskQueue.filter(t => t.status === 'queued').length,
      completed: this.completedTasks.length,
      tokenBudget: { used: this.tokensUsed, max: this.config.maxTokenBudget },
    }
  }

  // ---- private ----

  private nextTask(): DreamTask | undefined {
    const queued = this.config.taskQueue
      .filter(t => t.status === 'queued')
      .sort((a, b) => b.priority - a.priority)
    return queued[0]
  }

  private async executeTask(task: DreamTask, signal: AbortSignal): Promise<string> {
    // Dynamically import to avoid circular deps at module load time.
    const { runWorker } = await import('./coordinator/workerAgent.js')

    const result = await runWorker({
      taskId: task.id,
      task: task.description,
      allowedTools: [],
      timeout: Math.min(10 * 60_000, this.config.maxDuration),
    })

    if (signal.aborted) {
      throw new Error('dream stopped')
    }

    if (result.status === 'failed') {
      throw new Error(result.result)
    }
    if (result.status === 'timeout') {
      throw new Error(`task timed out after ${result.duration}ms`)
    }

    return result.result
  }
}

export function createDreamEngine(config?: Partial<DreamConfig>): DreamEngine {
  return new DreamEngine({
    ...DEFAULT_CONFIG,
    ...(config ?? {}),
    taskQueue: config?.taskQueue ?? [],
  })
}
