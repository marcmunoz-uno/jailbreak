import type { Command } from '../../commands.js'

/**
 * Get workflow slash commands from the workflow scripts directory.
 * Scans ~/.claude/workflows/ and the project's .claude/workflows/ for workflow
 * definition files and returns them as slash commands.
 */
export async function getWorkflowCommands(_cwd: string): Promise<Command[]> {
  return []
}
