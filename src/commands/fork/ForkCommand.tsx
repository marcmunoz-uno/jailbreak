import React, { useEffect, useState } from 'react'
import type { LocalJSXCommandContext } from '../../commands.js'
import { Box, Text } from '../../ink.js'
import type { LocalJSXCommandOnDone } from '../../types/command.js'

type ForkStatus =
  | { type: 'pending' }
  | { type: 'running' }
  | { type: 'done'; result: string }
  | { type: 'error'; message: string }

function ForkComponent({
  args,
  context,
  onDone,
}: {
  args: string
  context: LocalJSXCommandContext
  onDone: LocalJSXCommandOnDone
}) {
  const [status, setStatus] = useState<ForkStatus>({ type: 'pending' })

  useEffect(() => {
    const task = args.trim()
    if (!task) {
      setStatus({ type: 'error', message: 'Usage: /fork <task description>' })
      const timer = setTimeout(() => onDone('No task description provided.', { display: 'system' }), 0)
      return () => clearTimeout(timer)
    }

    setStatus({ type: 'running' })

    const messages = context.messages ?? []
    const conversationSummary = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-20)
      .map(m => {
        const content = Array.isArray(m.content)
          ? m.content
              .filter(b => b.type === 'text')
              .map(b => ('text' in b ? b.text : ''))
              .join(' ')
          : typeof m.content === 'string'
            ? m.content
            : ''
        return `[${m.role}]: ${content.slice(0, 500)}`
      })
      .join('\n')

    const prompt = [
      'You are a subagent forked from a parent conversation. Below is the recent conversation context:',
      '',
      conversationSummary,
      '',
      `Your task: ${task}`,
      '',
      'Complete the task autonomously using the tools available to you.',
    ].join('\n')

    // Spawn a background agent via the Task tool if available, otherwise fall back to a direct message
    const taskTool = context.options?.tools?.find((t: { name: string }) => t.name === 'Task')
    if (taskTool) {
      Promise.resolve()
        .then(async () => {
          // Use the Task tool through the existing tool infrastructure
          const result = await context.runTool?.('Task', { prompt, description: `Fork: ${task}` })
          const resultText = typeof result === 'string' ? result : JSON.stringify(result ?? 'Fork complete')
          setStatus({ type: 'done', result: resultText })
          onDone(`Fork complete: ${task}`, { display: 'system' })
        })
        .catch((err: unknown) => {
          const message = err instanceof Error ? err.message : String(err)
          setStatus({ type: 'error', message })
          onDone(`Fork failed: ${message}`, { display: 'system' })
        })
    } else {
      // Task tool not available — inject as a meta message instead
      onDone(
        `Fork queued: ${task}`,
        {
          display: 'system',
          metaMessages: [prompt],
          shouldQuery: true,
        },
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Box flexDirection="column">
      <Text dimColor>{'> /fork ' + args}</Text>
      {status.type === 'pending' && <Text color="yellow">Preparing fork...</Text>}
      {status.type === 'running' && <Text color="cyan">Running forked subagent...</Text>}
      {status.type === 'done' && <Text color="green">Fork complete.</Text>}
      {status.type === 'error' && <Text color="red">Error: {status.message}</Text>}
    </Box>
  )
}

export const call = async (
  onDone: LocalJSXCommandOnDone,
  context: LocalJSXCommandContext,
  args: string,
): Promise<React.ReactNode> => {
  return <ForkComponent args={args} context={context} onDone={onDone} />
}
