# Claude API – TypeScript Streaming

## Basic Streaming

```typescript
import Anthropic from '@anthropic-ai/sdk'

const client = new Anthropic()

const stream = client.messages.stream({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Write a poem about the ocean.' }],
})

for await (const event of stream) {
  if (
    event.type === 'content_block_delta' &&
    event.delta.type === 'text_delta'
  ) {
    process.stdout.write(event.delta.text)
  }
}

const finalMessage = await stream.finalMessage()
console.log('\nUsage:', finalMessage.usage)
```

## Using `.on()` Callbacks

```typescript
const message = await client.messages
  .stream({
    model: '{{SONNET_ID}}',
    max_tokens: 1024,
    messages: [{ role: 'user', content: 'Hello!' }],
  })
  .on('text', text => process.stdout.write(text))
  .finalMessage()
```
