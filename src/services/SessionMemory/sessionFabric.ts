import { mkdir, readFile, writeFile } from 'fs/promises'
import { basename, join } from 'path'
import { getSessionId } from '../../bootstrap/state.js'
import { getClaudeConfigHomeDir, isEnvTruthy } from '../../utils/envUtils.js'
import { getErrnoCode } from '../../utils/errors.js'
import { parseJSONL } from '../../utils/json.js'
import { getCwd } from '../../utils/cwd.js'

type SessionFabricEntry = {
  sessionId: string
  cwd: string
  cwdLabel: string
  updatedAt: string
  title?: string
  currentState?: string
  errors?: string
  keyResults?: string
}

const SESSION_FABRIC_DIR = 'session-fabric'
const SESSION_FABRIC_FILE = 'sessions.jsonl'
const MAX_FABRIC_ENTRIES = 12
const MAX_SECTION_CHARS = 280

function getSessionFabricPath(): string {
  return join(getClaudeConfigHomeDir(), SESSION_FABRIC_DIR, SESSION_FABRIC_FILE)
}

export function isSessionFabricEnabled(): boolean {
  return !isEnvTruthy(process.env.JAILBREAK_DISABLE_SESSION_FABRIC)
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

function truncate(value: string | undefined, maxChars = MAX_SECTION_CHARS): string {
  if (!value) return ''
  const normalized = normalizeWhitespace(value)
  if (normalized.length <= maxChars) return normalized
  return normalized.slice(0, maxChars - 1).trimEnd() + '…'
}

function extractSection(content: string, sectionName: string): string {
  const escaped = sectionName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(
    `# ${escaped}\\n(?:_.*?_\\n)?([\\s\\S]*?)(?=\\n# |$)`,
    'm',
  )
  const match = content.match(regex)
  return match?.[1]?.trim() ?? ''
}

function parseFabricEntry(memoryContent: string): SessionFabricEntry | null {
  const title = truncate(extractSection(memoryContent, 'Session Title'), 120)
  const currentState = truncate(extractSection(memoryContent, 'Current State'))
  const errors = truncate(extractSection(memoryContent, 'Errors & Corrections'))
  const keyResults = truncate(extractSection(memoryContent, 'Key results'))

  if (!title && !currentState && !errors && !keyResults) {
    return null
  }

  const cwd = getCwd()
  return {
    sessionId: getSessionId(),
    cwd,
    cwdLabel: basename(cwd) || cwd,
    updatedAt: new Date().toISOString(),
    ...(title ? { title } : {}),
    ...(currentState ? { currentState } : {}),
    ...(errors ? { errors } : {}),
    ...(keyResults ? { keyResults } : {}),
  }
}

async function readFabricEntries(): Promise<SessionFabricEntry[]> {
  try {
    const raw = await readFile(getSessionFabricPath())
    return parseJSONL<SessionFabricEntry>(raw)
  } catch (error) {
    if (getErrnoCode(error) === 'ENOENT') {
      return []
    }
    throw error
  }
}

export async function updateSessionFabric(
  memoryContent: string,
): Promise<void> {
  if (!isSessionFabricEnabled()) return

  const nextEntry = parseFabricEntry(memoryContent)
  if (!nextEntry) return

  const fabricPath = getSessionFabricPath()
  await mkdir(join(getClaudeConfigHomeDir(), SESSION_FABRIC_DIR), {
    recursive: true,
    mode: 0o700,
  })

  const existing = await readFabricEntries()
  const deduped = existing.filter(entry => entry.sessionId !== nextEntry.sessionId)
  const merged = [nextEntry, ...deduped]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, MAX_FABRIC_ENTRIES)

  const body = merged.map(entry => JSON.stringify(entry)).join('\n')
  await writeFile(fabricPath, body ? body + '\n' : '', {
    encoding: 'utf8',
    mode: 0o600,
  })
}

export async function loadSessionFabricPrompt(): Promise<string | null> {
  if (!isSessionFabricEnabled()) return null

  const currentSessionId = getSessionId()
  const currentCwd = getCwd()
  const entries = (await readFabricEntries())
    .filter(entry => entry.sessionId !== currentSessionId)
    .sort((a, b) => {
      const aSameRepo = a.cwd === currentCwd ? 1 : 0
      const bSameRepo = b.cwd === currentCwd ? 1 : 0
      if (aSameRepo !== bSameRepo) return bSameRepo - aSameRepo
      return b.updatedAt.localeCompare(a.updatedAt)
    })
    .slice(0, 5)

  if (entries.length === 0) {
    return null
  }

  const lines = entries.map(entry => {
    const parts = [
      `Session ${entry.sessionId.slice(0, 8)} in ${entry.cwdLabel}`,
      entry.title ? `title: ${entry.title}` : null,
      entry.currentState ? `current: ${entry.currentState}` : null,
      entry.errors ? `errors: ${entry.errors}` : null,
      entry.keyResults ? `results: ${entry.keyResults}` : null,
      `updated: ${entry.updatedAt}`,
    ].filter(Boolean)
    return `- ${parts.join(' | ')}`
  })

  return `# Session Fabric
Recent snapshots from other active/recent Jailbreak sessions. Use this as soft shared memory for coordination and continuity. Treat it as potentially stale; verify before taking irreversible actions.

${lines.join('\n')}`
}
