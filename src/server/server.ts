import type { ServerConfig } from './types.js'

export type ServerLogger = {
  info(msg: string, data?: unknown): void
  error(msg: string, data?: unknown): void
  warn(msg: string, data?: unknown): void
}

export type ServerHandle = {
  port: number | null
  stop(immediate?: boolean): void
}

export interface ISessionManager {
  destroyAll(): Promise<void>
}

/**
 * Start the Claude session server.
 */
export function startServer(
  _config: ServerConfig,
  _sessionManager: ISessionManager,
  _logger: ServerLogger,
): ServerHandle {
  throw new Error('Server not implemented in this build')
}
