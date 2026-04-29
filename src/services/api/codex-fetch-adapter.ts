/**
 * Codex Fetch Adapter
 *
 * Intercepts fetch calls from the Anthropic SDK and routes them to
 * ChatGPT's Codex backend API, translating between Anthropic Messages API
 * format and OpenAI Responses API format.
 *
 * Supports:
 * - Text messages (user/assistant)
 * - System prompts → instructions
 * - Tool definitions (Anthropic input_schema → OpenAI parameters)
 * - Tool use (tool_use → function_call, tool_result → function_call_output)
 * - Streaming events translation
 *
 * Endpoint: https://chatgpt.com/backend-api/codex/responses
 */

import { getCodexOAuthTokens } from '../../utils/auth.js'

// ── Available Codex models ──────────────────────────────────────────
export const CODEX_MODELS = [
  { id: 'gpt-5.2-codex', label: 'GPT-5.2 Codex', description: 'Frontier agentic coding model' },
  { id: 'gpt-5.1-codex', label: 'GPT-5.1 Codex', description: 'Codex coding model' },
  { id: 'gpt-5.1-codex-mini', label: 'GPT-5.1 Codex Mini', description: 'Fast Codex model' },
  { id: 'gpt-5.1-codex-max', label: 'GPT-5.1 Codex Max', description: 'Max Codex model' },
  { id: 'gpt-5.4', label: 'GPT-5.4', description: 'Latest GPT' },
  { id: 'gpt-5.2', label: 'GPT-5.2', description: 'GPT-5.2' },
] as const

export const DEFAULT_CODEX_MODEL = 'gpt-5.4'

function getCodexFallbackModels(model: string): string[] {
  const ordered = [
    model,
    'gpt-5.4',
    'gpt-5.2-codex',
    'gpt-5.1-codex',
    'gpt-5.1-codex-max',
    'gpt-5.1-codex-mini',
    'gpt-5.2',
  ]
  return [...new Set(ordered)].filter(candidate => isCodexModel(candidate))
}

/**
 * Maps Claude model names to corresponding Codex model names.
 * @param claudeModel - The Claude model name to map
 * @returns The corresponding Codex model ID
 */
export function mapClaudeModelToCodex(claudeModel: string | null): string {
  if (!claudeModel) return DEFAULT_CODEX_MODEL
  if (isCodexModel(claudeModel)) return claudeModel
  const lower = claudeModel.toLowerCase()
  if (lower.includes('opus')) return 'gpt-5.1-codex-max'
  if (lower.includes('haiku')) return 'gpt-5.1-codex-mini'
  if (lower.includes('sonnet')) return 'gpt-5.4'
  return DEFAULT_CODEX_MODEL
}

/**
 * Checks if a given model string is a valid Codex model.
 * @param model - The model string to check
 * @returns True if the model is a Codex model, false otherwise
 */
export function isCodexModel(model: string): boolean {
  return CODEX_MODELS.some(m => m.id === model)
}

// ── JWT helpers ─────────────────────────────────────────────────────

const JWT_CLAIM_PATH = 'https://api.openai.com/auth'

/**
 * Extracts the account ID from a Codex JWT token.
 * @param token - The JWT token to extract the account ID from
 * @returns The account ID
 * @throws Error if the token is invalid or account ID cannot be extracted
 */
function extractAccountId(token: string): string {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) throw new Error('Invalid token')
    const payload = JSON.parse(atob(parts[1]))
    const accountId = payload?.[JWT_CLAIM_PATH]?.chatgpt_account_id
    if (!accountId) throw new Error('No account ID in token')
    return accountId
  } catch {
    throw new Error('Failed to extract account ID from Codex token')
  }
}

// ── Types ───────────────────────────────────────────────────────────

interface AnthropicContentBlock {
  type: string
  text?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  tool_use_id?: string
  content?: string | AnthropicContentBlock[]
  [key: string]: unknown
}

interface AnthropicMessage {
  role: string
  content: string | AnthropicContentBlock[]
}

interface AnthropicTool {
  name: string
  description?: string
  input_schema?: Record<string, unknown>
}

// ── Tool translation: Anthropic → Codex ─────────────────────────────

/**
 * Translates Anthropic tool definitions to Codex format.
 * @param anthropicTools - Array of Anthropic tool definitions
 * @returns Array of Codex-compatible tool objects
 */
function translateTools(anthropicTools: AnthropicTool[]): Array<Record<string, unknown>> {
  return anthropicTools.map(tool => ({
    type: 'function',
    name: tool.name,
    description: tool.description || '',
    parameters: tool.input_schema || { type: 'object', properties: {} },
    strict: null,
  }))
}

// ── Message translation: Anthropic → Codex input ────────────────────

/**
 * Translates Anthropic message format to Codex input format.
 * Handles text content, tool results, and image attachments.
 * @param anthropicMessages - Array of messages in Anthropic format
 * @returns Array of Codex-compatible input objects
 */
