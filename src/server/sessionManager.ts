export interface IBackend {
  name: string
}

export type SessionManagerOptions = {
  idleTimeoutMs?: number
  maxSessions?: number
}

/**
 * SessionManager manages the lifecycle of server sessions.
 */
export class SessionManager {
  constructor(
    _backend: IBackend,
    _options: SessionManagerOptions = {},
  ) {}

  async destroyAll(): Promise<void> {
    // no-op stub
  }
}
