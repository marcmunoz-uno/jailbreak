# Claude API – PHP SDK

## Installation

```bash
composer require anthropics/anthropic-sdk-php
```

## Basic Usage

```php
<?php
use Anthropic\Client;

$client = Anthropic::client(getenv('ANTHROPIC_API_KEY'));

$response = $client->messages()->create([
    'model' => '{{SONNET_ID}}',
    'max_tokens' => 1024,
    'messages' => [
        ['role' => 'user', 'content' => 'Hello, Claude!'],
    ],
]);

echo $response->content[0]->text;
```

## Streaming

```php
$stream = $client->messages()->createStreamed([
    'model' => '{{SONNET_ID}}',
    'max_tokens' => 1024,
    'messages' => [['role' => 'user', 'content' => 'Tell me a story']],
]);

foreach ($stream as $event) {
    echo $event->choices[0]->delta->content ?? '';
}
```