function translateMessages(
  anthropicMessages: AnthropicMessage[],
): Array<Record<string, unknown>> {
  const codexInput: Array<Record<string, unknown>> = []
  // Track tool_use IDs to generate call_ids for function_call_output
  // Anthropic uses tool_use_id, Codex uses call_id
  let toolCallCounter = 0

  for (const msg of anthropicMessages) {
    if (typeof msg.content === 'string') {
      codexInput.push({ role: msg.role, content: msg.content })
      continue
    }

    if (!Array.isArray(msg.content)) continue

    if (msg.role === 'user') {
      const contentArr: Array<Record<string, unknown>> = []
      for (const block of msg.content) {
        if (block.type === 'tool_result') {
          const callId = block.tool_use_id || `call_${toolCallCounter++}`
          let outputText = ''
          if (typeof block.content === 'string') {
            outputText = block.content
          } else if (Array.isArray(block.content)) {
            outputText = block.content
              .map(c => {
                if (c.type === 'text') return c.text
                if (c.type === 'image') return '[Image data attached]'
                return ''
              })
              .join('\n')
          }
          codexInput.push({
            type: 'function_call_output',
            call_id: callId,
            output: outputText || '',
          })
        } else if (block.type === 'text' && typeof block.text === 'string') {
          contentArr.push({ type: 'input_text', text: block.text })
        } else if (
          block.type === 'image' &&
          typeof block.source === 'object' &&
          block.source !== null &&
          (block.source as any).type === 'base64'
        ) {
          contentArr.push({
            type: 'input_image',
            image_url: `data:${(block.source as any).media_type};base64,${(block.source as any).data}`,
          })
        }
      }
      if (contentArr.length > 0) {
        if (contentArr.length === 1 && contentArr[0].type === 'input_text') {
          codexInput.push({ role: 'user', content: contentArr[0].text })
        } else {
          codexInput.push({ role: 'user', content: contentArr })
        }
      }
    } else {
      // Process assistant or tool blocks
      for (const block of msg.content) {
        if (block.type === 'text' && typeof block.text === 'string') {
          if (msg.role === 'assistant') {
            codexInput.push({
              type: 'message',
              role: 'assistant',
              content: [{ type: 'output_text', text: block.text, annotations: [] }],
              status: 'completed',
            })
          }
        } else if (block.type === 'tool_use') {
          const callId = block.id || `call_${toolCallCounter++}`
          codexInput.push({
            type: 'function_call',
            call_id: callId,
            name: block.name || '',
            arguments: JSON.stringify(block.input || {}),
          })
        }
      }
    }
  }

  return codexInput
}

// ── Full request translation ────────────────────────────────────────

/**
 * Translates a complete Anthropic API request body to Codex format.
 * @param anthropicBody - The Anthropic request body to translate
 * @returns Object containing the translated Codex body and model
 */
function translateToCodexBody(anthropicBody: Record<string, unknown>): {
  codexBody: Record<string, unknown>
  codexModel: string
} {
  const anthropicMessages = (anthropicBody.messages || []) as AnthropicMessage[]
  const systemPrompt = anthropicBody.system as
    | string
    | Array<{ type: string; text?: string; cache_control?: unknown }>
    | undefined
  const claudeModel = anthropicBody.model as string
  const anthropicTools = (anthropicBody.tools || []) as AnthropicTool[]

  const codexModel = mapClaudeModelToCodex(claudeModel)

  // Build system instructions
  let instructions = ''
  if (systemPrompt) {
    instructions =
      typeof systemPrompt === 'string'
        ? systemPrompt
        : Array.isArray(systemPrompt)
          ? systemPrompt
              .filter(b => b.type === 'text' && typeof b.text === 'string')
              .map(b => b.text!)
              .join('\n')
          : ''
  }

  // Convert messages
  const input = translateMessages(anthropicMessages)

  const codexBody: Record<string, unknown> = {
    model: codexModel,
    store: false,
    stream: true,
    instructions,
    input,
    tool_choice: 'auto',
    parallel_tool_calls: true,
  }

  // Add tools if present
  if (anthropicTools.length > 0) {
    codexBody.tools = translateTools(anthropicTools)
  }

  return { codexBody, codexModel }
}

// ── Response translation: Codex SSE → Anthropic SSE ─────────────────

/**
 * Formats data as Server-Sent Events (SSE) format.
 * @param event - The event type
 * @param data - The data payload
 * @returns Formatted SSE string
 */
function formatSSE(event: string, data: string): string {
  return `event: ${event}\ndata: ${data}\n\n`
}

/**
 * Translates Codex streaming response to Anthropic format.
 * Converts Codex SSE events into Anthropic-compatible streaming events.
 * @param codexResponse - The streaming response from Codex API
 * @param codexModel - The Codex model used for the request
 * @returns Transformed Response object with Anthropic-format stream
 */
