import * as React from 'react'
import { Box, Text } from '../../ink.js'

export type ClawdPose = 'default' | 'arms-up' | 'look-left' | 'look-right'

type Props = {
  pose?: ClawdPose
}

const SKULL_ROWS = [
  '          ▓▓▓▓  ▓▓▓▓▓▓           ',
  '      ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓         ',
  '    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓       ',
  '   ▓▓▓▓▓▓▓▓░░░▓▓▓▓░░░▓▓▓▓▓▓      ',
  '  ▓▓▓▓▓▓░░░░░░▓▓▓▓░░░░░░▓▓▓▓     ',
  '  ▓▓▓▓░░  ░░░░▓▓▓▓░░░  ░░▓▓▓     ',
  ' ▓▓▓▓░░    ░░░▓▓▓▓░░    ░░▓▓▓    ',
  ' ▓▓▓▓░░      ▓▓▓▓▓      ░░▓▓▓    ',
  ' ▓▓▓▓▓      ▓▓▓▓▓▓▓      ▓▓▓▓    ',
  '  ▓▓▓▓▓    ▓▓░▓▓▓░▓▓    ▓▓▓▓     ',
  '   ▓▓▓▓▓  ▓▓▓▓▓▓▓▓▓▓  ▓▓▓▓▓  ░   ',
  '     ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓     ░  ',
  '      ▓▓▓▓▓▓░░░░░░▓▓▓▓▓▓   ░░    ',
  '    ░░  ▓▓░░▓▓  ▓▓░░▓▓   ░░      ',
  '  ░░░    ░░▓▓▓  ▓▓▓░░  ░░        ',
  '         ░░░      ░░░            '
]

export function Clawd(_props: Props) {
  return (
    <Box flexDirection="column" alignItems="center">
      {SKULL_ROWS.map((row, index) => (
        <Text key={index} color="clawd_body">
          {row}
        </Text>
      ))}
    </Box>
  )
}
