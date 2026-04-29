import { randomUUID } from 'crypto'

export interface DaemonConfig {
  pollInterval: number    // ms between task-source polls
  maxConcurrent: number   // max simultaneous workers
  taskSource: 'mcp' | 'file' | 'http'
  taskEndpoint?: string   // URL or path, depending on taskSource
}

export interface RegisteredWorker {
  id: string
  status: 'idle' | 'busy' | 'error'
  currentTask?: string
  startedAt?: number
}

// Pending task handed from a source poller to a worker slot.
interface PendingTask {
  id: string
  description: string
  createdAt: number
}

export class WorkerRegistry {
  private readonly config: DaemonConfig
  private workers: Map<string, RegisteredWorker> = new Map()
  private running = false
  private pollTimer: ReturnType<typeof setTimeout> | null = null
  private tasksCompleted = 0

  constructor(config: DaemonConfig) {
    this.config = config
    // Pre-allocate idle worker slots.
    for (let i = 0; i < config.maxConcurrent; i++) {
      const id = `worker-${randomUUID().slice(0, 8)}`
      this.workers.set(id, { id, status: 'idle' })
    }
  }

  /** Begin polling the configured task source for work. */
  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    this.schedulePoll()
  }

  /** Stop polling and wait for in-flight workers to finish. */
  async stop(): Promise<void> {
    this.running = false
    if (this.pollTimer !== null) {
      clearTimeout(this.pollTimer)
      this.pollTimer = null
    }
    // Wait until all busy workers become idle or error.
    await this.drainWorkers()
  }

  getWorkers(): RegisteredWorker[] {
    return Array.from(this.workers.values())
  }

  getStatus(): { running: boolean; workers: number; tasksCompleted: number } {
    return {
      running: this.running,
      workers: this.workers.size,
      tasksCompleted: this.tasksCompleted,
    }
  }

  // ---- private ----

  private schedulePoll(): void {
    if (!this.running) return
    this.pollTimer = setTimeout(() => {
      void this.poll().then(() => this.schedulePoll())
    }, this.config.pollInterval)
  }

  private async poll(): Promise<void> {
    const idleSlots = this.idleWorkers()
    if (idleSlots.length === 0) return

    const tasks = await this.fetchTasks(idleSlots.length)
    for (let i = 0; i < Math.min(tasks.length, idleSlots.length); i++) {
      void this.dispatch(idleSlots[i]!, tasks[i]!)
    }
  }

  private idleWorkers(): RegisteredWorker[] {
    return Array.from(this.workers.values()).filter(w => w.status === 'idle')
  }

  private async fetchTasks(max: number): Promise<PendingTask[]> {
    try {
      switch (this.config.taskSource) {
        case 'file':
          return await this.fetchFromFile(max)
        case 'http':
          return await this.fetchFromHttp(max)
        case 'mcp':
          return await this.fetchFromMcp(max)
        default:
          return []
      }
    } catch {
      // Source unavailable — return empty; next poll will retry.
      return []
    }
  }

  private async fetchFromFile(max: number): Promise<PendingTask[]> {
    const { readFile, writeFile } = await import('fs/promises')
    const path = this.config.taskEndpoint ?? '/tmp/daemon-tasks.json'
    let raw: string
    try {
      raw = await readFile(path, 'utf8')
    } catch {
      return []
    }
    const all: Array<{ id?: string; description: string }> = JSON.parse(raw)
    const batch = all.slice(0, max)
    // Remove consumed tasks from the file.
    await writeFile(path, JSON.stringify(all.slice(batch.length)), 'utf8')
    return batch.map(t => ({
      id: t.id ?? randomUUID(),
      description: t.description,
      createdAt: Date.now(),
    }))
  }

  private async fetchFromHttp(max: number): Promise<PendingTask[]> {
    const endpoint = this.config.taskEndpoint
    if (!endpoint) return []
    const response = await fetch(`${endpoint}?limit=${max}`, { method: 'GET' })
    if (!response.ok) return []
    const data: Array<{ id?: string; description: string }> = await response.json()
    return data.map(t => ({
      id: t.id ?? randomUUID(),
      description: t.description,
      createdAt: Date.now(),
    }))
  }

  private async fetchFromMcp(_max: number): Promise<PendingTask[]> {
    // MCP task source: tasks arrive via the MCP message queue in the parent
    // process. The daemon polls a shared in-memory queue populated by the
    // MCP server handler. Placeholder — concrete integration depends on the
    // MCP runtime available in the embedding process.
    return []
  }

  private async dispatch(worker: RegisteredWorker, task: PendingTask): Promise<void> {
    this.updateWorker(worker.id, { status: 'busy', currentTask: task.description, startedAt: Date.now() })
    try {
      const { runWorker } = await import('../coordinator/workerAgent.js')
      await runWorker({
        taskId: task.id,
        task: task.description,
        allowedTools: [],
      })
      this.tasksCompleted++
      this.updateWorker(worker.id, { status: 'idle', currentTask: undefined, startedAt: undefined })
    } catch {
      this.updateWorker(worker.id, { status: 'error', currentTask: undefined, startedAt: undefined })
      // Reset error worker after a brief back-off so the slot is reusable.
      setTimeout(() => {
        this.updateWorker(worker.id, { status: 'idle' })
      }, 5000)
    }
  }

  private updateWorker(id: string, patch: Partial<RegisteredWorker>): void {
    const existing = this.workers.get(id)
    if (existing) {
      this.workers.set(id, { ...existing, ...patch })
    }
  }

  private async drainWorkers(): Promise<void> {
    const pollUntilIdle = (): Promise<void> =>
      new Promise(resolve => {
        const check = (): void => {
          const anyBusy = Array.from(this.workers.values()).some(w => w.status === 'busy')
          if (!anyBusy) {
            resolve()
          } else {
            setTimeout(check, 250)
          }
        }
        check()
      })
    await pollUntilIdle()
  }
}

export function createDaemon(config: DaemonConfig): WorkerRegistry {
  return new WorkerRegistry(config)
}

export async function runDaemonWorker(_kind: string | undefined): Promise<void> {
  console.error('daemon worker not available in external build')
}