async function translateCodexStreamToAnthropic(
  codexResponse: Response,
  codexModel: string,
): Promise<Response> {
  const messageId = `msg_codex_${Date.now()}`

  const readable = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder()
      let contentBlockIndex = 0
      let outputTokens = 0
      let inputTokens = 0

      // Emit Anthropic message_start
      controller.enqueue(
        encoder.encode(
          formatSSE(
            'message_start',
            JSON.stringify({
              type: 'message_start',
              message: {
                id: messageId,
                type: 'message',
                role: 'assistant',
                content: [],
                model: codexModel,
                stop_reason: null,
                stop_sequence: null,
                usage: { input_tokens: 0, output_tokens: 0 },
              },
            }),
          ),
        ),
      )

      // Emit ping
      controller.enqueue(
        encoder.encode(
          formatSSE('ping', JSON.stringify({ type: 'ping' })),
        ),
      )

      // Track state for tool calls
      let currentTextBlockStarted = false
      let currentToolCallId = ''
      let currentToolCallName = ''
      let currentToolCallArgs = ''
      let inToolCall = false
      let hadToolCalls = false
      let inReasoningBlock = false

      try {
        const reader = codexResponse.body?.getReader()
        if (!reader) {
          emitTextBlock(controller, encoder, contentBlockIndex, 'Error: No response body')
          finishStream(controller, encoder, outputTokens, inputTokens, false)
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue

            // Parse "event: xxx" lines
            if (trimmed.startsWith('event: ')) continue

            if (!trimmed.startsWith('data: ')) continue
            const dataStr = trimmed.slice(6)
            if (dataStr === '[DONE]') continue

            let event: Record<string, unknown>
            try {
              event = JSON.parse(dataStr)
            } catch {
              continue
            }

            const eventType = event.type as string

            // ── Text output events ──────────────────────────────
            if (eventType === 'response.output_item.added') {
              const item = event.item as Record<string, unknown>
              if (item?.type === 'reasoning') {
                inReasoningBlock = true
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_start',
                      JSON.stringify({
                        type: 'content_block_start',
                        index: contentBlockIndex,
                        content_block: { type: 'thinking', thinking: '' },
                      }),
                    ),
                  ),
                )
              } else if (item?.type === 'message') {
                // New text message block starting
                if (inToolCall) {
                  // Close the previous tool call block
                  closeToolCallBlock(controller, encoder, contentBlockIndex, currentToolCallId, currentToolCallName, currentToolCallArgs)
                  contentBlockIndex++
                  inToolCall = false
                }
              } else if (item?.type === 'function_call') {
                // Close text block if open
                if (currentTextBlockStarted) {
                  controller.enqueue(
                    encoder.encode(
                      formatSSE('content_block_stop', JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      })),
                    ),
                  )
                  contentBlockIndex++
                  currentTextBlockStarted = false
                }

                // Start tool_use block (Anthropic format)
                currentToolCallId = (item.call_id as string) || `toolu_${Date.now()}`
                currentToolCallName = (item.name as string) || ''
                currentToolCallArgs = (item.arguments as string) || ''
                inToolCall = true
                hadToolCalls = true

                controller.enqueue(
                  encoder.encode(
                    formatSSE('content_block_start', JSON.stringify({
                      type: 'content_block_start',
                      index: contentBlockIndex,
                      content_block: {
                        type: 'tool_use',
                        id: currentToolCallId,
                        name: currentToolCallName,
                        input: {},
                      },
                    })),
                  ),
                )
              }
            }

            // Text deltas
            else if (eventType === 'response.output_text.delta') {
              const text = event.delta as string
              if (typeof text === 'string' && text.length > 0) {
                if (!currentTextBlockStarted) {
                  // Start a new text content block
                  controller.enqueue(
                    encoder.encode(
                      formatSSE('content_block_start', JSON.stringify({
                        type: 'content_block_start',
                        index: contentBlockIndex,
                        content_block: { type: 'text', text: '' },
                      })),
                    ),
                  )
                  currentTextBlockStarted = true
                }
                controller.enqueue(
                  encoder.encode(
                    formatSSE('content_block_delta', JSON.stringify({
                      type: 'content_block_delta',
                      index: contentBlockIndex,
                      delta: { type: 'text_delta', text },
                    })),
                  ),
                )
                outputTokens += 1
              }
            }
            
            // Reasoning deltas
            else if (eventType === 'response.reasoning.delta') {
              const text = event.delta as string
              if (typeof text === 'string' && text.length > 0) {
                if (!inReasoningBlock) {
                  inReasoningBlock = true
                  controller.enqueue(
                    encoder.encode(
                      formatSSE('content_block_start', JSON.stringify({
                        type: 'content_block_start',
                        index: contentBlockIndex,
                        content_block: { type: 'thinking', thinking: '' },
                      })),
                    ),
                  )
                }
                controller.enqueue(
                  encoder.encode(
                    formatSSE('content_block_delta', JSON.stringify({
                      type: 'content_block_delta',
                      index: contentBlockIndex,
                      delta: { type: 'thinking_delta', thinking: text },
                    })),
                  ),
                )
                outputTokens += 1 // approximate token counts
              }
            }

            // ── Tool call argument deltas ───────────────────────
            else if (eventType === 'response.function_call_arguments.delta') {
              const argDelta = event.delta as string
              if (typeof argDelta === 'string' && inToolCall) {
                currentToolCallArgs += argDelta
                controller.enqueue(
                  encoder.encode(
                    formatSSE('content_block_delta', JSON.stringify({
                      type: 'content_block_delta',
                      index: contentBlockIndex,
                      delta: {
                        type: 'input_json_delta',
                        partial_json: argDelta,
                      },
                    })),
                  ),
                )
              }
            }

            // Tool call arguments complete
            else if (eventType === 'response.function_call_arguments.done') {
              if (inToolCall) {
                currentToolCallArgs = (event.arguments as string) || currentToolCallArgs
              }
            }

            // Output item done — close blocks
            else if (eventType === 'response.output_item.done') {
              const item = event.item as Record<string, unknown>
              if (item?.type === 'function_call') {
                closeToolCallBlock(controller, encoder, contentBlockIndex, currentToolCallId, currentToolCallName, currentToolCallArgs)
                contentBlockIndex++
                inToolCall = false
                currentToolCallArgs = ''
              } else if (item?.type === 'message') {
                if (currentTextBlockStarted) {
                  controller.enqueue(
                    encoder.encode(
                      formatSSE('content_block_stop', JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      })),
                    ),
                  )
                  contentBlockIndex++
                  currentTextBlockStarted = false
                }
              } else if (item?.type === 'reasoning') {
                if (inReasoningBlock) {
                  controller.enqueue(
                    encoder.encode(
                      formatSSE('content_block_stop', JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      })),
                    ),
                  )
                  contentBlockIndex++
                  inReasoningBlock = false
                }
              }
            }

            // Response completed — extract usage
            else if (eventType === 'response.completed') {
              const response = event.response as Record<string, unknown>
              const usage = response?.usage as Record<string, number> | undefined
              if (usage) {
                outputTokens = usage.output_tokens || outputTokens
                inputTokens = usage.input_tokens || inputTokens
              }
            }
          }
        }
      } catch (err) {
        // If we're in the middle of a text block, emit the error there
        if (!currentTextBlockStarted) {
          controller.enqueue(
            encoder.encode(
              formatSSE('content_block_start', JSON.stringify({
                type: 'content_block_start',
                index: contentBlockIndex,
                content_block: { type: 'text', text: '' },
              })),
            ),
          )
          currentTextBlockStarted = true
        }
        controller.enqueue(
          encoder.encode(
            formatSSE('content_block_delta', JSON.stringify({
              type: 'content_block_delta',
              index: contentBlockIndex,
              delta: { type: 'text_delta', text: `\n\n[Error: ${String(err)}]` },
            })),
          ),
        )
      }

      // Close any remaining open blocks
      if (currentTextBlockStarted) {
        controller.enqueue(
          encoder.encode(
            formatSSE('content_block_stop', JSON.stringify({
              type: 'content_block_stop',
              index: contentBlockIndex,
            })),
          ),
        )
      }
      if (inReasoningBlock) {
        controller.enqueue(
          encoder.encode(
            formatSSE('content_block_stop', JSON.stringify({
              type: 'content_block_stop',
              index: contentBlockIndex,
            })),
          ),
        )
      }
      if (inToolCall) {
        closeToolCallBlock(controller, encoder, contentBlockIndex, currentToolCallId, currentToolCallName, currentToolCallArgs)
      }

      finishStream(controller, encoder, outputTokens, inputTokens, hadToolCalls)
    },
  })

  function closeToolCallBlock(
    controller: ReadableStreamDefaultController,
    encoder: TextEncoder,
    index: number,
    _toolCallId: string,
    _toolCallName: string,
    _toolCallArgs: string,
  ) {
    controller.enqueue(
      encoder.encode(
        formatSSE('content_block_stop', JSON.stringify({
          type: 'content_block_stop',
          index,
        })),
      ),
    )
  }

  function emitTextBlock(
    controller: ReadableStreamDefaultController,
    encoder: TextEncoder,
    index: number,
    text: string,
  ) {
    controller.enqueue(
      encoder.encode(
        formatSSE('content_block_start', JSON.stringify({
          type: 'content_block_start',
          index,
          content_block: { type: 'text', text: '' },
        })),
      ),
    )
    controller.enqueue(
      encoder.encode(
        formatSSE('content_block_delta', JSON.stringify({
          type: 'content_block_delta',
          index,
          delta: { type: 'text_delta', text },
        })),
      ),
    )
    controller.enqueue(
      encoder.encode(
        formatSSE('content_block_stop', JSON.stringify({
          type: 'content_block_stop',
          index,
        })),
      ),
    )
  }

  function finishStream(
    controller: ReadableStreamDefaultController,
    encoder: TextEncoder,
    outputTokens: number,
    inputTokens: number,
    hadToolCalls: boolean,
  ) {
    // Use 'tool_use' stop reason when model made tool calls
    const stopReason = hadToolCalls ? 'tool_use' : 'end_turn'

    controller.enqueue(
      encoder.encode(
        formatSSE(
          'message_delta',
          JSON.stringify({
            type: 'message_delta',
            delta: { stop_reason: stopReason, stop_sequence: null },
            usage: { output_tokens: outputTokens },
          }),
        ),
      ),
    )
    controller.enqueue(
      encoder.encode(
        formatSSE(
          'message_stop',
          JSON.stringify({
            type: 'message_stop',
            'amazon-bedrock-invocationMetrics': {
              inputTokenCount: inputTokens,
              outputTokenCount: outputTokens,
              invocationLatency: 0,
              firstByteLatency: 0,
            },
            usage: { input_tokens: inputTokens, output_tokens: outputTokens },
          }),
        ),
      ),
    )
    controller.close()
  }

  return new Response(readable, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'x-request-id': messageId,
    },
  })
}

