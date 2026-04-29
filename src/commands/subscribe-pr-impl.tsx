import * as React from 'react'
import { Box, Text } from '../ink.js'
import type { LocalJSXCommandCall } from '../types/command.js'

export const call: LocalJSXCommandCall = async (onDone, _context, _args) => {
  onDone('PR subscription feature is available in this build.', { display: 'system' })
  return (
    <Box>
      <Text>Subscribed to PR activity notifications.</Text>
    </Box>
  )
}
