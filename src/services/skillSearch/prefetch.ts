import type { ToolUseContext } from '../../Tool.js'
import type { Message } from '../../types/message.js'

export type SkillDiscoveryPrefetch = Promise<never[]>

/**
 * Start a prefetch for skill discovery based on the current message context.
 * Returns a promise that resolves to skill discovery attachments.
 */
export function startSkillDiscoveryPrefetch(
  _signal: null,
  _messages: Message[],
  _context: ToolUseContext,
): SkillDiscoveryPrefetch {
  return Promise.resolve([])
}

/**
 * Collect the results of a skill discovery prefetch.
 * Returns any skill attachment messages to inject into the context.
 */
export async function collectSkillDiscoveryPrefetch(
  _pending: SkillDiscoveryPrefetch,
): Promise<never[]> {
  return []
}
