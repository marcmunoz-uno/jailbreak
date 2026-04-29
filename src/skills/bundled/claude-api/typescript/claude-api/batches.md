# Claude API – TypeScript Batches

## Create a Batch

```typescript
import Anthropic from '@anthropic-ai/sdk'

const client = new Anthropic()

const batch = await client.messages.batches.create({
  requests: [
    {
      custom_id: 'request-1',
      params: {
        model: '{{SONNET_ID}}',
        max_tokens: 1024,
        messages: [{ role: 'user', content: 'Hello!' }],
      },
    },
  ],
})
console.log(batch.id)
```

## Poll for Results

```typescript
let status = await client.messages.batches.retrieve(batch.id)
while (status.processing_status !== 'ended') {
  await new Promise(r => setTimeout(r, 10_000))
  status = await client.messages.batches.retrieve(batch.id)
}

for await (const result of await client.messages.batches.results(batch.id)) {
  if (result.result.type === 'succeeded') {
    console.log(result.custom_id, result.result.message.content[0])
  }
}
```
