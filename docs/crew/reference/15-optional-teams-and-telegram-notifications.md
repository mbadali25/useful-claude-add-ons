<!-- Moved verbatim from plugin/crew/README.md (15. Optional: Teams and Telegram notifications) by L-0726; the README keeps an index entry. -->

## 15. Optional: Teams and Telegram notifications

**Outbound only.** crew sends messages; it never reads a channel and never takes
instructions from one.

Set it once in the machine-global `~/.claude/crew/config.json`; a repo's
`.crew/config.json` overrides any key it sets, a repo `null` inherits, and a repo
`"provider": "none"` opts out on purpose.

```json
"notify": {
  "provider": "telegram",
  "tokenEnv": "CREW_TELEGRAM_TOKEN",
  "chatId": "-1009876543210",
  "events": ["blocker", "deploy", "question"],
  "realertHours": 6
}
```

Three events send, each led by a subject that says what happened (T-0051, T-0060):

- `deploy` — every `/crew:promote` result: `Promotion passed` (silent) or
  `Deploy FAILED` (loud); a result naming neither is `Promotion outcome
  unknown` (loud), never a pass.
- `question` — Claude Code stopped and is waiting on you: `Question` (an
  AskUserQuestion or an elicitation) or `Needs permission` (any other tool),
  from the `Notification` hook's `notification_type` (the built-in five
  types are fixed; `notify.questionTypes` was removed). An idle "finished" prompt never pings. The line
  says what it is waiting on — the pending question, or the tool — read from
  the session transcript, capped and redacted. One ping per waiting episode:
  no repeat until your next typed message in that session. Approving a
  permission prompt does not reset it, so a second prompt in the same turn is
  silent.

- `blocker` — work stopped and only you can move it (T-0060), loud:
  `Approval waiting` (autopilot stopped at `approve`), `Review out of rounds`
  (autopilot stopped at `accept-review`/`replan` with the budget spent and a
  BLOCK open), `Lane stalled` / `Lane state unknown` (autopilot's in-flight
  check read another runner's marker as `stale`, or could not tell; needs
  T-0049's markers and takes its staleness from their TTL; `live` and
  `elsewhere` send nothing), and `Stop gate refused` (the same ticket refused
  at Stop twice in a row, recorded by `crew_notify.py stop`; the gates' calls
  land in a harness-only change). Autopilot's report runs `crew_notify.py
  run-stop` at every stop, and that code decides which stop pings.

The per-phase, per-review and per-ticket pings are retired; an old config's
`gate` reads as `deploy`, `waiting` as `question`, and `phase`/`review`/`done` as
`blocker`, each with a notice; a send under those three old names sends nothing. The same message is sent once per `realertHours`, and both that
record and the episode record advance only on a confirmed send.
`python3 hooks/scripts/crew_notify.py config --root .` prints what this repo
runs with, and why.

### Teams

The old `channel ••• → Connectors → Incoming Webhook` route is gone; Office 365
Connectors were permanently disabled across 18–22 May 2026. Any tutorial
describing that path is dead.

Current route: **••• next to the channel → Workflows → "Post to a channel when a
webhook request is received"**, confirm Team and channel, copy the URL. Export it
to `CREW_TEAMS_WEBHOOK` in your shell profile — that URL *is* the credential for
the channel, so keep it out of git.

Two things that will otherwise puzzle you: messages post as the **Flow bot**
(custom name and icon are not supported via Workflows webhooks), and the flow
runs under whoever created it — if that person leaves, notifications stop.

### Telegram

Yes, it's a bot — created through another bot. Message **@BotFather**, run
`/newbot`, take the token. Then **message your bot first**: a bot cannot open a
conversation with you. Read the chat id from `getUpdates`; group ids are negative,
which is normal rather than a bug.

Export `CREW_TELEGRAM_TOKEN` and put the chat id in `notify.chatId`. `tokenEnv`
and `urlEnv` count only in the global file (a repo's is ignored), so a cloned repo
cannot pick the request URL; a redirect is a failed send, never followed. If the
notify skill is already set up on this machine, its `telegram.bot_token_env` and
`chat_id` fill a null `tokenEnv` / `chatId` (read-only; its example chat id
`-1001234567890` counts as unset).

### Payload discipline

One line, the reason cut at 280 characters and the transcript excerpt at 200,
every line redacted first. No diffs, no findings text, no ticket
bodies, no error output that might carry a connection string. A chat channel
syncs to phones, is searchable by people outside the project, and in Teams may be
retained under policies you don't control. Send the fact; the detail stays in the
repo.

### Two-way is available and mostly a bad idea

MCP servers exist for both — Microsoft's official Work IQ Teams server (preview,
read/write with no read-only flag), `floriscornel/teams-mcp` (npx, has a
read-only mode), `InditexTech/mcp-teams-server`, and several Telegram ones
including some built to ask a question and wait for the reply.

Two reasons to stay outbound. A chat message becomes an instruction to an agent
holding shell and filesystem access — anyone who can post there, and anything
quoted in from a ticket or forwarded email, is writing into its context. And
approving a plan on a phone is worse review, not more of it: if work already
queues on your attention, making it easier to say yes without reading properly
doesn't widen that bottleneck.

If you go ahead regardless: private channel, allowlisted sender ids, a fixed
vocabulary (`approve T-0042`, `status`) parsed **by a script** rather than by the
model. And check whether Claude Code's own mobile access already covers it —
first-party, auth handled, no new inbound path.
