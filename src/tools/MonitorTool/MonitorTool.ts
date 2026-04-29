import { execSync } from 'child_process'
import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    target: z
      .enum(['files', 'processes', 'resources'])
      .describe('What to monitor: files, processes, or system resources'),
    path: z
      .string()
      .optional()
      .describe('Directory path to watch for file changes (used when target is "files")'),
    interval_seconds: z
      .number()
      .int()
      .min(1)
      .max(3600)
      .optional()
      .describe('Interval in seconds for monitoring (informational only, returns a snapshot)'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  target: string
  snapshot: string
  timestamp: string
}

const MONITOR_TOOL_NAME = 'monitor_tool'

export const MonitorTool = buildTool({
  name: MONITOR_TOOL_NAME,
  searchHint: 'monitor file changes, process health, and system resource usage',
  maxResultSizeChars: 100_000,
  async description(input) {
    const { target } = input as { target: string }
    return `Claude wants to monitor system ${target}`
  },
  userFacingName() {
    return 'Monitor'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  isReadOnly() {
    return true
  },
  async checkPermissions(_input, _context) {
    return {
      behavior: 'allow' as const,
      decisionReason: { type: 'other' as const, reason: 'auto' },
    }
  },
  async call(input) {
    const { target, path } = input
    const timestamp = new Date().toISOString()

    let snapshot: string

    switch (target) {
      case 'files': {
        const dir = path ?? '.'
        try {
          snapshot = execSync(
            `find ${JSON.stringify(dir)} -newer /tmp/.monitor_ref -maxdepth 3 2>/dev/null || echo "(no recent changes)"`,
            { encoding: 'utf8', timeout: 10_000 },
          ).trim()
          if (!snapshot) {
            snapshot = '(no recent file changes detected)'
          }
        } catch {
          snapshot = `(unable to read directory: ${dir})`
        }
        break
      }
      case 'processes': {
        try {
          snapshot = execSync('ps aux', {
            encoding: 'utf8',
            timeout: 10_000,
          }).trim()
        } catch {
          snapshot = '(unable to list processes)'
        }
        break
      }
      case 'resources': {
        const lines: string[] = []
        try {
          const topOut = execSync('top -l 1 -n 0', {
            encoding: 'utf8',
            timeout: 10_000,
          }).trim()
          lines.push('=== top ===', topOut)
        } catch {
          lines.push('(top unavailable)')
        }
        try {
          const vmOut = execSync('vm_stat', {
            encoding: 'utf8',
            timeout: 10_000,
          }).trim()
          lines.push('', '=== vm_stat ===', vmOut)
        } catch {
          lines.push('(vm_stat unavailable)')
        }
        snapshot = lines.join('\n')
        break
      }
    }

    return {
      data: { target, snapshot, timestamp },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: `[Monitor: ${output.target} @ ${output.timestamp}]\n${output.snapshot}`,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
