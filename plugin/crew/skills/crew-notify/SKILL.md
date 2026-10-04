---
name: crew-notify
description: Set up outbound notifications to Microsoft Teams or Telegram - deploy results and "Claude stopped and is waiting" questions - and explain the two-way MCP options. Use when the user says set up notifications, notify me, send to Teams, set up a Telegram bot, post updates to a channel, wire up a webhook, or asks how to get alerted when a promotion fails or Claude is waiting on them.
---

# Notifications

Outbound only, by design. crew sends messages; it never reads a channel and
never accepts instructions from one. The reason is at the bottom of this file
and it is worth reading before you decide to go two-way.

---

## Microsoft Teams

### The old way no longer works

If you find a tutorial saying "channel ••• → Connectors → Incoming Webhook,"
close it. <cite>Office 365 Connectors were permanently disabled across
18–22 May 2026</cite>, and that path is gone. The supported route is a
**Workflows (Power Automate)** webhook.

### Setup

1. In Teams, click the **•••** next to the target channel → **Workflows**.
2. Choose the template **Post to a channel when a webhook request is received**.
   (Private channels are supported; if the picker does not offer yours, create
   the flow from the Power Automate portal instead.)
3. Confirm the Team and Channel, finish the flow, and copy the URL it gives you.
4. Export it in your shell profile — never in the repo, never in config:

```bash
export CREW_TEAMS_WEBHOOK='https://prod-xx.westus.logic.azure.com/workflows/...'
```

5. Test before trusting it:

```bash
curl -sS -X POST "$CREW_TEAMS_WEBHOOK" -H 'Content-Type: application/json' \
  -d '{"type":"message","attachments":[{"contentType":"application/vnd.microsoft.card.adaptive","content":{"type":"AdaptiveCard","version":"1.4","body":[{"type":"TextBlock","text":"crew wired up","wrap":true}]}}]}'
```

### Limits worth knowing

- Messages post as the **Flow bot**. Custom bot name and icon are not available
  via Workflows webhooks — do not spend time trying.
- Interactive buttons do not render on MessageCard payloads. Use Adaptive Cards
  if you want richer layout, but see the warning about approvals below.
- The flow runs under whoever created it. If that person leaves, the
  notifications stop. Create it from a service or shared account if this matters.

---

## Telegram

Yes — Telegram integrations are bots. You create one through another bot.

### Setup

1. Message **@BotFather** in Telegram → `/newbot` → follow prompts.
2. Copy the token it gives you (looks like `123456789:AA...`).
3. Send your new bot any message, or add it to a group and post there.
   A bot cannot message you first; the conversation must be opened from your side.
4. Find the chat id:

```bash
curl -sS "https://api.telegram.org/bot${CREW_TELEGRAM_TOKEN}/getUpdates" \
  | python3 -c 'import json,sys;print([u["message"]["chat"]["id"] for u in json.load(sys.stdin)["result"]])'
```

Group ids are negative. That is normal, not an error.

5. Export both:

```bash
export CREW_TELEGRAM_TOKEN='123456789:AA...'
```

6. Test:

```bash
curl -sS -X POST "https://api.telegram.org/bot${CREW_TELEGRAM_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=<id>" --data-urlencode "text=crew wired up"
```

### Note

If you add the bot to a group, privacy mode means it only sees messages
addressed to it — which is fine here, since crew never reads anyway.

---

## Configuration

Set it once, machine-wide, in `~/.claude/crew/config.json` - `notify` is a
global key ("the person's own chat, not the project's"). A repo's
`.crew/config.json` overrides any key it sets; a repo that leaves `provider`
null inherits the global one, and a repo that says `"provider": "none"` opts
out on purpose (`crew_notify.py config` prints that it overrides the global
provider). `tokenEnv` is read from the global file only: a repo's
`tokenEnv` is ignored, with a notice, so a cloned repo cannot pick which
secret goes into the request URL. `config` prints `chatId` masked.

```json
"notify": {
  "provider": "telegram",
  "tokenEnv": "CREW_TELEGRAM_TOKEN",
  "chatId": "-1009876543210",
  "events": ["blocker", "deploy", "question"],
  "realertHours": 6
}
```

Teams: `"provider": "teams", "urlEnv": "CREW_TEAMS_WEBHOOK"`. The Teams branch
is tested against a local server only; no live Teams send has been claimed.

If the notify skill is set up on the same machine, its
`~/.config/notify/config.json` `telegram.bot_token_env` and `chat_id` fill a
null `tokenEnv` / `chatId` - read-only, never the provider. Its example chat id
`-1001234567890` counts as unset.

| Event | Fires when | Subject | Loud? |
|---|---|---|---|
| `deploy` | Every `/crew:promote` result | `Promotion passed` / `Deploy FAILED` / `Promotion outcome unknown` | all but a pass |
| `question` | Claude Code stopped and is waiting on you (the `Notification` hook) | `Question` / `Needs permission` | yes |
| `blocker` | Reserved until T-0060: accepted here, sends nothing | - | - |

