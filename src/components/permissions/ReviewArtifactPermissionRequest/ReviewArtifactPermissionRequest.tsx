import React from 'react'

type Props = {
  onYes: () => void
  onNo: () => void
}

export function ReviewArtifactPermissionRequest({ onYes, onNo }: Props): React.ReactElement {
  // Minimal stub — renders nothing interactive; falls back to default permission UI.
  void onYes
  void onNo
  return React.createElement(React.Fragment, null)
}
