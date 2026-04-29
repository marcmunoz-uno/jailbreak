import { z } from 'zod/v4'
import { buildTool, type ToolDef } from '../../Tool.js'
import { lazySchema } from '../../utils/lazySchema.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    message: z.string().min(1).describe('The notification message to send'),
    channel: z
      .enum(['telegram', 'slack', 'webhook'])
      .optional()
      .default('telegram')
      .describe('Notification channel to use'),
    urgency: z
      .enum(['low', 'normal', 'high'])
      .optional()
      .default('normal')
      .describe('Urgency level of the notification'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

type Output = {
  sent: boolean
  channel: string
  error?: string
}

const PUSH_NOTIFICATION_TOOL_NAME = 'kairos_push_notification'

async function sendTelegram(message: string, urgency: string): Promise<void> {
  const token = process.env['TELEGRAM_BOT_TOKEN']
  const chatId = process.env['TELEGRAM_CHAT_ID']

  if (!token || !chatId) {
    throw new Error(
      'Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables',
    )
  }

  const prefix =
    urgency === 'high' ? '🚨 ' : urgency === 'low' ? 'ℹ️ ' : ''
  const text = `${prefix}${message}`

  const url = `https://api.telegram.org/bot${token}/sendMessage`
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`Telegram API error ${response.status}: ${body}`)
  }
}

async function sendSlack(message: string, urgency: string): Promise<void> {
  const webhookUrl = process.env['SLACK_WEBHOOK_URL']

  if (!webhookUrl) {
    throw new Error('Missing SLACK_WEBHOOK_URL environment variable')
  }

  const emoji = urgency === 'high' ? ':rotating_light:' : urgency === 'low' ? ':information_source:' : ':bell:'
  const text = `${emoji} ${message}`

  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`Slack webhook error ${response.status}: ${body}`)
  }
}

async function sendWebhook(message: string, urgency: string): Promise<void> {
  const webhookUrl = process.env['NOTIFICATION_WEBHOOK_URL']

  if (!webhookUrl) {
    throw new Error('Missing NOTIFICATION_WEBHOOK_URL environment variable')
  }

  const response = await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, urgency, timestamp: new Date().toISOString() }),
  })

  if (!response.ok) {
    const body = await response.text()
    throw new Error(`Webhook error ${response.status}: ${body}`)
  }
}

export const PushNotificationTool = buildTool({
  name: PUSH_NOTIFICATION_TOOL_NAME,
  searchHint: 'send push notifications via telegram, slack, or webhook',
  maxResultSizeChars: 100_000,
  async description(input) {
    const { channel } = input as { channel?: string }
    return `Claude wants to send a push notification via ${channel ?? 'telegram'}`
  },
  userFacingName() {
    return 'Push Notification'
  },
  get inputSchema(): InputSchema {
    return inputSchema()
  },
  isReadOnly() {
    return false
  },
  async checkPermissions(_input, _context) {
    return {
      behavior: 'allow' as const,
      decisionReason: { type: 'other' as const, reason: 'auto' },
    }
  },
  async call(input) {
    const { message, channel = 'telegram', urgency = 'normal' } = input

    try {
      switch (channel) {
        case 'telegram':
          await sendTelegram(message, urgency)
          break
        case 'slack':
          await sendSlack(message, urgency)
          break
        case 'webhook':
          await sendWebhook(message, urgency)
          break
      }

      return {
        data: { sent: true, channel },
      }
    } catch (err) {
      return {
        data: {
          sent: false,
          channel,
          error: err instanceof Error ? err.message : String(err),
        },
      }
    }
  },
  mapToolResultToToolResultBlockParam(output, toolUseID) {
    const content = output.sent
      ? `Notification sent via ${output.channel}`
      : `Failed to send notification via ${output.channel}: ${output.error}`

    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content,
    }
  },
} satisfies ToolDef<InputSchema, Output>)