// ── Main fetch interceptor ──────────────────────────────────────────

const CODEX_BASE_URL = 'https://chatgpt.com/backend-api/codex/responses'

function joinUrl(baseUrl: string, path: string): string {
  return `${baseUrl.replace(/\/+$/, '')}${path}`
}

function extractAnthropicText(
  content: unknown,
): string {
  if (typeof content === 'string') {
    return content
  }
  if (!Array.isArray(content)) {
    return ''
  }
  return content
    .map(block => {
      if (
        typeof block === 'object' &&
        block !== null &&
        'type' in block &&
        block.type === 'text' &&
        'text' in block &&
        typeof block.text === 'string'
      ) {
        return block.text
      }
      return ''
    })
    .filter(Boolean)
    .join('\n')
}

function anthropicSystemToOpenAIMessage(
  system: unknown,
): Array<Record<string, unknown>> {
  const text = extractAnthropicText(system)
  if (!text) {
    return []
  }
  return [{ role: 'system', content: text }]
}

function anthropicMessagesToOpenAIChatMessages(
  anthropicMessages: AnthropicMessage[],
): Array<Record<string, unknown>> {
  const openAIMessages: Array<Record<string, unknown>> = []

  for (const msg of anthropicMessages) {
    if (typeof msg.content === 'string') {
      openAIMessages.push({
        role: msg.role,
        content: msg.content,
      })
      continue
    }

    if (!Array.isArray(msg.content)) {
      continue
    }

    if (msg.role === 'user') {
      const userParts: Array<Record<string, unknown>> = []

      for (const block of msg.content) {
        if (block.type === 'text' && typeof block.text === 'string') {
          userParts.push({ type: 'text', text: block.text })
        } else if (
          block.type === 'image' &&
          typeof block.source === 'object' &&
          block.source !== null &&
          (block.source as { type?: string }).type === 'base64'
        ) {
          const source = block.source as {
            media_type?: string
            data?: string
          }
          if (source.media_type && source.data) {
            userParts.push({
              type: 'image_url',
              image_url: {
                url: `data:${source.media_type};base64,${source.data}`,
              },
            })
          }
        } else if (block.type === 'tool_result') {
          openAIMessages.push({
            role: 'tool',
            tool_call_id: block.tool_use_id || `tool_${Date.now()}`,
            content: typeof block.content === 'string'
              ? block.content
              : extractAnthropicText(block.content),
          })
        }
      }

      if (userParts.length > 0) {
        openAIMessages.push({
          role: 'user',
          content:
            userParts.length === 1 && userParts[0]?.type === 'text'
              ? userParts[0].text
              : userParts,
        })
      }
      continue
    }

    if (msg.role === 'assistant') {
      const textParts: string[] = []
      const toolCalls: Array<Record<string, unknown>> = []

      for (const block of msg.content) {
        if (block.type === 'text' && typeof block.text === 'string') {
          textParts.push(block.text)
        } else if (block.type === 'tool_use') {
          toolCalls.push({
            id: block.id || `call_${Date.now()}`,
            type: 'function',
            function: {
              name: block.name || '',
              arguments: JSON.stringify(block.input || {}),
            },
          })
        }
      }

      if (textParts.length > 0 || toolCalls.length > 0) {
        openAIMessages.push({
          role: 'assistant',
          ...(textParts.length > 0 ? { content: textParts.join('\n') } : {}),
          ...(toolCalls.length > 0 ? { tool_calls: toolCalls } : {}),
        })
      }
    }
  }

  return openAIMessages
}

