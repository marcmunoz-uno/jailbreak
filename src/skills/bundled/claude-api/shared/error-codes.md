# Claude API – Error Codes

| Status | Error Type | Description | Action |
|--------|-----------|-------------|--------|
| 400 | `invalid_request_error` | Malformed request body | Fix your request |
| 401 | `authentication_error` | Invalid API key | Check ANTHROPIC_API_KEY |
| 403 | `permission_error` | Insufficient permissions | Check your plan |
| 404 | `not_found_error` | Resource not found | Check the ID |
| 429 | `rate_limit_error` | Too many requests | Exponential backoff |
| 500 | `api_error` | Internal server error | Retry with backoff |
| 529 | `overloaded_error` | API temporarily overloaded | Retry after 30s |

## Retry Strategy

```python
import time
import anthropic

client = anthropic.Anthropic(max_retries=3)  # auto-retries 429/529
```

```typescript
const client = new Anthropic({ maxRetries: 3 }) // auto-retries 429/529
```
