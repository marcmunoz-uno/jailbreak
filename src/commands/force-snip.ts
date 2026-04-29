import type { Command } from '../types/command.js'

const forceSnip: Command = {
  type: 'local',
  name: 'force-snip',
  description: 'Force a context snip to free up token space in the conversation history',
  isEnabled: () => true,
  supportsNonInteractive: false,
  load: () => import('./force-snip-impl.js'),
}

export default forceSnip
