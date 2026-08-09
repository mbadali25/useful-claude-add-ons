# Email backends

Two ways to send email. Pick per config (`email.backend`).

## `smtp` — the script sends it
Works from detached/background jobs (no MCP needed). Set `email.smtp.provider` to
fill host/port automatically, or set `host`/`port`/`starttls` for a custom server.

| provider | host | port | notes |
|---|---|---|---|
| `gmail` | smtp.gmail.com | 587 | Use a **Google App Password** (needs 2FA on the account), not your login password. |
| `m365` / `office365` | smtp.office365.com | 587 | Requires **Authenticated SMTP** enabled on the mailbox. Microsoft is retiring basic-auth SMTP, so this may need an app password or be disabled by tenant policy — if it fails, use the `connector` backend instead. |
| `outlook` | smtp-mail.outlook.com | 587 | Personal Outlook.com accounts. |

Creds come from env vars named in config (`username_env`/`password_env`, default
`SMTP_USER`/`SMTP_PASS`). Never put secrets in the config file.

## `connector` — Claude sends it via MCP
When a Claude **session** is driving (not a detached job), Claude sends the email
using a connected MCP email tool — the user's own account, no SMTP creds, and it
sidesteps M365 basic-auth SMTP restrictions.

With `backend: connector`, `notify.py` deliberately refuses and points here. The
skill instructs Claude to:
1. Read `email.to` from config.
2. Set **Subject** = the event / what's happening; **body** = the details.
3. Send via **Microsoft 365** or **Gmail** if connected; if neither is, tell the
   user and offer to switch to `smtp`.

## Which to use
- Background/cron/CI job → **smtp** (the script must run unattended).
- Interactive Claude session, especially on M365 where SMTP is locked down →
  **connector**.
- Telegram is the primary channel; email is the durable-record secondary.
