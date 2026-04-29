/**
 * Memory shape telemetry (MEMORY_SHAPE_TELEMETRY).
 *
 * Tracks token-budget shape across sessions: conversation tokens, system
 * prompt tokens, tool-result tokens, compaction count, and peak token usage.
 * Data is appended to a newline-delimited JSON log in ~/.claude/.
 */

import { existsSync, mkdirSync, readFileSync } from 'fs'
import { appendFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

export interface MemoryShape {
  sessionId: string
  timestamp: number
  conversationTokens: number
  systemPromptTokens: number
  toolResultTokens: number
  compactionCount: number
  peakTokens: number
}

const STATE_DIR = join(homedir(), '.claude')
const SHAPE_LOG = join(STATE_DIR, 'memory-shape.ndjson')

function ensureStateDir(): void {
  if (!existsSync(STATE_DIR)) {
    mkdirSync(STATE_DIR, { recursive: true })
  }
}

/**
 * Append a memory shape record to the telemetry log.
 * Each record is written as a single JSON line (NDJSON format).
 */
export function recordMemoryShape(shape: MemoryShape): void {
  ensureStateDir()
  try {
    appendFileSync(SHAPE_LOG, JSON.stringify(shape) + '\n', 'utf8')
  } catch {
    // Telemetry writes are best-effort — never throw
  }
}

/**
 * Read the most recent `limit` memory shape records from the log.
 * Defaults to the last 100 records.
 */
export function getMemoryShapeHistory(limit = 100): MemoryShape[] {
  if (!existsSync(SHAPE_LOG)) return []

  try {
    const raw = readFileSync(SHAPE_LOG, 'utf8')
    const lines = raw.split('\n').filter(line => line.trim().length > 0)
    const start = Math.max(0, lines.length - limit)
    return lines.slice(start).map(line => JSON.parse(line) as MemoryShape)
  } catch {
    return []
  }
}

/**
 * Compute aggregate statistics across all recorded memory shape sessions.
 */
export function getMemoryShapeStats(): {
  avgPeak: number
  avgCompactions: number
  sessions: number
} {
  const history = getMemoryShapeHistory(0 /* all */)

  if (history.length === 0) {
    return { avgPeak: 0, avgCompactions: 0, sessions: 0 }
  }

  // Group by sessionId so each session contributes once to the averages
  const bySession = new Map<string, MemoryShape[]>()
  for (const record of history) {
    const existing = bySession.get(record.sessionId)
    if (existing) {
      existing.push(record)
    } else {
      bySession.set(record.sessionId, [record])
    }
  }

  const sessionIds = [...bySession.keys()]
  let totalPeak = 0
  let totalCompactions = 0

  for (const id of sessionIds) {
    const records = bySession.get(id)!
    const peak = Math.max(...records.map(r => r.peakTokens))
    const compactions = Math.max(...records.map(r => r.compactionCount))
    totalPeak += peak
    totalCompactions += compactions
  }

  const sessions = sessionIds.length

  return {
    avgPeak: Math.round(totalPeak / sessions),
    avgCompactions: Math.round((totalCompactions / sessions) * 100) / 100,
    sessions,
  }
}
