import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() => z.strictObject({}))
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  messageCount: number
  info: string
}

export const CtxInspectTool = buildTool({
  name: 'ctx_inspect',
  searchHint: 'inspect current context size and message counts',
  maxResultSizeChars: 10_000,
  userFacingName() {
    return 'Inspect Context'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  isReadOnly() {
    return true
  },
  async description() {
    return 'Inspect the current conversation context size and message counts'
  },
  async prompt() {
    return 'Use ctx_inspect to check how many messages are in the current context window.'
  },
  async call(_input, { getAppState }) {
    const state = getAppState()
    const messageCount =
      (state as Record<string, unknown>).messages instanceof Array
        ? ((state as Record<string, unknown>).messages as unknown[]).length
        : 0
    return {
      data: {
        messageCount,
        info: `Context contains ${messageCount} messages.`,
      },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: output.info,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
