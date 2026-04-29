# Claude API – Python SDK

## Installation

```bash
pip install anthropic
```

## Quick Start

```python
import anthropic

client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY

message = client.messages.create(
    model="{{SONNET_ID}}",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, Claude!"}],
)
print(message.content[0].text)
```

## Async Client

```python
import asyncio
import anthropic

async def main():
    client = anthropic.AsyncAnthropic()
    message = await client.messages.create(
        model="{{SONNET_ID}}",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(message.content[0].text)

asyncio.run(main())
```
