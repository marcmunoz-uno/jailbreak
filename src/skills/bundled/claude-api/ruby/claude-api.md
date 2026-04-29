# Claude API – Ruby SDK

## Installation

```bash
gem install anthropic
```

## Basic Usage

```ruby
require 'anthropic'

client = Anthropic::Client.new # uses ANTHROPIC_API_KEY env var

message = client.messages.create(
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Hello, Claude!' }]
)

puts message.content.first.text
```

## Streaming

```ruby
client.messages.stream(
  model: '{{SONNET_ID}}',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'Tell me a story' }]
) do |event|
  print event.delta&.text
end
```

## Multi-turn

```ruby
messages = [
  { role: 'user', content: 'My name is Alice.' },
  { role: 'assistant', content: 'Hello, Alice!' },
  { role: 'user', content: 'What is my name?' },
]
```
