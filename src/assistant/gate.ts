/**
 * Kairos gate — runtime entitlement check for assistant mode.
 *
 * In external builds the GrowthBook gate is unavailable, so this falls back
 * to an env-var override (CLAUDE_CODE_KAIROS=1) and the forced-mode flag.
 */
import { isEnvTruthy } from '../utils/envUtils.js'

/**
 * Returns true when this session is entitled to run in Kairos (assistant)
 * mode. Called once during REPL setup; result is cached by the caller.
 */
export async function isKairosEnabled(): Promise<boolean> {
  // Hard env-var override — useful for local development and self-hosted
  // deployments that don't have GrowthBook configured.
  if (isEnvTruthy(process.env['CLAUDE_CODE_KAIROS'])) {
    return true
  }

  // In external builds, GrowthBook may not be reachable or configured.
  // Default to disabled so external users don't accidentally enter assistant
  // mode without explicit opt-in.
  return false
}
