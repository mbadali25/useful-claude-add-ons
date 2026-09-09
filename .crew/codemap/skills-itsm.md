# skills-itsm
anchor: useful-claude-add-ons@1f97e51c
verified: 2026-09-06

## Does
`infra-work-ticketing` gets infrastructure work logged to ServiceDesk Plus or Jira through an MCP
connector, falling back to a local Python CLI; `notify` sends Telegram or email pings about a
session and can block waiting for a reply. Together they are the "tell a human" path - one files
the paper trail, the other pages the person.

## Entry points
- DERIVED `skills/infra-work-ticketing/SKILL.md:17` - the model reaches for the `sdp_*` MCP tools
  first when infra work is detected in conversation.
- DERIVED `skills/infra-work-ticketing/scripts/ticketctl.py:1927` - argparse CLI, `main` at `:2093`.
  The fallback transport when MCP is not available.
- DERIVED `skills/notify/scripts/notify.py` - invoked as `python scripts/notify.py -e <event> -m
  <msg>`, per `skills/notify/SKILL.md:38-41`.
- DERIVED `skills/notify/scripts/notifyd.py` - the dispatcher daemon, started by hand
  (`skills/notify/SKILL.md:161`); it owns the single Telegram poller so concurrent jobs do not
  fight over replies.

## Owns data
- DERIVED A local write queue for failed SDP/Jira writes, drained by the `retry` command
  (`skills/infra-work-ticketing/scripts/ticketctl.py:2054`).
- DERIVED The Telegram inbox and poll offset at `<spool>/inbox.jsonl` and
  `<spool>/state/offset.json` (`skills/notify/SKILL.md:113`, implemented in
  `skills/notify/scripts/inbox.py`).

## Calls out to
- DERIVED Zoho ServiceDesk Plus Cloud over MCP at `skills/infra-work-ticketing/SKILL.md:410`; the
  tool set (`sdp_get`, `sdp_search`, `sdp_list_notes`, `sdp_create`, `sdp_add_note`, `sdp_update`,
  `sdp_transition`, `sdp_close`, `sdp_list_metadata`, `sdp_add_worklog`) is tabulated at
  `skills/infra-work-ticketing/SKILL.md:86-101`, with `sdp_link_account` named separately at
  `:135`. Jira Cloud and email are reachable only through the fallback (`:100-101`).
- DERIVED The Telegram Bot API at `skills/notify/scripts/tg.py:38`.

## Landmines
- **Ticket creation is ungated by default, and gated for exactly one class of caller.** Both halves
  are load-bearing; the previous revision of this note recorded only the first and stated it as a
  blanket, which is now wrong in the direction that matters.
  - DERIVED The default path is still ungated. `skills/infra-work-ticketing/SKILL.md:209-211` reads
    verbatim: "If you're confident about what the work is, create the ticket and report what you
    made in the same turn - no confirmation round-trip. Tickets are editable and a follow-up note
    can correct anything." That text is byte-identical to what it said at the previous anchor.
  - DERIVED `:213-231` adds a carve-out that did not exist at the previous anchor: a **batch of
    tickets from an automated security scan** requires "one explicit go-ahead before creating
    anything" *unless* this conversation visibly shows the upstream gate having fired - the
    scanner's own exit-3-and-marker preview (`GIZMODUCK_CONFIRMATION_REQUIRED`), the user approving
    that exact batch, and a rerun carrying the tool's own approval value (`--yes <digest>`). Note
    the polarity: the carve-out's *default* is to confirm, and observing the upstream sequence is
    what exempts you. "It came from a scanner" is explicitly not sufficient (`:216-218`).
  - DERIVED `:229-231` states the carve-out "does not add a confirmation requirement to this
    skill's other callers or to hand-typed, conversational ticket requests, which keep the fast path
    exactly as described above."
  - JUDGEMENT So a caller relying on this skill to pause before `sdp_create` still gets no pause on
    a conversational request. It gets one only on a scanner batch, and even then only when the
    upstream approval is *not* visible in the conversation.
  - DERIVED `:233` then begins "Ask first only when a fact you genuinely need is missing and
    unguessable", followed by four bullets (`:236-243`) - which system, which environment, planned
    versus incident, who requested. Every one is a missing-fact question; **none is a confirmation
    of the write**. (These moved from `:213` and `:216-223` purely because the carve-out was
    inserted above them; the text is unchanged.)
- **MCP writes bypass the secret scrubber.** DERIVED `skills/infra-work-ticketing/SKILL.md:139-141`:
  `ticketctl.py` scrubs, the MCP path does not, so a note pasted with command output can carry a
  token unless `redact-check --emit` is run first.
