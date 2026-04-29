# Claude API – C# SDK

## Installation

```bash
dotnet add package Anthropic.SDK
```

## Basic Usage

```csharp
using Anthropic.SDK;
using Anthropic.SDK.Messaging;

var client = new AnthropicClient(); // uses ANTHROPIC_API_KEY env var

var request = new MessageParameters
{
    Model = "{{SONNET_ID}}",
    MaxTokens = 1024,
    Messages = new List<Message>
    {
        new Message { Role = RoleType.User, Content = "Hello, Claude!" }
    }
};

var response = await client.Messages.GetClaudeMessageAsync(request);
Console.WriteLine(response.Content[0].Text);
```

## Streaming

```csharp
await foreach (var chunk in client.Messages.StreamClaudeMessageAsync(request))
{
    if (chunk.Delta?.Text is { } text)
        Console.Write(text);
}
```

## System Prompt

```csharp
var request = new MessageParameters
{
    Model = "{{SONNET_ID}}",
    MaxTokens = 1024,
    System = new List<SystemMessage>
    {
        new SystemMessage { Text = "You are a helpful assistant." }
    },
    Messages = new List<Message>
    {
        new Message { Role = RoleType.User, Content = "What is 2+2?" }
    }
};
```

## Multi-turn Conversation

```csharp
var messages = new List<Message>
{
    new Message { Role = RoleType.User, Content = "My name is Alice." },
    new Message { Role = RoleType.Assistant, Content = "Hello, Alice!" },
    new Message { Role = RoleType.User, Content = "What is my name?" }
};
```

## Tool Use

```csharp
var tools = new List<Tool>
{
    new Tool
    {
        Name = "get_weather",
        Description = "Get current weather for a location",
        InputSchema = new InputSchema
        {
            Type = "object",
            Properties = new Dictionary<string, Property>
            {
                ["location"] = new Property { Type = "string", Description = "City name" }
            },
            Required = new List<string> { "location" }
        }
    }
};

var request = new MessageParameters
{
    Model = "{{SONNET_ID}}",
    MaxTokens = 1024,
    Tools = tools,
    Messages = messages
};
```

## Error Handling

```csharp
try
{
    var response = await client.Messages.GetClaudeMessageAsync(request);
}
catch (AnthropicException ex) when (ex.StatusCode == 429)
{
    // Rate limited — back off and retry
    await Task.Delay(TimeSpan.FromSeconds(30));
}
catch (AnthropicException ex) when (ex.StatusCode == 529)
{
    // API overloaded
}
```

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your API key |
| `ANTHROPIC_BASE_URL` | Override API base URL |

## Resources

- [C# SDK GitHub](https://github.com/tghamm/Anthropic.SDK)
- [Anthropic API Reference](https://docs.anthropic.com/en/api)
