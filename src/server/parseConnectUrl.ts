export type ConnectUrl = { serverUrl: string; authToken: string | undefined }

/**
 * Parse a cc:// or cc+unix:// URL into a server URL and auth token.
 *
 * Format: cc://[token@]host:port[/path]
 *         cc+unix://[token@]/path/to/socket
 *
 * The auth token is the userinfo component (before @) of the URL.
 */
export function parseConnectUrl(raw: string): ConnectUrl {
  // Normalize cc:// and cc+unix:// to http:// for URL parsing
  const isUnix = raw.startsWith('cc+unix://')
  const normalized = isUnix
    ? raw.replace(/^cc\+unix:\/\//, 'http://localhost/')
    : raw.replace(/^cc:\/\//, 'http://')

  let parsed: URL
  try {
    parsed = new URL(normalized)
  } catch {
    throw new Error(`Invalid connect URL: ${raw}`)
  }

  const authToken = parsed.username ? decodeURIComponent(parsed.username) : undefined

  let serverUrl: string
  if (isUnix) {
    // Extract the socket path from the original URL
    const socketPath = raw.replace(/^cc\+unix:\/\/[^/]*/, '')
    serverUrl = `unix://${socketPath}`
  } else {
    // Rebuild the URL without auth info
    const host = parsed.host // includes port if present
    const pathname = parsed.pathname !== '/' ? parsed.pathname : ''
    serverUrl = `http://${host}${pathname}`
  }

  return { serverUrl, authToken }
}
