---
name: crew-notify
description: Set up outbound notifications to Microsoft Teams or Telegram, and explain the two-way MCP options. Use when the user says set up notifications, notify me, send to Teams, set up a Telegram bot, post updates to a channel, wire up a webhook, or asks how to get alerted when a phase finishes or a gate fails.
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

```json
"notify": {
  "provider": "teams",
  "urlEnv": "CREW_TEAMS_WEBHOOK",
  "events": ["phase", "gate", "waiting"]
}
```

Telegram:

```json
"notify": {
  "provider": "telegram",
  "tokenEnv": "CREW_TELEGRAM_TOKEN",
  "chatId": "-1001234567890",
  "events": ["phase", "gate", "review", "waiting"]
}
```

| Event | Fires when |
|---|---|
| `phase` | A `/crew:init` phase completes or blocks |
| `gate` | The verification gate fails |
| `review` | A review finishes, with the BLOCK/FIX counts |
| `waiting` | Claude is waiting on you (the `Notification` hook) |
| `done` | A ticket completes the full loop |

Opt into few. A channel that pings on everything gets muted within a week, and a
muted channel is worse than no channel because you believe you are covered.

Secrets live in environment variables. The webhook URL **is** the credential for
Teams — anyone holding it can post to that channel as the Flow bot. Treat it
like a password and keep it out of git.

## Payload discipline

One line. No diffs, no review findings, no ticket bodies, no file contents, no
error text that might contain a connection string. A chat channel is a less
controlled place than your repository: it syncs to phones, it is searchable by
people outside the project, and in Teams it may be retained under policies you
do not control.

`notify.sh` truncates at 280 characters for exactly this reason. Send the fact,
not the detail — the detail is in the repo where it belongs.

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
