import type { ServerConfig } from './types.js'

/**
 * Print the server startup banner to stdout.
 */
export function printBanner(
  config: ServerConfig,
  authToken: string,
  actualPort: number,
): void {
  const addr = config.unix
    ? `unix:${config.unix}`
    : `http://${config.host}:${actualPort}`
  process.stdout.write(`Claude Code server started at ${addr}\n`)
  process.stdout.write(`Auth token: ${authToken}\n`)
}
