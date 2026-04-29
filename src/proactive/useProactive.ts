import React from 'react'
import { subscribeToProactiveChanges, isProactiveActive } from './index.js'

export function useProactive(): boolean {
  return React.useSyncExternalStore(subscribeToProactiveChanges, isProactiveActive)
}
