/**
 * MCP-based skill registry (MCP_SKILLS).
 *
 * Wraps MCP server tools that look like skills as prompt Commands so they can
 * be listed and invoked alongside file-based skills.
 */

import type { Command } from '../types/command.js'

export interface McpSkill {
  name: string
  description: string
  serverName: string
  toolName: string
}

/** In-process registry of explicitly registered MCP skills. */
const registry: McpSkill[] = []

/**
 * Return all registered MCP skills wrapped as prompt Commands.
 *
 * Each skill is surfaced as a prompt command that will invoke the underlying
 * MCP tool when executed.  The actual tool invocation is handled by the MCP
 * client layer; here we only produce the Command descriptors so the skill
 * appears in `/skills` listings.
 */
export function getMcpSkills(): Command[] {
  return registry.map(skill => ({
    type: 'prompt' as const,
    name: skill.name,
    description: skill.description,
    progressMessage: `Running ${skill.name}…`,
    contentLength: 0,
    source: 'mcp' as const,
    // The prompt content delegates to the MCP tool by name
    content: () =>
      Promise.resolve([
        {
          type: 'text' as const,
          text: `Invoke the MCP tool "${skill.toolName}" from server "${skill.serverName}".`,
        },
      ]),
    isEnabled: () => true,
    isHidden: false,
  })) as unknown as Command[]
}

/**
 * Register a specific MCP tool as a first-class skill.
 * Duplicate registrations (same name) are silently ignored.
 */
export function registerMcpSkill(skill: McpSkill): void {
  const alreadyRegistered = registry.some(s => s.name === skill.name)
  if (!alreadyRegistered) {
    registry.push(skill)
  }
}

/**
 * Return all registered MCP skills in their raw descriptor form.
 */
export function listMcpSkills(): McpSkill[] {
  return [...registry]
}
