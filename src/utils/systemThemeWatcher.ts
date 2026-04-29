/**
 * macOS system theme watcher for the AUTO_THEME feature.
 *
 * Polls `defaults read -g AppleInterfaceStyle` every 5 seconds to detect
 * dark/light mode changes. "Dark" in the output means dark mode; an error
 * (exit code != 0) means light mode (the key is absent when light is active).
 */

import { execSync } from 'child_process'

export type Theme = 'dark' | 'light'
export type ThemeChangeCallback = (theme: Theme) => void

/**
 * Read the current macOS appearance by querying the global defaults domain.
 * Returns 'dark' if AppleInterfaceStyle is "Dark", otherwise 'light'.
 */
export function getCurrentTheme(): Theme {
  try {
    const result = execSync('defaults read -g AppleInterfaceStyle 2>/dev/null', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim()
    return result === 'Dark' ? 'dark' : 'light'
  } catch {
    // Key absent means light mode is active
    return 'light'
  }
}

/**
 * Poll for macOS system theme changes every 5 seconds.
 * Calls `callback` whenever the theme transitions between dark and light.
 * Returns a function that stops polling when called.
 */
export function watchTheme(callback: ThemeChangeCallback): () => void {
  let current: Theme = getCurrentTheme()
  const intervalMs = 5_000

  const timer = setInterval(() => {
    const next = getCurrentTheme()
    if (next !== current) {
      current = next
      callback(current)
    }
  }, intervalMs)

  // Allow the Node/Bun process to exit even if the watcher is still active
  if (typeof timer === 'object' && timer !== null && 'unref' in timer) {
    ;(timer as NodeJS.Timeout).unref()
  }

  return () => clearInterval(timer)
}