function anthropicToolsToOpenAITools(
  anthropicTools: unknown,
): Array<Record<string, unknown>> | undefined {
  if (!Array.isArray(anthropicTools) || anthropicTools.length === 0) {
    return undefined
  }

  return anthropicTools.map(tool => {
    const typedTool = tool as AnthropicTool
    return {
      type: 'function',
      function: {
        name: typedTool.name,
        description: typedTool.description || '',
        parameters: typedTool.input_schema || {
          type: 'object',
          properties: {},
        },
      },
    }
  })
}

function buildAnthropicJsonResponseFromOpenAI(
  openAIResponse: Record<string, unknown>,
  model: string,
): Response {
  const choices = Array.isArray(openAIResponse.choices)
    ? (openAIResponse.choices as Array<Record<string, unknown>>)
    : []
  const firstChoice = choices[0] || {}
  const message =
    typeof firstChoice.message === 'object' && firstChoice.message !== null
      ? (firstChoice.message as Record<string, unknown>)
      : {}
  const toolCalls = Array.isArray(message.tool_calls)
    ? (message.tool_calls as Array<Record<string, unknown>>)
    : []
  const contentBlocks: Array<Record<string, unknown>> = []
  const messageContent =
    typeof message.content === 'string' ? message.content : ''

  if (messageContent) {
    contentBlocks.push({ type: 'text', text: messageContent })
  }

  for (const toolCall of toolCalls) {
    const fn =
      typeof toolCall.function === 'object' && toolCall.function !== null
        ? (toolCall.function as Record<string, unknown>)
        : {}
    let parsedArgs: Record<string, unknown> = {}
    if (typeof fn.arguments === 'string') {
      try {
        parsedArgs = JSON.parse(fn.arguments) as Record<string, unknown>
      } catch {
        parsedArgs = {}
      }
    }
    contentBlocks.push({
      type: 'tool_use',
      id:
        typeof toolCall.id === 'string' ? toolCall.id : `toolu_${Date.now()}`,
      name: typeof fn.name === 'string' ? fn.name : '',
      input: parsedArgs,
    })
  }

  const usage =
    typeof openAIResponse.usage === 'object' && openAIResponse.usage !== null
      ? (openAIResponse.usage as Record<string, number>)
      : {}
  const finishReason =
    typeof firstChoice.finish_reason === 'string'
      ? firstChoice.finish_reason
      : 'stop'
  const stopReason =
    finishReason === 'tool_calls' ? 'tool_use' : 'end_turn'

  return new Response(
    JSON.stringify({
      id:
        typeof openAIResponse.id === 'string'
          ? openAIResponse.id
          : `msg_${Date.now()}`,
      type: 'message',
      role: 'assistant',
      model,
      content: contentBlocks,
      stop_reason: stopReason,
      stop_sequence: null,
      usage: {
        input_tokens:
          typeof usage.prompt_tokens === 'number' ? usage.prompt_tokens : 0,
        output_tokens:
          typeof usage.completion_tokens === 'number'
            ? usage.completion_tokens
            : 0,
      },
    }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    },
  )
}

