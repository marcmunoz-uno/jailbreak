import type { AppState } from '../../state/AppState.js'
import type { SetAppState, TaskStateBase } from '../../Task.js'

export type MonitorMcpTaskState = TaskStateBase & {
  type: 'monitor_mcp'
  agentId?: string
  serverName?: string
}

export function killMonitorMcpTasksForAgent(
  _agentId: string,
  _getAppState: () => AppState,
  _setAppState: SetAppState,
): void {
  // no-op stub
}

export function killMonitorMcp(
  _taskId: string,
  _setAppState: SetAppState,
): void {
  // no-op stub
}
