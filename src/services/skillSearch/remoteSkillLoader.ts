/**
 * Remote skill loader — fetches and caches remote skill content.
 */

export type RemoteSkillLoadResult = {
  cacheHit: boolean
  latencyMs: number
  skillPath: string
  content: string
  fileCount: number
  totalBytes: number
  fetchMethod: string
}

/**
 * Load a remote skill by slug and URL.
 * Fetches the skill content and returns it with cache metadata.
 */
export async function loadRemoteSkill(
  _slug: string,
  _url: string,
): Promise<RemoteSkillLoadResult> {
  throw new Error('Remote skill loading is not supported in this build')
}
