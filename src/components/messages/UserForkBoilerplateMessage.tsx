import type { TextBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import * as React from 'react'
import { Box, Text } from '../../ink.js'

type Props = {
  addMargin: boolean
  param: TextBlockParam
}

export function UserForkBoilerplateMessage({ addMargin, param }: Props): React.ReactNode {
  // Extract the directive from inside <fork-boilerplate> tags, showing only
  // what the subagent was asked to do rather than the full boilerplate.
  const text = param.text
  const directiveMatch = text.match(/<fork-directive>([\s\S]*?)<\/fork-directive>/)
  const displayText = directiveMatch ? directiveMatch[1].trim() : text

  return (
    <Box marginTop={addMargin ? 1 : 0}>
      <Text dimColor>[fork] </Text>
      <Text>{displayText}</Text>
    </Box>
  )
}
