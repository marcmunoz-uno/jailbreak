/**
 * Remote skill state management.
 * Tracks discovered remote skills within a session.
 */

export type RemoteSkillMeta = {
  url: string
  name: string
  description?: string
}

/**
 * Strip the canonical prefix from a skill name to get the slug.
 * Returns null if the name does not match the canonical prefix format.
 */
export function stripCanonicalPrefix(_name: string): string | null {
  return null
}

/**
 * Get a discovered remote skill by slug.
 * Returns undefined if the skill was not discovered in this session.
 */
export function getDiscoveredRemoteSkill(
  _slug: string,
): RemoteSkillMeta | undefined {
  return undefined
}
