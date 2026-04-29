import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { isBriefEnabled } from '../BriefTool/BriefTool.js'
import {
  validateAttachmentPaths,
  resolveAttachments,
  type ResolvedAttachment,
} from '../BriefTool/attachments.js'
import {
  SEND_USER_FILE_TOOL_NAME,
  SEND_USER_FILE_DESCRIPTION,
  SEND_USER_FILE_PROMPT,
} from './prompt.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    paths: z
      .array(z.string())
      .describe('File paths to deliver (absolute or relative to cwd)'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

const outputSchema = lazySchema(() =>
  z.object({
    files: z.array(
      z.object({
        path: z.string(),
        size: z.number(),
        isImage: z.boolean(),
        file_uuid: z.string().optional(),
      }),
    ).describe('Resolved file metadata'),
  }),
)
type OutputSchema = ReturnType<typeof outputSchema>

export type Output = { files: ResolvedAttachment[] }

export const SendUserFileTool = buildTool({
  name: SEND_USER_FILE_TOOL_NAME,
  searchHint: 'deliver files directly to the user',
  maxResultSizeChars: 100_000,
  userFacingName: () => 'Send File',
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  get outputSchema(): OutputSchema {
    return outputSchema()
  },
  isEnabled() {
    return isBriefEnabled()
  },
  isConcurrencySafe() {
    return true
  },
  isReadOnly() {
    return true
  },
  async validateInput({ paths }, _context) {
    return validateAttachmentPaths(paths)
  },
  async description() {
    return SEND_USER_FILE_DESCRIPTION
  },
  async prompt() {
    return SEND_USER_FILE_PROMPT
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    const n = output.files.length
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: `Delivered ${n} file${n === 1 ? '' : 's'} to user`,
    }
  },
  renderToolUseMessage: undefined,
  renderToolResultMessage: undefined,
  async call({ paths }, context) {
    const appState = context.getAppState()
    const files = await resolveAttachments(paths, {
      replBridgeEnabled: appState.replBridgeEnabled,
      signal: context.abortController.signal,
    })
    return { data: { files } }
  },
} satisfies ToolDef<InputSchema, Output>)
