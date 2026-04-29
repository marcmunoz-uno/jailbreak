import type { TextBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import * as React from 'react'
import { Box, Text } from '../../ink.js'

type Props = {
  addMargin: boolean
  param: TextBlockParam
}

export function UserGitHubWebhookMessage({ addMargin, param }: Props): React.ReactNode {
  // Extract inner content from <github-webhook-activity> tag
  const text = param.text
  const innerMatch = text.match(/<github-webhook-activity>([\s\S]*?)<\/github-webhook-activity>/)
  const content = innerMatch ? innerMatch[1].trim() : text

  return (
    <Box marginTop={addMargin ? 1 : 0} flexDirection="column">
      <Text bold color="yellow">[GitHub Webhook] </Text>
      <Text>{content}</Text>
    </Box>
  )
}
