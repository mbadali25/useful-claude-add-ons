---
name: notify
description: Notify a Claude session's progress to your phone or inbox via a Telegram bot (primary) or email (secondary). Use whenever the user wants to be pinged/texted/emailed/messaged about a job or task — 'tell me when this finishes', 'message me if it errors', 'ping me on Telegram when the build is done', 'let me know if it needs input', 'email me the results' — or wants to wire complete/error/question/info alerts into a script or long-running task. Telegram is two-way, so a question event can block and wait for the user's reply from their phone, and concurrent jobs can each get their own topic. Config-driven (global or per-project). Trigger any time the goal is an out-of-band heads-up about session or job status, even if the user does not say Telegram or email.
---

# Notify (Telegram + email)

Sends a short notification about what's happening in a session. **Subject** = the
event / what's happening; **body** = the details.

- **Telegram** (primary): Bot API over HTTPS, stdlib only, works in detached jobs,
  and is **two-way** — a `question` waits for your reply.
- **Email** (secondary): SMTP from a job, or the **M365 / Gmail connector** when a
  Claude session is driving.

## Setup (once)

1. Copy `assets/config.example.json` to **global** `~/.config/notify/config.json`
   or **per-project** `./.notify.json` (project overrides global, key by key).
2. **Telegram**: create a bot with `@BotFather` (`/newbot`) → get a token. Message
   your bot once, then run `scripts/telegram_get_chat_id.py` to get your `chat_id`.
   Token walkthrough: `references/get-bot-token.md`. Chat/two-way notes:
   `references/telegram-setup.md`.
3. Export the token (config only names the env var; never store the token in the
   file):
   - macOS/Linux: `export TELEGRAM_BOT_TOKEN=...`
   - Windows: `setx TELEGRAM_BOT_TOKEN "..."` — full commands in `references/windows.md`.
4. **Email** (optional): pick a backend — `smtp` (with `provider: gmail|m365`) or
   `connector`. See `references/email-backends.md`.

Config schema + resolution order: `references/config.md`. A `/notify-setup` slash
command lives in `commands/notify-setup.md`.

## Sending

```bash
python scripts/notify.py -e complete -m "nightly ETL finished in 12m"
python scripts/notify.py -e error    -m "migration failed on step 4 (exit 1)"
python scripts/notify.py -e info -s "Deploy started" -m "rolling out v2.3 to prod"
python scripts/notify.py -m "test" --dry-run          # print, send nothing
```

| Flag | Meaning |
|---|---|
| `-m/--message` | body details (required) |
| `-e/--event` | `complete`/`error`/`question`/`info`; sets the default subject and is gated by `config.events` |
| `-s/--subject` | subject line (what's happening); defaults to the event label |
| `--session` | job/session label, prefixed to the subject → `[label] subject` |
| `-c/--channel` | `telegram`/`email`/`both` (default: `config.default_channel`) |
| `--wait` | Telegram: block for a reply (implied by `--event question`) |
| `--timeout` | reply-wait seconds (default `config.reply.timeout_seconds`) |
| `--dry-run` | show resolved target + subject/body, send nothing |

Mute a whole class of alert without touching scripts: set it `false` in
`config.events` (e.g. `"complete": false` to only hear about errors). The script
exits 0 and sends nothing.

**Long bodies split automatically.** Telegram caps a message at 4096 characters
and rejects anything longer outright, so a body over the limit goes as several
messages numbered `(1/3)`, `(2/3)`, … Breaks land on a blank line where possible,
then a newline, then a hard cut. Buttons are attached to the last part only, and
that part is the one a reply correlates against — so `--wait` and `-e question`
behave the same whether the body split or not. `--dry-run` reports the part count.
Pass a whole log or diff as `-m` without pre-truncating it.

## Two-way: asking a question and waiting

`question` (or any `--wait`) sends the message, then **blocks** polling Telegram for
your reply and prints it as JSON:

```bash
reply=$(python scripts/notify.py -e question \
  -s "Prod deploy needs approval" -m "Proceed with v2.3? (yes/no)" --timeout 900)
# -> {"reply": "yes"}   (exit 0)   |   {"reply": null, "timed_out": true} (exit 5)
```

When **you (Claude)** are driving a session and hit a decision point, use this to
ask the user on their phone and act on the answer. Parse the `reply` field; on exit
5 (timeout) fall back to a safe default and say so.

## Email via a connector (when a session is driving)

If `email.backend` is `connector`, the script does **not** send — instead you
(Claude) send the email using an available MCP email tool, because those are your
tools, not a CLI:

1. Read `email.to` from config; **Subject** = the event/what's happening;
   **body** = the details.
2. Prefer **Microsoft 365** (`send`/mail tool) or **Gmail** if connected. If
   neither is connected, tell the user, and offer to switch `backend` to `smtp`.

Use `connector` for session-time emails from your account; use `smtp` for emails
fired by a detached/background job that can't call MCP.

## Concurrent jobs (dispatcher + topic-per-job)

For many jobs at once — or to give each job its own chat lane — turn on the
dispatcher. A single `notifyd` process owns the one Telegram poller so jobs never
fight over replies. Set `telegram.mode`:

- `dm` — all jobs in one shared chat.
- `topics` — one forum **topic per `--job`** in a supergroup (visually separate).

```bash
export TELEGRAM_BOT_TOKEN=...
python scripts/notifyd.py &                 # start the dispatcher (keep alive)
python scripts/notify.py -e question --job deploy-web -s "Approve prod?" -m "v2.3?"
python scripts/notify.py -e question --job db-migrate -s "Run migration?" -m "step 4?"
```

Each `--job` gets its own topic; the daemon routes button taps, reply-to, and
in-topic text back to the right waiting job. The client refuses to wait if the
daemon isn't running (heartbeat check), so it fails fast instead of hanging. Full
architecture, forum-group setup, and process-manager tips: `references/concurrency.md`.

## Wiring into a job

```bash
if my_long_job; then
  python scripts/notify.py -e complete -m "job ok"
else
  python scripts/notify.py -e error -m "job failed (exit $?)"
fi
```

## Files

- `scripts/notify.py` — client: sends, or (dispatcher mode) queues + waits. Stdlib only.
- `scripts/notifyd.py` — the dispatcher daemon (single poller, topic-per-job, reply routing).
- `scripts/tg.py` — shared Telegram Bot API helpers.
- `scripts/telegram_get_chat_id.py` — one-time helper to find your `chat_id`.
- `references/get-bot-token.md` — step-by-step BotFather token guide (+ group privacy mode).
- `references/windows.md` — Windows commands: env vars, sending, running the daemon.
- `references/concurrency.md` — dispatcher architecture, dm vs topics, forum-group setup.
- `references/config.md` — config schema + resolution order.
- `references/telegram-setup.md` — chat_id + two-way notes.
- `references/email-backends.md` — SMTP presets (Gmail/M365) + connector path.
- `assets/config.example.json` — starter config.
- `commands/notify-setup.md` — `/notify-setup` slash command.

## Responsible use

Send only what the user asked, where they intend. Keep the bot token secret (it
controls the bot). Don't spam; don't route messages to chats the user didn't set up.
