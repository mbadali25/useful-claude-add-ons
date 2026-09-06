# skills-itsm
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
`infra-work-ticketing` gets infrastructure work logged to ServiceDesk Plus or Jira through an MCP
connector, falling back to a local Python CLI; `notify` sends Telegram or email pings about a
session and can block waiting for a reply. Together they are the "tell a human" path - one files
the paper trail, the other pages the person.

## Entry points
- `skills/infra-work-ticketing/SKILL.md:17` - the model reaches for the `sdp_*` MCP tools first
  when infra work is detected in conversation.
- `skills/infra-work-ticketing/scripts/ticketctl.py:1927` - argparse CLI, `main` at `:2093`. The
  fallback transport when MCP is not available.
- `skills/notify/scripts/notify.py` - invoked as `python scripts/notify.py -e <event> -m <msg>`,
  per `skills/notify/SKILL.md:38-41`.
- `skills/notify/scripts/notifyd.py` - the dispatcher daemon, started by hand
  (`skills/notify/SKILL.md:161`); it owns the single Telegram poller so concurrent jobs do not
  fight over replies.

## Owns data
- A local write queue for failed SDP/Jira writes, drained by the `retry` command
  (`skills/infra-work-ticketing/scripts/ticketctl.py:2054`).
- The Telegram inbox and poll offset at `<spool>/inbox.jsonl` and `<spool>/state/offset.json`
  (`skills/notify/SKILL.md:113`, implemented in `skills/notify/scripts/inbox.py`).

## Calls out to
- Zoho ServiceDesk Plus Cloud over MCP at `skills/infra-work-ticketing/SKILL.md:390`; the tool set
  (`sdp_get`, `sdp_search`, `sdp_create`, `sdp_add_note`, `sdp_update`, `sdp_transition`,
  `sdp_close`, `sdp_list_metadata`, `sdp_add_worklog`) is tabulated at
  `skills/infra-work-ticketing/SKILL.md:86-101`. Jira Cloud and email are reachable only through the
  fallback (`:101`).
- The Telegram Bot API at `skills/notify/scripts/tg.py:38`.

## Landmines
- **This skill instructs an unconfirmed write to a live service desk.**
  `skills/infra-work-ticketing/SKILL.md:209-211` reads verbatim: "If you're confident about what the
  work is, create the ticket and report what you made in the same turn - no confirmation
  round-trip. Tickets are editable and a follow-up note can correct anything." `:213` then begins
  "Ask first only when a fact you genuinely need is missing and unguessable", followed by four
  bullets (`:216-223`) - which system, which environment, planned versus incident, who requested.
  Every one is a missing-fact question; **none is a confirmation of the write**. Anything relying on
  this skill to pause before `sdp_create` is relying on something that is not there.
- **MCP writes bypass the secret scrubber.** `skills/infra-work-ticketing/SKILL.md:139-141`:
  `ticketctl.py` scrubs, the MCP path does not, so a note pasted with command output can carry a
  token unless `redact-check --emit` is run first.
- **The Telegram token is env-only, and the code enforces it** - `skills/notify/scripts/notify.py:88`
  and `:193` read `os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))` and nothing reads
  a literal token out of config JSON. Confirmed in code, not inferred from the documentation.
- A `question` event **blocks**. Timeout defaults to `cfg["reply"]["timeout_seconds"]` or 3600s
  (`skills/notify/scripts/notify.py:314`, `:325`); on timeout it exits **5** with
  `{"reply": null, "timed_out": true}` (`:182`, `:187`, `:255`). A caller that does not handle exit 5
  hangs or misreads a timeout as an answer.
- Config resolution is global `~/.config/notify/config.json` merged with per-project `./.notify.json`
  via `deep_merge` at `skills/notify/scripts/notify.py:63`, project keys winning - the same
  two-layer shape that has already caused two agents here to disagree about a value without naming
  which file they read.

## Unverified
- `ticketctl.py`'s scrubber implementation and its `zoho-token` / `jira-token` OAuth subcommands
  were not read; scrubbing behaviour is taken from SKILL.md beyond confirming a `redact-check`
  subparser exists.
- `skills/notify/scripts/notifyd.py` and `inbox.py` were not read in depth - dispatcher and
  topic-routing behaviour comes from SKILL.md prose, not from tracing the code.
- No `references/*.md` under either skill was opened.
