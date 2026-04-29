/**
 * Assistant (Kairos) module entry point.
 *
 * Exposes the assistant lifecycle functions used by main.tsx, bridge, and
 * command handlers. The assistant stack runs as a persistent in-process team
 * whose context is initialized once per session.
 */
import { setCliTeammateModeOverride } from '../utils/swarm/backends/teammateModeSnapshot.js'

let _assistantForced = false

/**
 * Mark that the user explicitly requested assistant mode (e.g. --assistant
 * CLI flag or `claude assistant <sessionId>` subcommand). Prevents the normal
 * Kairos gate check from downgrading the session.
 */
export function markAssistantForced(): void {
  _assistantForced = true
}

export function isAssistantForced(): boolean {
  return _assistantForced
}

/**
 * True when this process is running in assistant (Kairos) mode.
 * Set during bootstrap when kairosEnabled is confirmed.
 */
let _assistantMode = false

export function setAssistantMode(active: boolean): void {
  _assistantMode = active
}

export function isAssistantMode(): boolean {
  return _assistantMode
}

export type AssistantTeamContext = {
  teamId: string
  initialized: boolean
}

/**
 * Initialize the in-process assistant team so Agent(name: "...") spawns
 * teammates without requiring a TeamCreate round-trip.
 * Called once during REPL setup when kairosEnabled is confirmed.
 */
export async function initializeAssistantTeam(): Promise<AssistantTeamContext> {
  // Override teammate mode to 'assistant' so the team tools resolve correctly.
  setCliTeammateModeOverride('assistant')
  _assistantMode = true

  return {
    teamId: `assistant-${Date.now()}`,
    initialized: true,
  }
}

/**
 * System prompt addendum injected at the end of the main system prompt when
 * running in assistant mode. Instructs the model to behave as a persistent
 * assistant rather than a one-shot query responder.
 */
export function getAssistantSystemPromptAddendum(): string {
  return `# Assistant Mode

You are running as a persistent assistant. You have access to the user's environment, files, and tools across sessions.

Key behaviors:
- Proactively surface relevant information without being asked
- Maintain context across multiple interactions
- Use the Brief tool for all user-facing output when brief mode is enabled
- Prefer concise, actionable responses over verbose explanations
- When idle, call Sleep and wait for the next tick or user message`
}
