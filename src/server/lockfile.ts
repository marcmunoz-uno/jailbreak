export type ServerLockInfo = {
  pid: number
  port: number
  host: string
  httpUrl: string
  startedAt: number
}

/**
 * Write a server lockfile so other processes can detect a running server.
 */
export async function writeServerLock(_info: ServerLockInfo): Promise<void> {
  // no-op stub
}

/**
 * Remove the server lockfile on shutdown.
 */
export async function removeServerLock(): Promise<void> {
  // no-op stub
}

/**
 * Check if a server is already running by reading the lockfile.
 * Returns the lock info if a server is running, null otherwise.
 */
export async function probeRunningServer(): Promise<ServerLockInfo | null> {
  return null
}