async function translateOpenAIChatStreamToAnthropic(
  openAIResponse: Response,
  model: string,
): Promise<Response> {
  const encoder = new TextEncoder()
  const messageId = `msg_${Date.now()}`

  const readable = new ReadableStream({
    async start(controller) {
      let contentBlockIndex = 0
      let inputTokens = 0
      let outputTokens = 0
      let currentTextBlockStarted = false
      let currentToolIndex: number | null = null
      const toolCallState = new Map<
        number,
        { id: string; name: string; args: string; started: boolean }
      >()

      controller.enqueue(
        encoder.encode(
          formatSSE(
            'message_start',
            JSON.stringify({
              type: 'message_start',
              message: {
                id: messageId,
                type: 'message',
                role: 'assistant',
                model,
                content: [],
                stop_reason: null,
                stop_sequence: null,
                usage: { input_tokens: 0, output_tokens: 0 },
              },
            }),
          ),
        ),
      )
      controller.enqueue(
        encoder.encode(formatSSE('ping', JSON.stringify({ type: 'ping' }))),
      )

      try {
        const reader = openAIResponse.body?.getReader()
        if (!reader) {
          emitTextBlock(
            controller,
            encoder,
            contentBlockIndex,
            'Error: No response body',
          )
          finishStream(controller, encoder, outputTokens, inputTokens, false)
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''
        let hadToolCalls = false

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() || ''

          for (const chunk of chunks) {
            const dataLine = chunk
              .split('\n')
              .find(line => line.startsWith('data: '))
            if (!dataLine) continue
            const dataStr = dataLine.slice(6).trim()
            if (!dataStr || dataStr === '[DONE]') continue

            let payload: Record<string, unknown>
            try {
              payload = JSON.parse(dataStr) as Record<string, unknown>
            } catch {
              continue
            }

            if (
              typeof payload.usage === 'object' &&
              payload.usage !== null &&
              !Array.isArray(payload.usage)
            ) {
              const usage = payload.usage as Record<string, number>
              inputTokens = usage.prompt_tokens || inputTokens
              outputTokens = usage.completion_tokens || outputTokens
            }

            const choices = Array.isArray(payload.choices)
              ? (payload.choices as Array<Record<string, unknown>>)
              : []
            const firstChoice = choices[0]
            if (!firstChoice) continue
            const delta =
              typeof firstChoice.delta === 'object' && firstChoice.delta !== null
                ? (firstChoice.delta as Record<string, unknown>)
                : {}

            if (typeof delta.content === 'string' && delta.content.length > 0) {
              if (currentToolIndex !== null) {
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_stop',
                      JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      }),
                    ),
                  ),
                )
                contentBlockIndex++
                currentToolIndex = null
              }
              if (!currentTextBlockStarted) {
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_start',
                      JSON.stringify({
                        type: 'content_block_start',
                        index: contentBlockIndex,
                        content_block: { type: 'text', text: '' },
                      }),
                    ),
                  ),
                )
                currentTextBlockStarted = true
              }
              controller.enqueue(
                encoder.encode(
                  formatSSE(
                    'content_block_delta',
                    JSON.stringify({
                      type: 'content_block_delta',
                      index: contentBlockIndex,
                      delta: { type: 'text_delta', text: delta.content },
                    }),
                  ),
                ),
              )
            }

            const toolCalls = Array.isArray(delta.tool_calls)
              ? (delta.tool_calls as Array<Record<string, unknown>>)
              : []
            for (const toolCallDelta of toolCalls) {
              const index =
                typeof toolCallDelta.index === 'number'
                  ? toolCallDelta.index
                  : 0
              let state = toolCallState.get(index)
              if (!state) {
                state = {
                  id: '',
                  name: '',
                  args: '',
                  started: false,
                }
                toolCallState.set(index, state)
              }

              if (typeof toolCallDelta.id === 'string') {
                state.id = toolCallDelta.id
              }
              const fn =
                typeof toolCallDelta.function === 'object' &&
                toolCallDelta.function !== null
                  ? (toolCallDelta.function as Record<string, unknown>)
                  : {}
              if (typeof fn.name === 'string') {
                state.name = fn.name
              }
              if (typeof fn.arguments === 'string') {
                state.args += fn.arguments
              }

              if (!state.started) {
                if (currentTextBlockStarted) {
                  controller.enqueue(
                    encoder.encode(
                      formatSSE(
                        'content_block_stop',
                        JSON.stringify({
                          type: 'content_block_stop',
                          index: contentBlockIndex,
                        }),
                      ),
                    ),
                  )
                  contentBlockIndex++
                  currentTextBlockStarted = false
                }
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_start',
                      JSON.stringify({
                        type: 'content_block_start',
                        index: contentBlockIndex,
                        content_block: {
                          type: 'tool_use',
                          id: state.id || `toolu_${Date.now()}`,
                          name: state.name,
                          input: {},
                        },
                      }),
                    ),
                  ),
                )
                state.started = true
                currentToolIndex = index
                hadToolCalls = true
              }

              if (typeof fn.arguments === 'string' && fn.arguments.length > 0) {
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_delta',
                      JSON.stringify({
                        type: 'content_block_delta',
                        index: contentBlockIndex,
                        delta: {
                          type: 'input_json_delta',
                          partial_json: fn.arguments,
                        },
                      }),
                    ),
                  ),
                )
              }
            }

            if (typeof firstChoice.finish_reason === 'string') {
              if (currentTextBlockStarted) {
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_stop',
                      JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      }),
                    ),
                  ),
                )
                contentBlockIndex++
                currentTextBlockStarted = false
              }
              if (currentToolIndex !== null) {
                controller.enqueue(
                  encoder.encode(
                    formatSSE(
                      'content_block_stop',
                      JSON.stringify({
                        type: 'content_block_stop',
                        index: contentBlockIndex,
                      }),
                    ),
                  ),
                )
                contentBlockIndex++
                currentToolIndex = null
              }
            }
          }
        }

        finishStream(
          controller,
          encoder,
          outputTokens,
          inputTokens,
          toolCallState.size > 0,
        )
      } catch (err) {
        emitTextBlock(
          controller,
          encoder,
          contentBlockIndex,
          `Error: ${String(err)}`,
        )
        finishStream(controller, encoder, outputTokens, inputTokens, false)
      }
    },
  })

  return new Response(readable, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'x-request-id': messageId,
    },
  })
}

