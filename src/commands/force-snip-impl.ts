import { snipCompactIfNeeded } from '../services/compact/snipCompact.js'
import type { LocalCommandCall } from '../types/command.js'

export const call: LocalCommandCall = async (_args, context) => {
  const messages = context.getMessages()
  const result = snipCompactIfNeeded(messages, { force: true })
  return {
    type: 'text',
    value: result.executed
      ? `Snipped context, freed ${result.tokensFreed} tokens.`
      : 'No context was snipped.',
  }
}
