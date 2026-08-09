# Getting a Telegram bot token

A **bot token** is the secret key that lets `notify` control your bot — send
messages and receive your replies. You get it from Telegram's official bot,
**@BotFather**. Takes about two minutes.

## Create the bot
1. Open Telegram (phone or desktop) and search **@BotFather**. Pick the account
   with the blue verified checkmark. Open it and tap **Start**.
2. Send **/newbot**.
3. **Name** it (free text, shown at the top of the chat): e.g. `Claude Job Notifier`.
4. **Username** it: must be unique and **end in `bot`**, e.g. `yourname_claude_bot`.
   If it's taken, BotFather asks for another.
5. BotFather replies with your token on its own line:
   ```
   123456789:AAEabc123DEF456ghi789JKL012mno345PQR
   ```
   The number before `:` is the bot id; the whole string is the token. **Copy it.**

## Store it as an environment variable
`notify` reads the token from `TELEGRAM_BOT_TOKEN`. The config file only names the
variable — never paste the token into the file.
- macOS/Linux: `export TELEGRAM_BOT_TOKEN="123456789:AAE..."`
- Windows: see `references/windows.md` (`setx` / `$env:`).

## Let the bot read free-text replies in a group (topics mode only)
By default a bot in a **group** has **privacy mode ON**, so it only receives:
commands, @mentions, and **replies to its own messages**. Effect on `notify`:

| Answer method | Works with privacy ON? |
|---|---|
| Inline **button** tap | ✅ always |
| **Reply** to the question message | ✅ always |
| **Bare free-text** in the job's topic | ❌ needs privacy OFF |

To use bare free-text answers in topics:
1. BotFather → **/mybots** → your bot → **Bot Settings** → **Group Privacy** →
   **Turn off** (or send **/setprivacy** → pick bot → **Disable**).
2. **Remove and re-add** the bot to the group — the change only takes effect after
   re-adding.

Private 1:1 chats (`dm` mode with your own bot DM) are unaffected — the bot always
sees your messages there.

## Manage or recover the token
| Need | BotFather |
|---|---|
| See the token again | /mybots → bot → **API Token** (or /token) |
| Regenerate (if leaked) | /revoke → pick bot (old token dies immediately) |
| Rename / avatar / about | /setname, /setuserpic, /setdescription |
| Delete the bot | /deletebot |

## Security
The token is full control of the bot. Don't commit it to git or paste it into
shared logs. If it leaks, run **/revoke** right away and update `TELEGRAM_BOT_TOKEN`.
