/**
 * Run a headless (non-interactive) session connected to a remote Claude server.
 */
export async function runConnectHeadless(
  _config: unknown,
  _prompt: string,
  _outputFormat: string,
  _interactive: boolean,
): Promise<void> {
  throw new Error('Headless connect not implemented in this build')
}
