# Concurrency, the dispatcher, and topic-per-job

## Why a dispatcher
A Telegram bot has **one** `getUpdates` stream — it can't be scoped to a chat or a
job. If every concurrent job polled the same bot, they'd steal each other's replies
(and Telegram returns 409s). So one long-lived process, **`notifyd`**, owns the
single poller. Jobs never call Telegram; they drop a request in a spool directory
and wait for an answer file. The daemon sends each message and routes every button
tap / reply back to the right job.

This is on automatically when `telegram.mode == "topics"` or `dispatcher.enabled`.

## Two layouts (config: `telegram.mode`)

| mode | What you see | When to use |
|---|---|---|
| `dm` | all jobs in one shared chat; each question is its own message | simplest; works today; no group needed |
| `topics` | one supergroup, **one forum topic per job** — separate threads | concurrent jobs you want visually separated |

Both use the same dispatcher and the same reply routing. `topics` just adds a
thread per `--job`.

## Reply routing (always unambiguous where it matters)
- **Inline buttons** — `callback_data` carries the request id, so a tap maps to the
  exact question regardless of how many are open.
- **Reply-to** — replying to a specific question message maps by `message_id`.
- **Bare text in a topic** — answers the newest open question in that topic. (In
  `dm` mode a bare reply answers the newest open question overall; use buttons or
  reply-to when several are open at once.)

## Running the daemon
```bash
export TELEGRAM_BOT_TOKEN="123:abc"
python scripts/notifyd.py            # foreground
python scripts/notifyd.py status     # {"running": true, "heartbeat_age_s": 1}
python scripts/notifyd.py stop
```
Keep it alive with your process manager of choice:
```bash
nohup python scripts/notifyd.py >~/.local/state/notify/notifyd.log 2>&1 &
# or pm2 start scripts/notifyd.py --interpreter python3 --name notifyd
# or a systemd --user unit
```
On **Windows**, run it in a terminal, hidden via `pythonw`, as a logon task, or as
an NSSM service — see `references/windows.md`.
The client refuses to wait for a reply if the daemon's heartbeat is stale (>10s),
so a dead daemon fails fast with a clear message instead of hanging.

## Forum-group setup (topics mode)
1. Create a **group**, then in group settings enable **Topics** (makes it a forum
   supergroup).
2. Add your bot and make it an **admin** with **Manage Topics**.
3. **Turn off Group Privacy** for the bot (BotFather → /mybots → bot → Bot Settings
   → Group Privacy → Turn off), then **remove and re-add** the bot to the group.
   Without this, the bot can't see bare free-text replies in a topic — only button
   taps and reply-to would work. Details: `references/get-bot-token.md`.
4. Send any message in the group, run `scripts/telegram_get_chat_id.py`, and use the
   group's negative id (e.g. `-1001234567890`) as `telegram.chat_id`.
Topics are created on first use per `--job` and cached in the spool
(`state/topics.json`). With `dispatcher.close_topic_on_complete` (default true), a
`complete`/`error` event closes the job's topic.

## Concurrency notes
- One `notifyd` per bot token. Don't run two.
- Many jobs → many `--job` values → many topics, all served by the one daemon.
- Reuse a `--job` name to keep posting into the same topic/thread.
- Spool writes are atomic (temp + rename); the daemon reloads unanswered questions
  on restart, so a daemon bounce doesn't drop an in-flight question.
