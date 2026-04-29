# Claude API – Python Tool Use

## Define and Use a Tool

```python
import anthropic
import json

client = anthropic.Anthropic()

tools = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, e.g. 'London'",
                },
            },
            "required": ["location"],
        },
    }
]

messages = [{"role": "user", "content": "What's the weather in Paris?"}]

response = client.messages.create(
    model="{{SONNET_ID}}",
    max_tokens=1024,
    tools=tools,
    messages=messages,
)

# Handle tool use
if response.stop_reason == "tool_use":
    tool_use = next(b for b in response.content if b.type == "tool_use")
    tool_result = {"location": tool_use.input["location"], "temp": "20°C, sunny"}

    messages.append({"role": "assistant", "content": response.content})
    messages.append({
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(tool_result)}],
    })

    final = client.messages.create(model="{{SONNET_ID}}", max_tokens=1024, tools=tools, messages=messages)
    print(final.content[0].text)
```
