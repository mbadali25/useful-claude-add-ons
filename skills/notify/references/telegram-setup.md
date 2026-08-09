# Telegram setup

## 1. Create the bot & get a token
Full step-by-step (with the privacy-mode setting for group/topics use) is in
`references/get-bot-token.md`. In short: message **@BotFather**, send `/newbot`,
follow the prompts, copy the token it returns. Keep it secret.

Export it (macOS/Linux shown; **Windows** commands are in `references/windows.md`):
```bash
export TELEGRAM_BOT_TOKEN="123456789:AAE..."
```

## 2. Get your chat_id
- Open a chat with your new bot and send it any message (e.g. `hi`). The bot can't
  message you until you've messaged it first.
- Run:
  ```bash
  export TELEGRAM_BOT_TOKEN="123456789:AAE..."
  python scripts/telegram_get_chat_id.py
  ```
- Copy the printed `chat_id` into `telegram.chat_id` in your config.

## 3. Wire it up
```bash
export TELEGRAM_BOT_TOKEN="123456789:AAE..."
python scripts/notify.py -e info -m "hello from notify" --dry-run   # verify target
python scripts/notify.py -e info -m "hello from notify"             # real send
```

## Two-way (waiting for a reply)
`notify.py -e question ...` sends, then long-polls `getUpdates` for the next text
message from your `chat_id` and prints `{"reply": "..."}`. Exit 5 means it timed
out with no reply.

Constraints:
- The bot must be in **polling** mode — no webhook set on it. Fresh BotFather bots
  are fine. (If you ever set a webhook, `getUpdates` returns a 409 conflict.)
- Only one poller at a time per bot. Don't run two waiting `notify.py` calls against
  the same bot simultaneously; they'll fight over updates.
- Replies are matched by `chat_id`, so in a group only messages from that chat count.

## Groups & multiple people
- To notify a group, add the bot to the group and send a message there; the helper
  prints the group's (negative) `chat_id`. Use that as `telegram.chat_id`.
- Anyone in that chat can answer a `question`; the first text reply wins.
