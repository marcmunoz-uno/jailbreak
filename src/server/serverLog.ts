import type { ServerLogger } from './server.js'

/**
 * Create a server logger that writes to stderr.
 */
export function createServerLogger(): ServerLogger {
  return {
    info(msg: string, data?: unknown) {
      process.stderr.write(
        `[INFO] ${msg}${data !== undefined ? ` ${JSON.stringify(data)}` : ''}\n`,
      )
    },
    error(msg: string, data?: unknown) {
      process.stderr.write(
        `[ERROR] ${msg}${data !== undefined ? ` ${JSON.stringify(data)}` : ''}\n`,
      )
    },
    warn(msg: string, data?: unknown) {
      process.stderr.write(
        `[WARN] ${msg}${data !== undefined ? ` ${JSON.stringify(data)}` : ''}\n`,
      )
    },
  }
}
