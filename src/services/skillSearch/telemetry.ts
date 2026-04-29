/**
 * Telemetry helpers for remote skill loading events.
 */

export type RemoteSkillLoadedEvent = {
  slug: string
  cacheHit: boolean
  latencyMs: number
  urlScheme?: string
  error?: string
  fileCount?: number
  totalBytes?: number
  fetchMethod?: string
}

/**
 * Log a remote skill loaded event for analytics.
 */
export function logRemoteSkillLoaded(_event: RemoteSkillLoadedEvent): void {
  // no-op stub
}
