import type { SystemPrompt } from './systemPromptType.js'
import type { ToolUseContext } from '../Tool.js'

export type MaybeGenerateTaskSummaryOptions = {
  systemPrompt: SystemPrompt
  userContext: string
  systemContext: string
  toolUseContext: ToolUseContext
  forkContextMessages: unknown[]
}

export function shouldGenerateTaskSummary(): boolean {
  return false
}

export async function maybeGenerateTaskSummary(
  _options: MaybeGenerateTaskSummaryOptions,
): Promise<void> {
  // stub: no-op
}
