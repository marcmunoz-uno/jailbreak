# Anthropic Agents SDK – Python

The Python Agents SDK (`anthropic-agents`) provides higher-level primitives for building multi-turn agents.

## Installation

```bash
pip install anthropic-agents
```

## Quick Start

```python
from anthropic_agents import Agent

agent = Agent(model="{{SONNET_ID}}")
result = agent.run("Summarize the file README.md")
print(result.output)
```

## Key Concepts

- **Agent**: An autonomous Claude-powered agent that can use tools.
- **Tool**: A callable function exposed to the agent.
- **Runner**: Manages the agent loop (tool calls → results → next step).
