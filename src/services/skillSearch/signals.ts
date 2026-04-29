/**
 * Signal types used during skill discovery.
 * DiscoverySignal indicates the context that triggered a skill discovery.
 */
export type DiscoverySignal =
  | 'user_input'
  | 'assistant_turn'
  | 'prefetch'
