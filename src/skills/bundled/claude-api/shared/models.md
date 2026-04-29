# Claude Models

## Current Models

| Model | ID | Context | Best For |
|-------|-----|---------|---------|
| Claude Opus 4.6 | `claude-opus-4-6` | 200K | Complex reasoning, research |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 200K | Balanced performance |
| Claude Haiku 4.5 | `claude-haiku-4-5` | 200K | Fast, cost-efficient tasks |

## Selecting a Model

Use the exact model ID — do **not** append date suffixes (e.g. `claude-sonnet-4-6`, not `claude-sonnet-4-6-20250101`).

```python
model = "{{SONNET_ID}}"   # Recommended default
model = "{{OPUS_ID}}"     # For complex tasks
model = "{{HAIKU_ID}}"    # For fast/cheap tasks
```

## Legacy Aliases

| Alias | Resolves To |
|-------|------------|
| `claude-3-5-sonnet-latest` | Latest Sonnet 3.5 |
| `claude-3-opus-latest` | Latest Opus 3 |

See https://docs.anthropic.com/en/docs/about-claude/models for the full current list.
