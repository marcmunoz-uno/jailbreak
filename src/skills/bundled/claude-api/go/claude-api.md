# Claude API – Go SDK

## Installation

```bash
go get github.com/anthropics/anthropic-sdk-go
```

## Basic Usage

```go
package main

import (
    "context"
    "fmt"
    anthropic "github.com/anthropics/anthropic-sdk-go"
)

func main() {
    client := anthropic.NewClient() // uses ANTHROPIC_API_KEY

    msg, err := client.Messages.New(context.Background(), anthropic.MessageNewParams{
        Model:     anthropic.F(anthropic.ModelClaude{{SONNET_ID}}),
        MaxTokens: anthropic.F(int64(1024)),
        Messages: anthropic.F([]anthropic.MessageParam{
            anthropic.UserMessage(anthropic.NewTextBlock("Hello, Claude!")),
        }),
    })
    if err != nil {
        panic(err)
    }
    fmt.Println(msg.Content[0].Text)
}
```

## Streaming

```go
stream := client.Messages.NewStreaming(ctx, anthropic.MessageNewParams{
    Model:     anthropic.F(anthropic.ModelClaude{{SONNET_ID}}),
    MaxTokens: anthropic.F(int64(1024)),
    Messages:  anthropic.F(messages),
})

for stream.Next() {
    event := stream.Current()
    // handle event
}
if err := stream.Err(); err != nil {
    panic(err)
}
```
