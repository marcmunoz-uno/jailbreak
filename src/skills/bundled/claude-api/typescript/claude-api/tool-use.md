# Claude API – TypeScript Tool Use

## Define and Use a Tool

```typescript
import Anthropic from '@anthropic-ai/sdk'

const client = new Anthropic()

const tools: Anthropic.Tool[] = [
  {
    name: 'get_weather',
    description: 'Get the current weather for a location.',
    input_schema: {
      type: 'object',
      properties: {
        location: { type: 'string', description: 'City name' },
      },
      required: ['location'],
    },
  },
]

const messages: Anthropic.MessageParam[] = [
  { role: 'user', content: "What's the weather in Paris?" },
]

const response = await client.messages.create({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  tools,
  messages,
})

if (response.stop_reason === 'tool_use') {
  const toolUse = response.content.find(b => b.type === 'tool_use')!
  const result = { temperature: '20°C', condition: 'sunny' }

  messages.push({ role: 'assistant', content: response.content })
  messages.push({
    role: 'user',
    content: [
      {
        type: 'tool_result',
        tool_use_id: toolUse.id,
        content: JSON.stringify(result),
      },
    ],
  })

  const final = await client.messages.create({
    model: '{{SONNET_ID}}',
    max_tokens: 1024,
    tools,
    messages,
  })
  console.log(final.content[0])
}
```
