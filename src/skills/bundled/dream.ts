import { createDreamEngine } from '../../dream.js'
import { registerBundledSkill } from '../bundledSkills.js'

export function registerDreamSkill(): void {
  registerBundledSkill({
    name: 'dream',
    description: 'Run background dream tasks — process the task queue with token budgeting and priority scheduling.',
    whenToUse: 'Use when the user wants to run background tasks, process a dream queue, or execute low-priority work while idle.',
    userInvocable: true,
    isEnabled: () => true,
    async getPromptForCommand(args) {
      const engine = createDreamEngine()
      if (args) {
        engine.addTask(args, 10)
      }
      const status = engine.getStatus()
      const prompt = `# Dream Task Execution

Process the dream task queue. Use the DreamEngine to run queued tasks with priority scheduling and token budgeting.

${args ? `## User-specified task\n${args}\n\n` : ''}## Current Status
- Queue depth: ${status.queue}
- Token budget: ${status.tokenBudget.used}/${status.tokenBudget.max} used

Start the engine and report completion status when done.`
      return [{ type: 'text', text: prompt }]
    },
  })
}
