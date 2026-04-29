import { execSync } from 'child_process'
import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    repo: z
      .string()
      .describe('Repository in "owner/repo" format (e.g. "anthropics/claude-code")'),
    pr_number: z
      .number()
      .int()
      .positive()
      .optional()
      .describe('PR number to inspect. If omitted, lists open PRs.'),
    events: z
      .array(z.string())
      .optional()
      .describe('Event types to filter (e.g. ["review", "check"])'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type CheckRun = {
  name: string
  status: string
  conclusion: string | null
}

type Review = {
  author: string
  state: string
  body: string
}

type Output = {
  status: string
  checks: CheckRun[]
  reviews: Review[]
  pr_number?: number
  title?: string
  url?: string
}

const SUBSCRIBE_PR_TOOL_NAME = 'kairos_github_webhooks'

export const SubscribePRTool = buildTool({
  name: SUBSCRIBE_PR_TOOL_NAME,
  searchHint: 'subscribe to GitHub PR events and check PR status',
  maxResultSizeChars: 100_000,
  async description(input) {
    const { repo, pr_number } = input as { repo: string; pr_number?: number }
    return pr_number
      ? `Claude wants to check PR #${pr_number} in ${repo}`
      : `Claude wants to list open PRs in ${repo}`
  },
  userFacingName() {
    return 'GitHub PR'
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
    const { repo, pr_number } = input

    if (!pr_number) {
      // List open PRs
      let listOutput: string
      try {
        listOutput = execSync(
          `gh pr list --repo ${JSON.stringify(repo)} --json number,title,state,url`,
          { encoding: 'utf8', timeout: 30_000 },
        ).trim()
      } catch (err) {
        return {
          data: {
            status: `error: ${err instanceof Error ? err.message : String(err)}`,
            checks: [],
            reviews: [],
          },
        }
      }

      return {
        data: {
          status: listOutput,
          checks: [],
          reviews: [],
        },
      }
    }

    // Get PR details
    let prJson: string
    try {
      prJson = execSync(
        `gh pr view ${pr_number} --repo ${JSON.stringify(repo)} --json title,state,url,statusCheckRollup,reviews`,
        { encoding: 'utf8', timeout: 30_000 },
      ).trim()
    } catch (err) {
      return {
        data: {
          status: `error: ${err instanceof Error ? err.message : String(err)}`,
          checks: [],
          reviews: [],
          pr_number,
        },
      }
    }

    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(prJson) as Record<string, unknown>
    } catch {
      return {
        data: {
          status: 'error: failed to parse gh output',
          checks: [],
          reviews: [],
          pr_number,
        },
      }
    }

    const checks: CheckRun[] = []
    const rawChecks = parsed['statusCheckRollup']
    if (Array.isArray(rawChecks)) {
      for (const c of rawChecks) {
        const check = c as Record<string, unknown>
        checks.push({
          name: String(check['name'] ?? check['context'] ?? ''),
          status: String(check['status'] ?? check['state'] ?? ''),
          conclusion: check['conclusion'] != null ? String(check['conclusion']) : null,
        })
      }
    }

    const reviews: Review[] = []
    const rawReviews = parsed['reviews']
    if (Array.isArray(rawReviews)) {
      for (const r of rawReviews) {
        const rev = r as Record<string, unknown>
        const author = rev['author'] as Record<string, unknown> | undefined
        reviews.push({
          author: String(author?.['login'] ?? ''),
          state: String(rev['state'] ?? ''),
          body: String(rev['body'] ?? ''),
        })
      }
    }

    return {
      data: {
        status: String(parsed['state'] ?? 'unknown'),
        checks,
        reviews,
        pr_number,
        title: parsed['title'] ? String(parsed['title']) : undefined,
        url: parsed['url'] ? String(parsed['url']) : undefined,
      },
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    const lines: string[] = []

    if (output.title) {
      lines.push(`PR #${output.pr_number}: ${output.title}`)
      lines.push(`Status: ${output.status}`)
      if (output.url) lines.push(`URL: ${output.url}`)
    } else {
      lines.push(output.status)
    }

    if (output.checks.length > 0) {
      lines.push('\nChecks:')
      for (const c of output.checks) {
        lines.push(`  ${c.name}: ${c.status}${c.conclusion ? ` (${c.conclusion})` : ''}`)
      }
    }

    if (output.reviews.length > 0) {
      lines.push('\nReviews:')
      for (const r of output.reviews) {
        lines.push(`  ${r.author}: ${r.state}`)
      }
    }

    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: lines.join('\n'),
    }
  },
} satisfies ToolDef<InputSchema, Output>)
