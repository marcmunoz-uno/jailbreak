# Claude API – Python Batches

## Create a Batch

```python
import anthropic

client = anthropic.Anthropic()

batch = client.messages.batches.create(
    requests=[
        {
            "custom_id": "request-1",
            "params": {
                "model": "{{SONNET_ID}}",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "Hello!"}],
            },
        },
        {
            "custom_id": "request-2",
            "params": {
                "model": "{{SONNET_ID}}",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "What is 2+2?"}],
            },
        },
    ]
)
print(batch.id)
```

## Poll for Results

```python
import time

while True:
    batch = client.messages.batches.retrieve(batch.id)
    if batch.processing_status == "ended":
        break
    time.sleep(10)

for result in client.messages.batches.results(batch.id):
    print(result.custom_id, result.result.message.content[0].text)
```
