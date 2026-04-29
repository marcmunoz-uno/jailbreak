# Claude API – Python Streaming

## Basic Streaming

```python
import anthropic

client = anthropic.Anthropic()

with client.messages.stream(
    model="{{SONNET_ID}}",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a poem about the sea."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

## Async Streaming

```python
import asyncio
import anthropic

async def main():
    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model="{{SONNET_ID}}",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}],
    ) as stream:
        async for text in stream.text_stream:
            print(text, end="", flush=True)

asyncio.run(main())
```

## Low-level SSE Events

```python
with client.messages.stream(model="{{SONNET_ID}}", max_tokens=1024, messages=msgs) as stream:
    for event in stream:
        print(event.type)
```
