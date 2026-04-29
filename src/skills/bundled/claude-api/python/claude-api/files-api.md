# Claude API – Python Files API

## Upload a File

```python
import anthropic

client = anthropic.Anthropic()

with open("document.pdf", "rb") as f:
    file_obj = client.beta.files.upload(
        file=("document.pdf", f, "application/pdf"),
    )

print(file_obj.id)
```

## Use File in Message

```python
message = client.beta.messages.create(
    model="{{SONNET_ID}}",
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "file", "file_id": file_obj.id},
                },
                {"type": "text", "text": "Summarize this document."},
            ],
        }
    ],
    betas=["files-api-2025-04-14"],
)
```

## List and Delete Files

```python
files = client.beta.files.list()
for f in files.data:
    print(f.id, f.filename)

client.beta.files.delete(file_obj.id)
```
