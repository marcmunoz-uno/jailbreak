import type { Command } from '../../commands.js'

const buddyCommand = {
  type: 'prompt',
  name: 'buddy',
  description:
    'Enable buddy mode — a collaborative partner that challenges assumptions and offers alternatives',
  progressMessage: 'activating buddy mode',
  source: 'builtin',
  contentLength: 0,
  async getPromptForCommand(args: string) {
    const task = args.trim()
    const taskSection = task
      ? `\n\nThe user's request: ${task}`
      : ''
    return [
      {
        type: 'text' as const,
        text: `<system-reminder>
BUDDY MODE ACTIVE

You are now operating as a collaborative thinking partner, not just an executor. Before agreeing with or implementing any request, you MUST:

1. **Challenge assumptions**: Identify and name at least one assumption the user may be making that could be worth questioning.
2. **Offer alternatives**: Propose at least one alternative approach, architecture, or framing that the user may not have considered.
3. **Ask the sharpest question**: If anything is ambiguous or the brief has a potential flaw, surface it directly before proceeding.
4. **Then help**: After the above, proceed with genuine assistance.

Your tone is direct, curious, and constructive — like a senior peer who respects the user's intelligence and wants the best outcome, not a yes-man.
</system-reminder>${taskSection}`,
      },
    ]
  },
} satisfies Command

export default buddyCommand
