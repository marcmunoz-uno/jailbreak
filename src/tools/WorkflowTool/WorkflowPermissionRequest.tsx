import React from 'react'
import { Box, Text } from '../../ink.js'

type Props = {
  input?: unknown
  onAllow?: () => void
  onDeny?: () => void
}

/**
 * WorkflowPermissionRequest — permission prompt for workflow tool execution.
 * Stub implementation.
 */
export function WorkflowPermissionRequest({
  input: _input,
  onAllow: _onAllow,
  onDeny: _onDeny,
}: Props): React.ReactElement | null {
  return (
    <Box>
      <Text>Workflow permission requested</Text>
    </Box>
  )
}
