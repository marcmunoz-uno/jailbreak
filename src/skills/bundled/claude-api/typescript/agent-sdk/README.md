# Anthropic Agents SDK – TypeScript

## Installation

```bash
npm install @anthropic-ai/agents
```

## Quick Start

```typescript
import { Agent } from '@anthropic-ai/agents'

const agent = new Agent({ model: '{{SONNET_ID}}' })
const result = await agent.run('Summarize the latest news.')
console.log(result.output)
```

## Key Concepts

- **Agent**: Claude-powered agent that can call tools and iterate.
- **Tool**: Typed function the agent can invoke.
- **Runner**: Manages the agent loop until completion.
