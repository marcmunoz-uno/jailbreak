/**
 * Skill generator (RUN_SKILL_GENERATOR).
 *
 * Analyzes conversation summaries and recent sessions to identify reusable
 * patterns, then materializes them as skill markdown files on disk.
 */

import { existsSync, mkdirSync, readdirSync, readFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

export interface SkillTemplate {
  name: string
  description: string
  prompt: string
  triggers: string[]
}

const DEFAULT_SKILLS_DIR = join(homedir(), '.claude', 'skills')

/**
 * Analyze a plain-text conversation summary and attempt to extract a reusable
 * skill pattern from it.
 *
 * Returns a SkillTemplate when a clear, repeatable task pattern is detected,
 * or null when the conversation does not contain an obvious skill candidate.
 *
 * Detection heuristics (no LLM call — purely structural):
 * - The summary must describe a named, repeatable task (contains an imperative verb phrase).
 * - At least one trigger keyword must be derivable from the summary.
 * - The summary must be at least 20 characters to avoid matching noise.
 */
export async function generateSkill(
  conversationSummary: string,
): Promise<SkillTemplate | null> {
  const trimmed = conversationSummary.trim()
  if (trimmed.length < 20) return null

  // Extract the first sentence as the description
  const firstSentence = trimmed.split(/[.!?\n]/)[0]?.trim() ?? trimmed
  if (!firstSentence) return null

  // Derive a slug-style name from the first sentence
  const name = firstSentence
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .trim()
    .split(/\s+/)
    .slice(0, 5)
    .join('-')

  if (!name) return null

  // Derive trigger keywords: words longer than 4 chars, lowercased
  const triggers = [
    ...new Set(
      firstSentence
        .toLowerCase()
        .replace(/[^a-z\s]/g, '')
        .split(/\s+/)
        .filter(w => w.length > 4),
    ),
  ].slice(0, 6)

  return {
    name,
    description: firstSentence,
    prompt: trimmed,
    triggers,
  }
}

/**
 * Write a skill template to disk at `skillsDir/<name>/SKILL.md`.
 * Creates intermediate directories as needed.
 * Returns the absolute path of the written file.
 */
export async function saveSkill(
  template: SkillTemplate,
  skillsDir?: string,
): Promise<string> {
  const dir = skillsDir ?? DEFAULT_SKILLS_DIR
  const skillDir = join(dir, template.name)
  mkdirSync(skillDir, { recursive: true })

  const frontmatter = [
    '---',
    `name: ${template.name}`,
    `description: ${template.description}`,
    template.triggers.length > 0
      ? `triggers: [${template.triggers.map(t => `"${t}"`).join(', ')}]`
      : '',
    '---',
  ]
    .filter(Boolean)
    .join('\n')

  const content = `${frontmatter}\n\n${template.prompt}\n`
  const filePath = join(skillDir, 'SKILL.md')
  await Bun.write(filePath, content)
  return filePath
}

/**
 * Scan recent session summaries (plain-text `.summary` files in
 * `~/.claude/sessions/`) and generate skill templates from any that yield a
 * detectable pattern.
 *
 * @param options.minConfidence  Minimum summary length treated as "confident
 *   enough" to generate a skill from (default: 50 characters).
 */
export async function runSkillGenerator(options?: {
  minConfidence?: number
}): Promise<SkillTemplate[]> {
  const minLen = options?.minConfidence ?? 50
  const sessionsDir = join(homedir(), '.claude', 'sessions')

  if (!existsSync(sessionsDir)) return []

  let summaryFiles: string[]
  try {
    summaryFiles = readdirSync(sessionsDir)
      .filter(f => f.endsWith('.summary'))
      .map(f => join(sessionsDir, f))
  } catch {
    return []
  }

  const templates: SkillTemplate[] = []

  for (const filePath of summaryFiles) {
    try {
      const text = readFileSync(filePath, 'utf8').trim()
      if (text.length < minLen) continue
      const template = await generateSkill(text)
      if (template) templates.push(template)
    } catch {
      // Skip unreadable files
    }
  }

  return templates
}
