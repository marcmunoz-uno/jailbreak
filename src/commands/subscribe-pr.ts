import { feature } from 'bun:bundle'
import type { Command } from '../types/command.js'

const subscribePr: Command = {
  type: 'local-jsx',
  name: 'subscribe-pr',
  description: 'Subscribe to PR activity notifications',
  isEnabled: () => {
    if (feature('KAIROS_GITHUB_WEBHOOKS')) return true
    return false
  },
  load: () => import('./subscribe-pr-impl.js'),
}

export default subscribePr
