import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    size_chars: z
      .number()
      .int()
      .min(1)
      .max(10_000_000)
      .describe('Number of characters to generate'),
    pattern: z
      .enum(['lorem', 'code', 'json'])
      .optional()
      .default('lorem')
      .describe('Pattern type to generate: lorem ipsum text, code-like output, or JSON'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  content: string
  actual_size: number
}

const OVERFLOW_TEST_TOOL_NAME = 'overflow_test_tool'

const LOREM_SENTENCE =
  'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. '

const CODE_LINE =
  'const result = await processData(input, { timeout: 5000, retries: 3, verbose: false });\n'

function generateLorem(sizeChars: number): string {
  const chunks: string[] = []
  let remaining = sizeChars
  while (remaining > 0) {
    const chunk =
      remaining >= LOREM_SENTENCE.length
        ? LOREM_SENTENCE
        : LOREM_SENTENCE.slice(0, remaining)
    chunks.push(chunk)
    remaining -= chunk.length
  }
  return chunks.join('')
}

function generateCode(sizeChars: number): string {
  const lines: string[] = []
  let total = 0
  let lineNum = 1
  while (total < sizeChars) {
    const line = `// line ${lineNum}\n${CODE_LINE}`
    if (total + line.length > sizeChars) {
      lines.push(line.slice(0, sizeChars - total))
      break
    }
    lines.push(line)
    total += line.length
    lineNum++
  }
  return lines.join('')
}

function generateJson(sizeChars: number): string {
  const entry = '{"id":1,"value":"placeholder","active":true,"score":0.999},'
  const header = '{"items":['
  const footer = ']}'

  const itemBudget = sizeChars - header.length - footer.length
  if (itemBudget <= 0) {
    return (header + footer).slice(0, sizeChars)
  }

  const items: string[] = []
  let total = 0
  let idx = 0
  while (total < itemBudget) {
    const item = entry.replace('"id":1', `"id":${idx}`)
    const needed = itemBudget - total
    if (item.length > needed) {
      items.push(item.slice(0, needed))
      break
    }
    items.push(item)
    total += item.length
    idx++
  }

  // Remove trailing comma from last entry
  if (items.length > 0) {
    items[items.length - 1] = (items[items.length - 1] ?? '').replace(/,$/, '')
  }

  return header + items.join('') + footer
}

export const OverflowTestTool = buildTool({
  name: OVERFLOW_TEST_TOOL_NAME,
  searchHint: 'generate large outputs to test context overflow and token limits',
  maxResultSizeChars: 10_000_000,
  async description(input) {
    const { size_chars } = input as { size_chars: number }
    return `Claude wants to generate ${size_chars.toLocaleString()} characters to test context overflow`
  },
  userFacingName() {
    return 'Overflow Test'
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
    const { size_chars, pattern = 'lorem' } = input

    let content: string
    switch (pattern) {
      case 'code':
        content = generateCode(size_chars)
        break
      case 'json':
        content = generateJson(size_chars)
        break
      default:
        content = generateLorem(size_chars)
        break
    }

    return {
      data: { content, actual_size: content.length },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: output.content,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
