import { feature } from 'bun:bundle'
import type { Command, LocalJSXCommandOnDone, LocalJSXCommandContext } from '../../types/command.js'
import type { ToolUseContext } from '../../Tool.js'

const assistant = {
  type: 'local-jsx',
  name: 'assistant',
  description: 'Open the Kairos assistant setup',
  isEnabled: () => {
    if (feature('KAIROS')) {
      return true
    }
    return false
  },
  immediate: false,
  load: () =>
    import('./assistant.js').then(({ NewInstallWizard, computeDefaultInstallDir }) => ({
      async call(
        onDone: LocalJSXCommandOnDone,
        _context: ToolUseContext & LocalJSXCommandContext,
      ): Promise<React.ReactNode> {
        const React = await import('react')
        const defaultDir = await computeDefaultInstallDir()
        return React.default.createElement(NewInstallWizard, {
          defaultDir,
          onInstalled: (dir: string) =>
            onDone(`Assistant installed to ${dir}`, { display: 'system' }),
          onCancel: () =>
            onDone('Assistant setup cancelled', { display: 'system' }),
          onError: (msg: string) =>
            onDone(`Assistant setup error: ${msg}`, { display: 'system' }),
        })
      },
    })),
} satisfies Command

export default assistant
