# Claude API – TypeScript Files API

## Upload a File

```typescript
import Anthropic from '@anthropic-ai/sdk'
import fs from 'fs'

const client = new Anthropic()

const file = await client.beta.files.upload({
  file: new File([fs.readFileSync('document.pdf')], 'document.pdf', {
    type: 'application/pdf',
  }),
})
console.log(file.id)
```

## Use File in Message

```typescript
const message = await client.beta.messages.create({
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  messages: [
    {
      role: 'user',
      content: [
        { type: 'document', source: { type: 'file', file_id: file.id } },
        { type: 'text', text: 'Summarize this document.' },
      ],
    },
  ],
  betas: ['files-api-2025-04-14'],
})
```

## List and Delete Files

```typescript
const files = await client.beta.files.list()
for (const f of files.data) {
  console.log(f.id, f.filename)
}

await client.beta.files.delete(file.id)
```
