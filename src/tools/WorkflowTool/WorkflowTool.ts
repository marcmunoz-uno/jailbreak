import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { WORKFLOW_TOOL_NAME } from './constants.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    workflow_id: z
      .string()
      .describe('The ID or name of the workflow to run'),
    args: z
      .record(z.string(), z.unknown())
      .optional()
      .describe('Optional arguments to pass to the workflow'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  workflow_id: string
  status: 'started' | 'completed' | 'failed'
  message: string
}

export const WorkflowTool = buildTool({
  name: WORKFLOW_TOOL_NAME,
  searchHint: 'run a workflow script',
  maxResultSizeChars: 100_000,
  userFacingName() {
    return 'Workflow'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  isReadOnly() {
    return false
  },
  async description() {
    return 'Run a workflow script by ID or name'
  },
  async prompt() {
    return 'Run a named workflow script with optional arguments.'
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: `Workflow ${output.workflow_id}: ${output.message}`,
    }
  },
  async call({ workflow_id }) {
    return {
      data: {
        workflow_id,
        status: 'completed' as const,
        message: 'Workflow completed successfully',
      },
    }
  },
} satisfies ToolDef<InputSchema, Output>)
