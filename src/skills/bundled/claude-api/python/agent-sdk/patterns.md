# Python Agent SDK – Common Patterns

## Custom Tools

```python
from anthropic_agents import Agent, tool

@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    return f"Sunny, 22°C in {location}"

agent = Agent(model="{{SONNET_ID}}", tools=[get_weather])
result = agent.run("What is the weather in London?")
```

## Streaming Agent Output

```python
async for event in agent.run_stream("Explain quantum computing"):
    if event.type == "text":
        print(event.text, end="", flush=True)
```

## Multi-agent Handoff

```python
from anthropic_agents import Agent, handoff

researcher = Agent(model="{{SONNET_ID}}", name="researcher")
writer = Agent(model="{{SONNET_ID}}", name="writer")

orchestrator = Agent(
    model="{{SONNET_ID}}",
    tools=[handoff(researcher), handoff(writer)],
)
```
