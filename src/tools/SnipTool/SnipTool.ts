import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { snipCompactIfNeeded } from '../../services/compact/snipCompact.js'
import { SNIP_TOOL_NAME, SNIP_TOOL_DESCRIPTION, SNIP_TOOL_PROMPT } from './prompt.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    message_id: z
      .string()
      .optional()
      .describe('Optional message ID to snip up to. If omitted, snips the oldest context.'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  tokensFreed: number
  executed: boolean
}

const outputSchema = lazySchema(() =>
  z.object({
    tokensFreed: z.number(),
    executed: z.boolean(),
  }),
)
type OutputSchema = ReturnType<typeof outputSchema>

export const SnipTool = buildTool({
  name: SNIP_TOOL_NAME,
  searchHint: 'remove old conversation context to free up tokens',
  maxResultSizeChars: 1000,
  userFacingName() {
    return 'Snip'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  get outputSchema(): OutputSchema {
    return outputSchema()
  },
  isEnabled() {
    return true
  },
  isConcurrencySafe() {
    return false
  },
  isReadOnly() {
    return false
  },
  async description() {
    return SNIP_TOOL_DESCRIPTION
  },
  async prompt() {
    return SNIP_TOOL_PROMPT
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: output.executed
        ? `Snipped context, freed ${output.tokensFreed} tokens.`
        : 'No context was snipped.',
    }
  },
  async call(_input, context) {
    const messages = context.getMessages()
    const result = snipCompactIfNeeded(messages, { force: true })
    return {
      data: {
        tokensFreed: result.tokensFreed,
        executed: result.executed,
      },
    }
  },
} satisfies ToolDef<InputSchema, Output>)
