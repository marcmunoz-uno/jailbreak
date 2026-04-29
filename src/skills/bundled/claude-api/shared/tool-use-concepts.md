# Claude API – Tool Use Concepts

## Overview

Tool use (function calling) lets Claude invoke external functions to retrieve data or perform actions.

## Flow

1. Send a message with `tools` defined
2. Claude responds with `stop_reason: "tool_use"` and a `tool_use` content block
3. Execute the tool locally and return a `tool_result` message
4. Claude uses the result to form a final answer

## Tool Definition

```json
{
  "name": "get_stock_price",
  "description": "Get the current stock price for a ticker symbol.",
  "input_schema": {
    "type": "object",
    "properties": {
      "ticker": {
        "type": "string",
        "description": "Stock ticker, e.g. AAPL"
      }
    },
    "required": ["ticker"]
  }
}
```

## Tool Choice

| Value | Behavior |
|-------|---------|
| `auto` (default) | Claude decides whether to use a tool |
| `any` | Claude must use one of the provided tools |
| `tool` | Claude must use the specific named tool |
| `none` | Claude must not use any tools |

## Parallel Tool Use

Claude may invoke multiple tools in a single response. Handle all `tool_use` blocks and return all results before continuing.

## Best Practices

- Write clear, specific descriptions — Claude uses them to decide when to call
- Keep input schemas minimal and typed
- Return structured JSON from tools for best results
- Always handle the `tool_use` stop reason before treating the response as final
