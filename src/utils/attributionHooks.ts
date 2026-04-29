/**
 * Git commit attribution hooks (COMMIT_ATTRIBUTION).
 *
 * Provides helpers to inject co-author trailers into commit messages and to
 * install / remove a `prepare-commit-msg` hook that does so automatically.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { chmodSync, unlinkSync } from 'fs'
import { join } from 'path'
import { execSync } from 'child_process'

const HOOK_MARKER = '# free-code-attribution-hook'
const HOOK_SCRIPT = `#!/bin/sh
${HOOK_MARKER}
COMMIT_MSG_FILE=$1
CURRENT=$(cat "$COMMIT_MSG_FILE")
if echo "$CURRENT" | grep -q "Co-Authored-By:"; then
  exit 0
fi
printf '\\n\\nCo-Authored-By: Jailbreak Agent <jailbreak@local>' >> "$COMMIT_MSG_FILE"
`

/**
 * Return the co-author trailer line for commits made by this agent.
 */
export function getAttributionTrailer(): string {
  return 'Co-Authored-By: Jailbreak Agent <jailbreak@local>'
}

/**
 * Inject the co-author trailer into a commit message if not already present.
 * Leaves the message unchanged if it already contains a Co-Authored-By line.
 */
export function injectAttribution(commitMessage: string): string {
  if (commitMessage.includes('Co-Authored-By:')) return commitMessage
  return `${commitMessage.trimEnd()}\n\n${getAttributionTrailer()}`
}

/**
 * Resolve the `.git/hooks` directory for the given repo path (or cwd).
 * Handles `core.hooksPath` overrides when git is available.
 */
function resolveHooksDir(repoPath?: string): string {
  const cwd = repoPath ?? process.cwd()
  try {
    const custom = execSync('git config core.hooksPath', {
      cwd,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim()
    if (custom) return custom
  } catch {
    // No custom hooksPath — use the default
  }
  return join(cwd, '.git', 'hooks')
}

/**
 * Install a `prepare-commit-msg` hook that appends the attribution trailer.
 * Skips installation if the hook already contains the marker comment.
 */
export function setupAttributionHook(repoPath?: string): void {
  const hooksDir = resolveHooksDir(repoPath)
  if (!existsSync(hooksDir)) {
    mkdirSync(hooksDir, { recursive: true })
  }

  const hookPath = join(hooksDir, 'prepare-commit-msg')

  if (existsSync(hookPath)) {
    const existing = readFileSync(hookPath, 'utf8')
    if (existing.includes(HOOK_MARKER)) {
      // Already installed — nothing to do
      return
    }
    // Append to existing hook rather than overwriting
    writeFileSync(hookPath, `${existing.trimEnd()}\n\n${HOOK_SCRIPT}`)
  } else {
    writeFileSync(hookPath, HOOK_SCRIPT)
  }

  chmodSync(hookPath, 0o755)
}

/**
 * Remove the attribution hook installed by `setupAttributionHook`.
 * If the hook file contains other content (i.e. was appended to), only the
 * attribution section is stripped. If the hook was created solely for
 * attribution, the file is deleted entirely.
 */
export function clearAttributionHook(repoPath?: string): void {
  const hooksDir = resolveHooksDir(repoPath)
  const hookPath = join(hooksDir, 'prepare-commit-msg')

  if (!existsSync(hookPath)) return

  const content = readFileSync(hookPath, 'utf8')
  if (!content.includes(HOOK_MARKER)) return

  // Strip the attribution block (everything from the marker line onwards that
  // was appended as a contiguous block)
  const stripped = content
    .split('\n')
    .filter(line => !line.includes(HOOK_MARKER))
    .join('\n')
    .trimEnd()

  const withoutScript = stripped.replace(HOOK_SCRIPT.trimEnd(), '').trimEnd()

  if (!withoutScript || withoutScript === '#!/bin/sh') {
    unlinkSync(hookPath)
  } else {
    writeFileSync(hookPath, `${withoutScript}\n`)
  }
}
