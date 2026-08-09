---
description: Set up or edit notifications (Telegram bot + optional email)
---

Configure the `notify` skill for this user. Keep it to a few tight prompts; reuse
anything already obvious from the conversation or an existing config.

1. Ask **global** (`~/.config/notify/config.json`) or **per-project**
   (`./.notify.json`). Default global.
2. **Telegram (primary):**
   - Walk them through `@BotFather` → `/newbot` → token, per
     `references/telegram-setup.md`.
   - Have them message the bot once, then run `scripts/telegram_get_chat_id.py`
     (with `TELEGRAM_BOT_TOKEN` exported) to capture `chat_id`.
   - Store the token as an env var; put only its name in the config.
3. **Email (secondary, optional):** ask backend —
   - `connector` if they want session-time emails from their M365/Gmail account
     (check which connector is actually available and say so), or
   - `smtp` with `provider: gmail|m365|outlook` for background jobs (note the
     app-password / M365-SMTP caveats in `references/email-backends.md`).
   - Collect `email.to` and `email.from`.
4. Ask which **events** to enable (complete/error/question/info) and the reply
   timeout for questions.
5. Write the config from `assets/config.example.json`, then run a `--dry-run` to
   show the resolved target + subject/body, and offer one real test message.
