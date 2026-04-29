import { feature } from 'bun:bundle'
import type { Command, LocalJSXCommandOnDone, LocalJSXCommandContext } from '../types/command.js'
import type { ToolUseContext } from '../Tool.js'

const proactive = {
  type: 'local-jsx',
  name: 'proactive',
  description: 'Toggle proactive autonomous mode',
  isEnabled: () => {
    if (feature('PROACTIVE') || feature('KAIROS')) {
      return true
    }
    return false
  },
  immediate: true,
  load: () =>
    Promise.resolve({
      async call(
        onDone: LocalJSXCommandOnDone,
        _context: ToolUseContext & LocalJSXCommandContext,
      ): Promise<React.ReactNode> {
        const { activateProactive, deactivateProactive, isProactiveActive } =
          await import('../proactive/index.js')

        const active = isProactiveActive()

        if (active) {
          deactivateProactive()
        } else {
          activateProactive('slash_command')
        }

        const newState = !active
        onDone(
          newState ? 'Proactive mode enabled' : 'Proactive mode disabled',
          { display: 'system' },
        )
        return null
      },
    }),
} satisfies Command

export default proactive
