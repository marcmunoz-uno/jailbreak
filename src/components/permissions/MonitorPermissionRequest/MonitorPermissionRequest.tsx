import React from 'react'

type Props = {
  onYes: () => void
  onNo: () => void
}

export function MonitorPermissionRequest({ onYes, onNo }: Props): React.ReactElement {
  void onYes
  void onNo
  return React.createElement(React.Fragment, null)
}
