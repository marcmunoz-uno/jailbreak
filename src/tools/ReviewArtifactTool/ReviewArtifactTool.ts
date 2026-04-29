import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    artifact: z
      .string()
      .describe('The artifact to review — a file path, PR URL, or commit SHA'),
    focus: z
      .string()
      .optional()
      .describe(
        'Optional: specific area to focus the review on (e.g. security, performance)',
      ),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  artifact: string
  review: string
}

export const ReviewArtifactTool = buildTool({
  name: 'review_artifact',
  searchHint: 'review a code artifact, PR, or commit for quality and issues',
  maxResultSizeChars: 200_000,
  userFacingName() {
    return 'Review Artifact'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  async description({ artifact }) {
    return `Review artifact: ${artifact}`
  },
  async prompt() {
    return 'Use review_artifact to analyze a code artifact, pull request, or commit for bugs, style issues, and correctness.'
  },
  async call({ artifact, focus }) {
    const focusSuffix = focus ? ` (focus: ${focus})` : ''
    return {
      data: {
        artifact,
        review: `Review requested for ${artifact}${focusSuffix}. Use the hunter skill or manual inspection to complete the review.`,
      },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: output.review,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
