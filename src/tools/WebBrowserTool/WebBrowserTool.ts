import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    url: z.string().url().describe('The URL to load in the browser'),
    action: z
      .enum(['fetch', 'screenshot', 'extract'])
      .describe(
        'Action to perform: fetch returns page text, extract uses a CSS selector, screenshot requires puppeteer',
      ),
    selector: z
      .string()
      .optional()
      .describe('CSS selector to extract content (used when action is "extract")'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  content: string
  title?: string
  url: string
}

const WEB_BROWSER_TOOL_NAME = 'web_browser_tool'

function stripHtmlTags(html: string): string {
  // Remove script and style blocks
  let text = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ')
  // Replace block elements with newlines
  text = text.replace(/<\/?(p|div|h[1-6]|br|li|tr|td|th)[^>]*>/gi, '\n')
  // Strip remaining tags
  text = text.replace(/<[^>]+>/g, '')
  // Decode common HTML entities
  text = text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, ' ')
  // Collapse whitespace
  return text.replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim()
}

function extractTitle(html: string): string | undefined {
  const match = html.match(/<title[^>]*>([^<]*)<\/title>/i)
  return match ? match[1]?.trim() : undefined
}

function extractBySelector(html: string, selector: string): string {
  // Minimal CSS selector extraction without a DOM parser.
  // Supports simple tag, .class, #id, and tag.class patterns.
  const tagMatch = selector.match(/^([a-z][a-z0-9]*)?(?:#([^.[\s]+))?(?:\.([^#[\s]+))?$/i)
  if (!tagMatch) {
    return '(unsupported selector — use fetch action for full text)'
  }

  const [, tag, id, cls] = tagMatch

  let pattern: RegExp
  if (tag && id) {
    pattern = new RegExp(`<${tag}[^>]*\\sid="${id}"[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i')
  } else if (tag && cls) {
    pattern = new RegExp(`<${tag}[^>]*\\sclass="[^"]*${cls}[^"]*"[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i')
  } else if (id) {
    pattern = new RegExp(`<[a-z][a-z0-9]*[^>]*\\sid="${id}"[^>]*>([\\s\\S]*?)<\\/[a-z][a-z0-9]*>`, 'i')
  } else if (cls) {
    pattern = new RegExp(`<[a-z][a-z0-9]*[^>]*\\sclass="[^"]*${cls}[^"]*"[^>]*>([\\s\\S]*?)<\\/[a-z][a-z0-9]*>`, 'i')
  } else if (tag) {
    pattern = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'i')
  } else {
    return '(could not parse selector)'
  }

  const match = html.match(pattern)
  return match ? stripHtmlTags(match[1] ?? '') : '(selector matched no elements)'
}

export const WebBrowserTool = buildTool({
  name: WEB_BROWSER_TOOL_NAME,
  searchHint: 'fetch and extract web page content using a browser',
  maxResultSizeChars: 100_000,
  async description(input) {
    const { url, action } = input as { url: string; action: string }
    try {
      const hostname = new URL(url).hostname
      return `Claude wants to ${action} content from ${hostname}`
    } catch {
      return `Claude wants to ${action} content from a web page`
    }
  },
  userFacingName() {
    return 'Web Browser'
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
  async call(input, context) {
    const { url, action, selector } = input

    if (action === 'screenshot') {
      return {
        data: {
          content:
            'Screenshot action requires puppeteer which is not installed. Use action "fetch" or "extract" instead.',
          url,
        },
      }
    }

    const response = await fetch(url, {
      signal: context.abortController.signal,
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      },
    })

    const html = await response.text()
    const title = extractTitle(html)

    let content: string
    if (action === 'extract' && selector) {
      content = extractBySelector(html, selector)
    } else {
      content = stripHtmlTags(html)
    }

    return {
      data: { content, title, url },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    const header = output.title
      ? `Title: ${output.title}\nURL: ${output.url}\n\n`
      : `URL: ${output.url}\n\n`
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: header + output.content,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
