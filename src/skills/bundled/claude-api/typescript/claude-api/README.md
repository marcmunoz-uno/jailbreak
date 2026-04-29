# Claude API – TypeScript SDK

## Installation

```bash
npm install @anthropic-ai/sdk
```

## Quick Start

```typescript
import Anthropic from '@anthropic-ai/sdk'

const client = new Anthropic() // uses ANTHROPIC_API_KEY

const message = await client.messages.create({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Hello, Claude!' }],
})
console.log(message.content[0].type === 'text' ? message.content[0].text : '')
```

## With System Prompt

```typescript
const message = await client.messages.create({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  system: 'You are a helpful assistant.',
  messages: [{ role: 'user', content: 'What is TypeScript?' }],
})
```