- **A failed MCP write is lost; a failed `ticketctl.py` write is not.** DERIVED
  `skills/infra-work-ticketing/SKILL.md:387-390` - "The MCP server has no such queue. A failed
  `sdp_add_note` is simply gone", and the instruction is to re-send through `ticketctl.py note`
  rather than retrying the MCP call. The local queue at `ticketctl.py:2054` covers only the
  fallback transport, which is the path the skill tells you *not* to use by default.
- **The Telegram token is env-only, and the code enforces it** - DERIVED
  `skills/notify/scripts/notify.py:88` and `:193` read
  `os.environ.get(tgc.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))` and nothing reads a literal token
  out of config JSON. Confirmed in code, not inferred from the documentation.
- A `question` event **blocks**. DERIVED Timeout defaults to `cfg["reply"]["timeout_seconds"]` or
  3600s (`skills/notify/scripts/notify.py:314`, `:325`); on timeout it exits **5** with
  `{"reply": null, "timed_out": true}` (`:182`, `:187`, `:255`). A caller that does not handle exit 5
  hangs or misreads a timeout as an answer.
- DERIVED Config resolution is global `~/.config/notify/config.json` merged with per-project
  `./.notify.json` via `deep_merge` at `skills/notify/scripts/notify.py:63`, project keys winning -
  JUDGEMENT the same two-layer shape that has already caused two agents here to disagree about a
  value without naming which file they read.

## Unverified
- `ticketctl.py`'s scrubber implementation and its `zoho-token` / `jira-token` OAuth subcommands
  were not read; scrubbing behaviour is taken from SKILL.md beyond confirming a `redact-check`
  subparser exists.
- `skills/notify/scripts/notifyd.py` and `inbox.py` were not read in depth - dispatcher and
  topic-routing behaviour comes from SKILL.md prose, not from tracing the code.
- No `references/*.md` under either skill was opened.
- Whether an agent actually *honours* the `:213-231` carve-out is not verified and cannot be from
  this repo: it is prose instruction to a model, not an enforced gate. The enforced half lives
  upstream in `plugin/gizmoduck/` (documented in the gizmoduck codemap note, not here). What is
  verified here is only that the instruction exists and what it says.

## Re-anchor provenance
Re-anchored a02331ee -> 1f97e51c on 2026-09-06. Every `path:line` above was re-resolved by reading
the current file, not carried over.

**What changed.** One cited path moved: `skills/infra-work-ticketing/SKILL.md`, in commit
`b7b7101d` ("crew 0.16.17, gizmoduck 0.2.3, localgpu 0.1.14: endpoint scan trigger, a real ticket
gate, and a review gate that no longer fails open", #74). `git diff --stat` reports `1 file changed,
20 insertions(+)` and no deletions - a pure insertion of the scanner-batch carve-out at `:213-231`.
Note it was **not** `9338e89d` ("Gate gizmoduck ticket creation..."), which was the commit this
re-anchor set out to check; `9338e89d` gated the gizmoduck side and left this skill untouched.

**The gating claim did not invert; it narrowed.** The old note's verbatim quote at `:209-211` is
still verbatim and still at `:209-211`. What became wrong was its blanket conclusion - "Anything
relying on this skill to pause before `sdp_create` is relying on something that is not there" - now
false for one class of caller. Rewritten above as two claims with their scopes attached, rather than
one claim reworded.

**Line numbers corrected.** `:390` -> `:410` (the MCP endpoint; the old number now lands in the
"no such queue" paragraph). `:213` -> `:233` and `:216-223` -> `:236-243` (the ask-first bullets,
displaced by the insertion, text unchanged).

**Content drift corrected.** The tabulated tool list omitted `sdp_list_notes`
(`SKILL.md:90`); added. `sdp_link_account` (`:135`) is named in the skill but is not a row in the
`:86-101` table, so it is now cited separately rather than folded into the table's list.

**Re-verified unchanged, by reading each line.** `SKILL.md:17`, `:86`, `:90`, `:101`, `:135`,
`:139-141`; `ticketctl.py:1927`, `:2054`, `:2093`; `notify.py:63`, `:88`, `:182`, `:187`, `:193`,
`:255`, `:314`, `:325`; `tg.py:38`; `notify/SKILL.md:38-41`, `:113`, `:161`. All resolved to the
text the note claims.

**Also checked, outside this note's subsystem.** That the gizmoduck gate the carve-out names is real
rather than aspirational: `plugin/gizmoduck/scripts/gizmoduck.py` implements `--yes DIGEST` with
`_records_digest` at `:122-141`, binding the approval to the exact previewed batch, and refuses a
stale or mismatched digest rather than treating it as a bare yes (`:475-479`). Recorded here only
because the carve-out's meaning depends on it; the gizmoduck subsystem is documented elsewhere.
