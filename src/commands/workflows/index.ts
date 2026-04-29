import type { Command } from '../../commands.js'

const workflowsCommand = {
  type: 'local-jsx',
  name: 'workflows',
  description:
    'List and run saved workflow scripts from ~/.claude/workflows/ or ~/.jailbreak/workflows/',
  argumentHint: '[workflow name]',
  isEnabled: () => true,
  load: () => import('./WorkflowCommand.js'),
} satisfies Command

export default workflowsCommand