export function createOpenAICompatibleFetch(
  apiKey: string,
  {
    baseUrl,
    modelOverride,
  }: {
    baseUrl: string
    modelOverride?: string
  },
): (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> {
  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = input instanceof Request ? input.url : String(input)
    if (!url.includes('/v1/messages')) {
      return globalThis.fetch(input, init)
    }

    let anthropicBody: Record<string, unknown>
    try {
      const bodyText =
        init?.body instanceof ReadableStream
          ? await new Response(init.body).text()
          : typeof init?.body === 'string'
            ? init.body
            : '{}'
      anthropicBody = JSON.parse(bodyText)
    } catch {
      anthropicBody = {}
    }

    const model =
      modelOverride ||
      (typeof anthropicBody.model === 'string' ? anthropicBody.model : '')
    if (!model) {
      return new Response(
        JSON.stringify({
          type: 'error',
          error: {
            type: 'invalid_request_error',
            message:
              'No OpenAI-compatible model configured. Set OPENAI_MODEL or pass --model.',
          },
        }),
        {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        },
      )
    }

    const stream = anthropicBody.stream === true
    const messages = anthropicMessagesToOpenAIChatMessages(
      Array.isArray(anthropicBody.messages)
        ? (anthropicBody.messages as AnthropicMessage[])
        : [],
    )
    const systemMessages = anthropicSystemToOpenAIMessage(anthropicBody.system)
    const tools = anthropicToolsToOpenAITools(anthropicBody.tools)
    const requestBody: Record<string, unknown> = {
      model,
      messages: [...systemMessages, ...messages],
      stream,
      // Anthropic Messages uses max_tokens; newer OpenAI chat/completions
      // models such as GPT-5 expect max_completion_tokens instead.
      ...(typeof anthropicBody.max_tokens === 'number'
        ? { max_completion_tokens: anthropicBody.max_tokens }
        : {}),
      ...(tools ? { tools } : {}),
    }

    const response = await fetchWith429Retry(
      joinUrl(baseUrl, '/chat/completions'),
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(requestBody),
      },
    )

    if (!response.ok) {
      const errorText = await response.text()
      return new Response(
        JSON.stringify({
          type: 'error',
          error: {
            type: 'api_error',
            message: `OpenAI-compatible API error (${response.status}): ${errorText}`,
          },
        }),
        {
          status: response.status,
          headers: { 'Content-Type': 'application/json' },
        },
      )
    }

    if (stream) {
      return translateOpenAIChatStreamToAnthropic(response, model)
    }

    const json = (await response.json()) as Record<string, unknown>
    return buildAnthropicJsonResponseFromOpenAI(json, model)
  }
}

