# Claude API – Prompt Caching

Cache expensive prompt prefixes to reduce latency and cost.

## Python

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="{{SONNET_ID}}",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": "<very long system prompt...>",
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[{"role": "user", "content": "Summarize the above."}],
)
print(response.usage.cache_read_input_tokens)
print(response.usage.cache_creation_input_tokens)
```

## TypeScript

```typescript
const response = await client.messages.create({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  system: [
    {
      type: 'text',
      text: '<very long system prompt...>',
      cache_control: { type: 'ephemeral' },
    },
  ],
  messages: [{ role: 'user', content: 'Summarize the above.' }],
})
```

## Rules

- Minimum cacheable prefix: 1024 tokens (Sonnet/Opus), 2048 (Haiku)
- Cache TTL: 5 minutes
- At most 4 cache breakpoints per request
