import { existsSync, readdirSync, readFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import React, { useEffect, useState } from 'react'
import type { LocalJSXCommandContext } from '../../commands.js'
import { Box, Text } from '../../ink.js'
import type { LocalJSXCommandOnDone } from '../../types/command.js'

const WORKFLOW_DIRS = [
  join(homedir(), '.claude', 'workflows'),
  join(homedir(), '.jailbreak', 'workflows'),
]

type Workflow = {
  name: string
  path: string
  dir: string
}

function loadWorkflows(): Workflow[] {
  const results: Workflow[] = []
  for (const dir of WORKFLOW_DIRS) {
    if (!existsSync(dir)) continue
    try {
      const entries = readdirSync(dir)
      for (const entry of entries) {
        if (entry.endsWith('.md') || entry.endsWith('.sh') || entry.endsWith('.txt')) {
          results.push({
            name: entry.replace(/\.(md|sh|txt)$/, ''),
            path: join(dir, entry),
            dir,
          })
        }
      }
    } catch {
      // Skip unreadable directories
    }
  }
  return results
}

function WorkflowList({
  workflows,
  onDone,
}: {
  workflows: Workflow[]
  onDone: LocalJSXCommandOnDone
}) {
  useEffect(() => {
    const lines = workflows.map(w => `  ${w.name}  (${w.dir})`).join('\n')
    const message = workflows.length === 0
      ? 'No workflows found. Create .md or .sh files in ~/.claude/workflows/ or ~/.jailbreak/workflows/.'
      : `Available workflows:\n${lines}`
    const timer = setTimeout(() => onDone(message, { display: 'system' }), 0)
    return () => clearTimeout(timer)
  }, [workflows, onDone])

  if (workflows.length === 0) {
    return (
      <Box>
        <Text dimColor>No workflows found in workflow directories.</Text>
      </Box>
    )
  }

  return (
    <Box flexDirection="column">
      <Text bold>Available workflows:</Text>
      {workflows.map(w => (
        <Box key={w.path}>
          <Text>  </Text>
          <Text color="cyan">{w.name}</Text>
          <Text dimColor>  {w.dir}</Text>
        </Box>
      ))}
    </Box>
  )
}

function WorkflowRunner({
  workflow,
  onDone,
}: {
  workflow: Workflow
  onDone: LocalJSXCommandOnDone
}) {
  useEffect(() => {
    try {
      const content = readFileSync(workflow.path, 'utf-8')
      onDone(
        `Running workflow: ${workflow.name}`,
        {
          display: 'system',
          metaMessages: [
            `<workflow name="${workflow.name}">\n${content}\n</workflow>`,
          ],
          shouldQuery: true,
        },
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      onDone(`Failed to load workflow "${workflow.name}": ${message}`, { display: 'system' })
    }
  }, [workflow, onDone])

  return (
    <Box>
      <Text color="cyan">Loading workflow: </Text>
      <Text>{workflow.name}</Text>
    </Box>
  )
}

export const call = async (
  onDone: LocalJSXCommandOnDone,
  _context: LocalJSXCommandContext,
  args: string,
): Promise<React.ReactNode> => {
  const name = args.trim().toLowerCase()
  const workflows = loadWorkflows()

  if (!name) {
    return <WorkflowList workflows={workflows} onDone={onDone} />
  }

  const match = workflows.find(
    w => w.name.toLowerCase() === name || w.name.toLowerCase().startsWith(name),
  )

  if (!match) {
    const available = workflows.map(w => w.name).join(', ') || 'none'
    const message = `Workflow "${name}" not found. Available: ${available}`
    onDone(message, { display: 'system' })
    return (
      <Box>
        <Text color="red">{message}</Text>
      </Box>
    )
  }

  return <WorkflowRunner workflow={match} onDone={onDone} />
}
