# TypeScript Agent SDK – Common Patterns

## Custom Tools

```typescript
import { Agent, tool } from '@anthropic-ai/agents'
import { z } from 'zod'

const getWeather = tool({
  name: 'get_weather',
  description: 'Get current weather for a location',
  parameters: z.object({ location: z.string() }),
  execute: async ({ location }) => `Sunny, 22°C in ${location}`,
})

const agent = new Agent({ model: '{{SONNET_ID}}', tools: [getWeather] })
const result = await agent.run('What is the weather in Tokyo?')
```

## Streaming

```typescript
const stream = agent.runStream('Write a short story')
for await (const event of stream) {
  if (event.type === 'text') process.stdout.write(event.text)
}
```

## Multi-agent Handoff

```typescript
import { Agent, handoff } from '@anthropic-ai/agents'

const researcher = new Agent({ model: '{{SONNET_ID}}', name: 'researcher' })
const writer = new Agent({ model: '{{SONNET_ID}}', name: 'writer' })
const orchestrator = new Agent({
  model: '{{SONNET_ID}}',
  tools: [handoff(researcher), handoff(writer)],
})
```
