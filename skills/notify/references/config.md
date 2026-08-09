# Configuration

## Resolution order (later overrides earlier, key by key)

1. **Global** — `~/.config/notify/config.json`
2. **Project** — `./.notify.json` in the working directory
3. **Explicit** — `--config <path>` replaces both

Merge is deep: a project file can override just `default_channel` or one email
field while inheriting the rest from global.

## Schema

| Key | Type | Notes |
|---|---|---|
| `default_channel` | string | `telegram` \| `email` \| `both` (default `telegram`) |
| `telegram.bot_token_env` | string | env var holding the bot token (default `TELEGRAM_BOT_TOKEN`) |
| `telegram.chat_id` | string/int | where to send; from `telegram_get_chat_id.py`. In `topics` mode this is the forum **supergroup** id (negative). |
| `telegram.mode` | string | `dm` (one shared chat) or `topics` (one forum topic per `--job`). `topics` requires the dispatcher. See `references/concurrency.md`. |
| `dispatcher.enabled` | bool | route Telegram through the `notifyd` dispatcher (auto-on when `mode==topics`). Needed for concurrent jobs and reply-waiting at scale. |
| `dispatcher.spool_dir` | string | request/answer spool (default `~/.local/state/notify/spool`) |
| `dispatcher.close_topic_on_complete` | bool | close a job's topic on a `complete`/`error` event (default true) |
| `email.backend` | string | `smtp` (script sends) \| `connector` (Claude sends via MCP) |
| `email.to` | string | recipient inbox |
| `email.from` | string | envelope From |
| `email.smtp.provider` | string | `gmail` \| `m365` \| `outlook` — fills host/port/starttls automatically |
| `email.smtp.host`/`port`/`starttls` | — | override or set manually for a custom server |
| `email.smtp.username_env`/`password_env` | string | env vars for SMTP creds (default `SMTP_USER`/`SMTP_PASS`) |
| `events` | object | per-event on/off: `complete`/`error`/`question`/`info`. `false` mutes (exit 0, no send). |
| `reply.enabled` | bool | allow two-way waiting |
| `reply.timeout_seconds` | int | default reply-wait timeout (default 3600) |

## Credentials — env vars only

The config names env vars; the script reads the secrets from the environment:

```bash
export TELEGRAM_BOT_TOKEN="123456:AA...token"
# only if using email backend 'smtp':
export SMTP_USER="claude-jobs@example.com"
export SMTP_PASS="app-password-here"        # Gmail/M365: an App Password
```

## Per-project example (`./.notify.json`)

Inherit global Telegram, but for this repo also email on errors and stay quiet on
completions:

```json
{
  "default_channel": "both",
  "email": { "backend": "smtp", "to": "oncall@example.com", "from": "ci@example.com",
             "smtp": { "provider": "m365" } },
  "events": { "complete": false, "error": true, "question": true, "info": false }
}
```
