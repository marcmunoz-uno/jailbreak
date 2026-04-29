import type { Command } from '../../commands.js'

const forkCommand = {
  type: 'local-jsx' as const,
  name: 'fork',
  description: 'Fork the current conversation into a parallel subagent branch',
  argumentHint: '<task description>',
  isEnabled: () => true,
  load: () => import('./ForkCommand.js'),
} satisfies Command

export default forkCommand
