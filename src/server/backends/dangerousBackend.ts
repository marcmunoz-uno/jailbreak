import type { IBackend } from '../sessionManager.js'

/**
 * DangerousBackend — bypasses permission checks.
 * Use only in trusted server environments where the caller has already
 * authenticated.
 */
export class DangerousBackend implements IBackend {
  readonly name = 'dangerous'
}
