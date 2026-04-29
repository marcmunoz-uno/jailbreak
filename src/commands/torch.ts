import type { Command } from '../commands.js'

const torchCommand = {
  type: 'prompt',
  name: 'torch',
  description:
    'Illuminate code structure: dependency graph, entry points, hot paths, and complexity overview',
  progressMessage: 'analyzing project architecture',
  source: 'builtin',
  contentLength: 0,
  async getPromptForCommand(args: string) {
    const focus = args.trim()
    const focusSection = focus
      ? `\nFocus area requested by the user: ${focus}\n`
      : ''
    return [
      {
        type: 'text' as const,
        text: `Perform a structured architectural analysis of the current project. Use the available file-reading and search tools to explore the codebase.${focusSection}

Produce a concise report with the following sections:

## Entry Points
List the main entry points (e.g. index files, CLI entrypoints, server startup files).

## Dependency Graph (High Level)
Describe the top-level modules and how they depend on each other. Use a simple text diagram or bullet list showing import relationships between major areas.

## Hot Paths
Identify the most critical execution paths — the code that runs most frequently or handles the most important user-facing functionality.

## Complexity Hotspots
Flag the files or modules with the highest apparent complexity: large files, deep nesting, many responsibilities, or frequently changed code.

## Architecture Summary
In 3–5 sentences, summarize the overall architecture pattern (e.g. layered, event-driven, plugin-based) and any notable design decisions.

Be specific with file paths. Explore the codebase using your tools before responding.`,
      },
    ]
  },
} satisfies Command

export default torchCommand