const OPENAI_COMPATIBLE_MAX_RETRIES = 3
const OPENAI_COMPATIBLE_BASE_DELAY_MS = 1500
const OPENAI_COMPATIBLE_MAX_DELAY_MS = 15000

function getRetryDelayMs(response: Response, attempt: number): number {
  const retryAfter = response.headers.get('retry-after')
  if (retryAfter) {
    const seconds = Number(retryAfter)
    if (Number.isFinite(seconds) && seconds >= 0) {
      return Math.min(seconds * 1000, OPENAI_COMPATIBLE_MAX_DELAY_MS)
    }

    const retryAt = Date.parse(retryAfter)
    if (Number.isFinite(retryAt)) {
      return Math.min(
        Math.max(0, retryAt - Date.now()),
        OPENAI_COMPATIBLE_MAX_DELAY_MS,
      )
    }
  }

  const exponentialDelay =
    OPENAI_COMPATIBLE_BASE_DELAY_MS * 2 ** Math.max(0, attempt - 1)
  return Math.min(exponentialDelay, OPENAI_COMPATIBLE_MAX_DELAY_MS)
}

async function fetchWith429Retry(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  for (let attempt = 1; ; attempt++) {
    const response = await globalThis.fetch(input, init)
    const shouldRetry =
      (response.status === 429 || response.status >= 500) &&
      attempt <= OPENAI_COMPATIBLE_MAX_RETRIES

    if (!shouldRetry) {
      return response
    }

    const delayMs = getRetryDelayMs(response, attempt)
    await new Promise(resolve => setTimeout(resolve, delayMs))
  }
}

/**
 * Creates a fetch function that intercepts Anthropic API calls and routes them to Codex.
 * @param accessToken - The Codex access token for authentication
 * @returns A fetch function that translates Anthropic requests to Codex format
 */
export function createCodexFetch(
  accessToken: string,
): (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> {
  const accountId = extractAccountId(accessToken)

  return async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = input instanceof Request ? input.url : String(input)

    // Only intercept Anthropic API message calls
    if (!url.includes('/v1/messages')) {
      return globalThis.fetch(input, init)
    }

    // Parse the Anthropic request body
    let anthropicBody: Record<string, unknown>
    try {
      const bodyText =
        init?.body instanceof ReadableStream
          ? await new Response(init.body).text()
          : typeof init?.body === 'string'
            ? init.body
            : '{}'
      anthropicBody = JSON.parse(bodyText)
    } catch {
      anthropicBody = {}
    }

    // Get current token (may have been refreshed)
    const tokens = getCodexOAuthTokens()
    const currentToken = tokens?.accessToken || accessToken

    // Translate to Codex format
    const { codexBody, codexModel } = translateToCodexBody(anthropicBody)

    const callCodexApi = async (
      model: string,
    ): Promise<{ response: Response; model: string }> => {
      const body = { ...codexBody, model }
      const response = await globalThis.fetch(CODEX_BASE_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          Authorization: `Bearer ${currentToken}`,
          'chatgpt-account-id': accountId,
          originator: 'pi',
          'OpenAI-Beta': 'responses=experimental',
        },
        body: JSON.stringify(body),
      })
      return { response, model }
    }

    let { response: codexResponse, model: resolvedCodexModel } =
      await callCodexApi(codexModel)

    if (!codexResponse.ok && codexResponse.status === 404) {
      for (const fallbackModel of getCodexFallbackModels(codexModel)) {
        if (fallbackModel === resolvedCodexModel) {
          continue
        }
        const retry = await callCodexApi(fallbackModel)
        if (retry.response.ok) {
          codexResponse = retry.response
          resolvedCodexModel = retry.model
          break
        }
      }
    }

    if (!codexResponse.ok) {
      const errorText = await codexResponse.text()
      const errorBody = {
        type: 'error',
        error: {
          type: 'api_error',
          message: `Codex API error (${codexResponse.status}): ${errorText}`,
        },
      }
      return new Response(JSON.stringify(errorBody), {
        status: codexResponse.status,
        headers: { 'Content-Type': 'application/json' },
      })
    }

    // Translate streaming response
    return translateCodexStreamToAnthropic(codexResponse, resolvedCodexModel)
  }
}
