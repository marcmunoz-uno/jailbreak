import { appendFileSync, mkdirSync } from 'fs'
import { join } from 'path'
import { getProjectDir } from '../../utils/sessionStorage.js'
import { getSessionId } from '../../bootstrap/state.js'

// One transcript segment per message — trimmed to text content only.
// Written as newline-delimited JSON to ~/.claude/projects/<hash>/transcripts/<date>/<session>.jsonl

function getTranscriptDir(date: string): string {
  const projectDir = getProjectDir()
  return join(projectDir, 'transcripts', date)
}

function getTranscriptPath(date: string): string {
  return join(getTranscriptDir(date), `${getSessionId()}.jsonl`)
}

function extractDate(messages: unknown[]): string {
  const first = messages[0] as { timestamp?: string } | undefined
  const ts = first?.timestamp
  if (ts) {
    return ts.slice(0, 10)
  }
  return new Date().toISOString().slice(0, 10)
}

function trimMessage(msg: unknown): unknown {
  if (!msg || typeof msg !== 'object') return msg
  const m = msg as Record<string, unknown>
  // Keep role + text content only — strip images and large blobs.
  const trimmed: Record<string, unknown> = { role: m['role'], timestamp: m['timestamp'] }
  const content = m['content']
  if (typeof content === 'string') {
    trimmed['content'] = content.slice(0, 2000)
  } else if (Array.isArray(content)) {
    trimmed['content'] = content
      .filter((c: unknown) => {
        const block = c as { type?: string }
        return block?.type === 'text' || block?.type === 'thinking'
      })
      .map((c: unknown) => {
        const block = c as { type?: string; text?: string }
        return { type: block.type, text: (block.text ?? '').slice(0, 2000) }
      })
  }
  return trimmed
}

/**
 * Write a batch of messages to the per-session per-day transcript file.
 * Fire-and-forget: errors are swallowed so callers don't need to await.
 */
export function writeSessionTranscriptSegment(messages: unknown[]): void {
  if (!messages || messages.length === 0) return

  try {
    const date = extractDate(messages)
    const dir = getTranscriptDir(date)
    mkdirSync(dir, { recursive: true })
    const path = getTranscriptPath(date)

    for (const msg of messages) {
      const trimmed = trimMessage(msg)
      appendFileSync(path, JSON.stringify(trimmed) + '\n', 'utf8')
    }
  } catch {
    // Transcript writes are best-effort.
  }
}

let _lastFlushedDate = ''

/**
 * When the date changes, flush any un-written messages to yesterday's file
 * so the /dream skill can find them even if no compaction fires overnight.
 */
export function flushOnDateChange(messages: unknown[], currentDate: string): void {
  if (_lastFlushedDate === currentDate) return
  _lastFlushedDate = currentDate
  writeSessionTranscriptSegment(messages)
}
