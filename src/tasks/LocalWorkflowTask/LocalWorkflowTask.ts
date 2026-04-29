import type { SetAppState, Task, TaskStateBase } from '../../Task.js'
import { createTaskStateBase, generateTaskId } from '../../Task.js'

// A single agent step within a workflow run
export type WorkflowAgent = {
  agentId: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  startTime?: number
  endTime?: number
}

export type LocalWorkflowTaskState = TaskStateBase & {
  type: 'local_workflow'
  workflowId: string
  agents: WorkflowAgent[]
  abortController?: AbortController
}

export function isLocalWorkflowTask(
  task: unknown,
): task is LocalWorkflowTaskState {
  return (
    typeof task === 'object' &&
    task !== null &&
    'type' in task &&
    (task as { type: unknown }).type === 'local_workflow'
  )
}

/**
 * Kill a running workflow task by ID.
 */
export function killWorkflowTask(
  taskId: string,
  setAppState: SetAppState,
): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId]
    if (!task || task.type !== 'local_workflow') return prev
    const workflowTask = task as LocalWorkflowTaskState
    workflowTask.abortController?.abort()
    return {
      ...prev,
      tasks: {
        ...prev.tasks,
        [taskId]: { ...task, status: 'killed' },
      },
    }
  })
}

/**
 * Skip a specific agent within a running workflow.
 */
export function skipWorkflowAgent(
  taskId: string,
  agentId: string,
  setAppState: SetAppState,
): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId]
    if (!task || task.type !== 'local_workflow') return prev
    const workflowTask = task as LocalWorkflowTaskState
    return {
      ...prev,
      tasks: {
        ...prev.tasks,
        [taskId]: {
          ...workflowTask,
          agents: workflowTask.agents.map(a =>
            a.agentId === agentId ? { ...a, status: 'skipped' as const } : a,
          ),
        },
      },
    }
  })
}

/**
 * Retry a specific agent within a running workflow.
 */
export function retryWorkflowAgent(
  taskId: string,
  agentId: string,
  setAppState: SetAppState,
): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId]
    if (!task || task.type !== 'local_workflow') return prev
    const workflowTask = task as LocalWorkflowTaskState
    return {
      ...prev,
      tasks: {
        ...prev.tasks,
        [taskId]: {
          ...workflowTask,
          agents: workflowTask.agents.map(a =>
            a.agentId === agentId ? { ...a, status: 'pending' as const } : a,
          ),
        },
      },
    }
  })
}

export const LocalWorkflowTask: Task = {
  name: 'local_workflow',
  type: 'local_workflow',
  async kill(taskId: string, setAppState: SetAppState): Promise<void> {
    killWorkflowTask(taskId, setAppState)
  },
}
