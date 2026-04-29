import type { Command } from '../../types/command.js'

const remoteControlServer = {
  type: 'local-jsx',
  name: 'remote-control',
  description: 'Start the remote control server',
  isEnabled: () => false,
  immediate: true,
  load: () =>
    Promise.resolve({
      async call(onDone: (msg: string, opts?: { display?: string }) => void): Promise<null> {
        onDone('Remote control server is not available in this build.', { display: 'system' })
        return null
      },
    }),
} satisfies Command

export default remoteControlServer
