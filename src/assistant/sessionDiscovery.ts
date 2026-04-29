/**
 * Assistant session discovery — lists active bridge sessions that are
 * running in assistant (Kairos) mode.
 *
 * In the external snapshot this is a stub: without the full Anthropic bridge
 * infrastructure the only way to discover sessions is via the daemon.json
 * written by a locally running assistant daemon.
 */
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { homedir } from 'os'

export type AssistantSession = {
  sessionId: string
  label: string
  startedAt: string
  cwd: string
}

type DaemonEntry = {
  sessionId: string
  label?: string
  startedAt?: string
  cwd?: string
}

function getDaemonJsonPath(): string {
  return join(homedir(), '.claude', 'assistant', 'daemon.json')
}

/**
 * Read the daemon.json file written by a locally running assistant daemon
 * and return the list of active sessions. Returns an empty array when the
 * file is absent, unreadable, or malformed.
 */
export async function discoverAssistantSessions(): Promise<AssistantSession[]> {
  const daemonPath = getDaemonJsonPath()

  if (!existsSync(daemonPath)) {
    return []
  }

  try {
    const raw = readFileSync(daemonPath, 'utf8')
    const parsed: unknown = JSON.parse(raw)

    if (!Array.isArray(parsed)) {
      return []
    }

    return (parsed as DaemonEntry[])
      .filter(entry => typeof entry?.sessionId === 'string')
      .map(entry => ({
        sessionId: entry.sessionId,
        label: entry.label ?? entry.sessionId,
        startedAt: entry.startedAt ?? new Date().toISOString(),
        cwd: entry.cwd ?? homedir(),
      }))
  } catch {
    return []
  }
}
