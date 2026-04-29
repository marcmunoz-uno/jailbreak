import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { isProactiveActive } from '../../proactive/index.js'
import { SLEEP_TOOL_NAME, DESCRIPTION, SLEEP_TOOL_PROMPT } from './prompt.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    duration_ms: z
      .number()
      .min(100)
      .max(300_000)
      .describe('Duration to sleep in milliseconds (100–300000)'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

const outputSchema = lazySchema(() =>
  z.object({
    slept_ms: z.number().describe('Actual milliseconds elapsed'),
    interrupted: z.boolean().describe('Whether the sleep was interrupted by an abort signal'),
  }),
)
type OutputSchema = ReturnType<typeof outputSchema>

export type Output = z.infer<OutputSchema>

export const SleepTool = buildTool({
  name: SLEEP_TOOL_NAME,
  searchHint: 'pause execution for a specified duration',
  maxResultSizeChars: 100_000,
  userFacingName: () => 'Sleep',
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  get outputSchema(): OutputSchema {
    return outputSchema()
  },
  isEnabled() {
    return isProactiveActive()
  },
  isConcurrencySafe() {
    return true
  },
  isReadOnly() {
    return true
  },
  async description() {
    return DESCRIPTION
  },
  async prompt() {
    return SLEEP_TOOL_PROMPT
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    const text = output.interrupted
      ? `Sleep interrupted after ${output.slept_ms}ms`
      : `Slept for ${output.slept_ms}ms`
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: text,
    }
  },
  async call({ duration_ms }, context) {
    const start = Date.now()
    const signal = context.abortController.signal

    await new Promise<void>(resolve => {
      if (signal.aborted) {
        resolve()
        return
      }
      const timer = setTimeout(resolve, duration_ms)
      signal.addEventListener('abort', () => {
        clearTimeout(timer)
        resolve()
      }, { once: true })
    })

    const slept_ms = Date.now() - start
    const interrupted = signal.aborted && slept_ms < duration_ms

    return {
      data: { slept_ms, interrupted },
    }
  },
} satisfies ToolDef<InputSchema, Output>)
