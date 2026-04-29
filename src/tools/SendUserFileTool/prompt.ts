export const SEND_USER_FILE_TOOL_NAME = 'kairos_send_user_file'

export const SEND_USER_FILE_DESCRIPTION = 'Deliver one or more files directly to the user without an accompanying message. Use when the user asks for a file, export, download, or artifact.'

export const SEND_USER_FILE_PROMPT = `Deliver one or more files directly to the user. Use when:
- The user requests a file, export, or download
- You have generated an artifact (report, image, data file) to hand off
- A file is more useful than pasting its contents inline

The files are delivered immediately. Each path must be absolute or relative to cwd.`
