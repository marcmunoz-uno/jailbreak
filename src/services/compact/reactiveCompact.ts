// Stub implementation of reactive compact service.
// All gates return false; tryReactiveCompact is a no-op.

export function isReactiveCompactEnabled(): boolean {
  return false
}

export function isWithheldPromptTooLong(_message: unknown): boolean {
  return false
}

export function isWithheldMediaSizeError(_message: unknown): boolean {
  return false
}

export async function tryReactiveCompact(_opts: {
  hasAttempted: boolean
  querySource: unknown
  aborted: boolean
  messages: unknown[]
  cacheSafeParams: {
    systemPrompt: unknown
    userContext: unknown
    systemContext: unknown
    toolUseContext: unknown
    forkContextMessages: unknown[]
  }
}): Promise<undefined> {
  return undefined
}
