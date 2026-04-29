import type { AttributionData } from './commitAttribution.js'
import type { AttributionState } from './commitAttribution.js'

/**
 * Build git trailer lines for squash-merge survival.
 * These become proper git trailers on squash commits when
 * squash_merge_commit_message=PR_BODY is configured.
 */
export function buildPRTrailers(
  attributionData: AttributionData,
  attribution: AttributionState | null | undefined,
): string[] {
  const trailers: string[] = []

  const claudePercent = attributionData.summary.claudePercent
  if (claudePercent > 0) {
    trailers.push(`Claude-Percent: ${claudePercent}`)
  }

  const surfaces = attributionData.summary.surfaces
  if (surfaces.length > 0) {
    trailers.push(`Claude-Surface: ${surfaces.join(', ')}`)
  }

  if (attribution?.promptCount && attribution.promptCount > 0) {
    trailers.push(`Claude-Prompts: ${attribution.promptCount}`)
  }

  trailers.push('Co-Authored-By: Claude <noreply@anthropic.com>')

  return trailers
}
