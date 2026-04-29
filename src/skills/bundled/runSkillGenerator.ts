import { registerBundledSkill } from '../bundledSkills.js'

const RUN_SKILL_GENERATOR_PROMPT = `# Run Skill Generator

Generate a new skill from a natural language description.

## Instructions

Based on the user's description, create a new skill file that:

1. Exports a \`register<SkillName>Skill()\` function
2. Calls \`registerBundledSkill\` with a name, description, and \`getPromptForCommand\`
3. Returns a prompt that helps the model accomplish the skill's purpose

Place the new skill file in \`src/skills/bundled/<skill-name>.ts\` and register it in \`src/skills/bundled/index.ts\`.

## User Request
`

export function registerRunSkillGeneratorSkill(): void {
  registerBundledSkill({
    name: 'run-skill-generator',
    description: 'Generate new skills from natural language descriptions',
    userInvocable: true,
    isEnabled: () => true,
    async getPromptForCommand(args) {
      const prompt = args
        ? `${RUN_SKILL_GENERATOR_PROMPT}${args}`
        : RUN_SKILL_GENERATOR_PROMPT + 'Please describe the skill you want to create.'
      return [{ type: 'text', text: prompt }]
    },
  })
}
