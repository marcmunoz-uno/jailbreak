import React from 'react'
import type { DeepImmutable } from 'src/types/utils.js'
import type { CommandResultDisplay } from '../../commands.js'
import { Box, Text } from '../../ink.js'
import type { LocalWorkflowTaskState } from '../../tasks/LocalWorkflowTask/LocalWorkflowTask.js'

type Props = {
  workflow: DeepImmutable<LocalWorkflowTaskState>
  onDone: (result?: string, options?: { display: CommandResultDisplay }) => void
  onKill?: () => void
  onSkipAgent?: (agentId: string) => void
  onRetryAgent?: (agentId: string) => void
  onBack?: () => void
}

/**
 * WorkflowDetailDialog — detail view for a running or completed workflow task.
 * Stub implementation — renders basic workflow status.
 */
export function WorkflowDetailDialog({
  workflow,
  onBack,
}: Props): React.ReactElement | null {
  return (
    <Box flexDirection="column">
      <Text>Workflow: {workflow.workflowId}</Text>
      <Text>Status: {workflow.status}</Text>
      {onBack && <Text dimColor>Press Escape to go back</Text>}
    </Box>
  )
}
