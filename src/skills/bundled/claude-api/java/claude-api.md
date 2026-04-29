# Claude API – Java SDK

## Installation (Maven)

```xml
<dependency>
  <groupId>com.anthropic</groupId>
  <artifactId>anthropic-java</artifactId>
  <version>LATEST</version>
</dependency>
```

## Basic Usage

```java
import com.anthropic.client.AnthropicClient;
import com.anthropic.client.okhttp.AnthropicOkHttpClient;
import com.anthropic.models.*;

AnthropicClient client = AnthropicOkHttpClient.fromEnv(); // uses ANTHROPIC_API_KEY

Message message = client.messages().create(
    MessageCreateParams.builder()
        .model(Model.CLAUDE_{{SONNET_ID}})
        .maxTokens(1024)
        .addUserMessage("Hello, Claude!")
        .build()
);
System.out.println(message.content().get(0).text().get().text());
```

## Streaming

```java
client.messages().createStreaming(params)
    .stream()
    .forEach(event -> System.out.print(
        event.delta().flatMap(d -> d.asText().map(t -> t.text())).orElse("")
    ));
```