**Question types.** `permission_prompt`, `worker_permission_prompt`,
`elicitation_dialog`, `elicitation_url_dialog` and `agent_needs_input`, or the
list in `notify.questionTypes`. `idle_prompt` ("finished, idle") never pings,
and neither does any other type; an unknown or missing type is logged, one line
each, to `<git-common-dir>/crew/notify/unrecognised.log` (capped at 200 lines).
The subject is `Question` for an elicitation, `agent_needs_input`, or a
permission prompt for AskUserQuestion; `Needs permission` for any other tool.
Measured on Claude Code 2.1.285: both arrive as `permission_prompt` with the
fixed message "Claude needs your permission", so the tool is read from the
session transcript's pending `tool_use`.

**What it is waiting on.** A question carries the payload's message plus the
first line of the pending question (AskUserQuestion's text), the pending
tool's name and description, or else Claude's last text - capped at 200
characters and passed through a redaction filter first.

**Once per waiting episode.** A question pings once per `session_id` +
`prompt_id`: no repeat until you have typed your next message in that session
and Claude asked again. Approving a permission prompt does not reset it (the
`prompt_id` is unchanged), so a second prompt in the same turn is silent. On top of that, the same event + ticket + reason is sent once per
`realertHours` (default 6). Both records advance only after a confirmed send,
so a failed send is retried next time rather than lost.

**Retired.** The per-phase, per-review and per-ticket pings are gone. An old
config's `events` still works: `gate` reads as `deploy`, `waiting` as
`question`, and `phase`, `review` and `done` as the reserved `blocker` - each
with a one-line notice, never a silent drop. `/crew:review` still carries its
`notify.sh review` line until a harness-only change removes it; it maps to
`blocker` and sends nothing.

Secrets live in environment variables. The webhook URL **is** the credential for
Teams — anyone holding it can post to that channel as the Flow bot. Treat it
like a password and keep it out of git.

## Payload discipline

One line, led by a subject that says what happened:

```
Needs permission [my-repo/T-0042-build] T-0042 (implement) Claude needs your permission - Bash: Run the migration
Deploy FAILED [my-repo/main] T-0042 (review) prod a1b2c3d - FAILED at gate 3
```

A detached HEAD shows the ticket, never `HEAD`. No diffs, no review findings,
no ticket bodies, no file contents, no error text that might contain a
connection string. A chat channel is a less controlled place than your
repository: it syncs to phones, it is searchable by people outside the project,
and in Teams it may be retained under policies you do not control.

`crew_notify.py` cuts the reason at 280 characters and the transcript excerpt at
200, and runs every line - and everything it writes to its state directory -
through `redact`: the values of environment variables named like a token,
secret, password or key, Telegram bot tokens, `Bearer` values, and `sk-`,
`ghp_`, `github_pat_`, `xox?-` and `AKIA` strings. It is a deny-list; the caps
bound what a miss can leak. Send the fact, not the detail — the detail is in
the repo where it belongs.

The sender is one module, `hooks/scripts/crew_notify.py` (`send`, `hook`,
`config`); `notify.sh` and `notify.ps1` are thin wrappers that keep the
one-sender election between the two shells. It honours a 429's `retry_after`,
paces sends a second apart, and always exits 0.

---

## Two-way: available, and mostly a bad idea

Both platforms have MCP servers if you want a channel to drive the crew:

- **Teams**: Microsoft's official Work IQ server (preview, part of Agent 365) is
  read/write with no read-only flag — you constrain it with Entra scopes.
  `floriscornel/teams-mcp` runs via npx and does offer a read-only mode.
  `InditexTech/mcp-teams-server` reads, posts, replies and mentions.
  Microsoft also documents turning a Teams bot into an MCP server for
  agent-to-human questions and approvals.
- **Telegram**: several exist, including ones built specifically to ask a user a
  question and wait for the reply.

Before wiring any of them in, weigh two things honestly.

**A chat message becomes an instruction to an agent with shell and filesystem
access.** Anyone who can post in that channel is writing into the agent's
context — and so is anything quoted into it from a ticket, an alert, or a
forwarded customer email. That is a prompt-injection surface with your
repositories inside the blast radius.

**Approving a plan on a phone is worse review, not more of it.** If work is
already queuing on the human's attention, a path that makes it easier to say yes
without reading properly does not widen the bottleneck. It makes it cheaper to
ignore.

If you go ahead anyway, the safer shape is: a private channel, an allowlist of
sender ids checked by a script, and a fixed vocabulary (`approve T-0042`,
`status`) parsed **by that script** — never letting free chat text reach the
model as instruction.

Also check whether Claude Code's own mobile access covers what you want first.
It is first-party, the auth is handled, and it does not add a new inbound path.
