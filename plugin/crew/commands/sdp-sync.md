---
description: Sync a ticket between ServiceDesk Plus (via MCP) and the local cache
argument-hint: <REQUEST-ID> [--push]
allowed-tools: Read, Write, Edit, Bash, ToolSearch
---

Sync $ARGUMENTS.

## Preconditions

1. `.crew/config.json` -> `tracker` must be `"sdp"`.
2. The ServiceDesk Plus MCP server must be connected. Check your available tools
   for `sdp_*` (`sdp_get`, `sdp_search`, `sdp_add_note`, ...). If tool search is
   active they will not be listed until you search for them, so search before
   concluding they are absent.

If either is missing, say exactly which one and stop. Do not fall back to file
tickets — a silent fallback splits the source of truth, and nobody notices until
two people are working from divergent ticket state.

`sdp_whoami` is the cheapest way to prove the connection is live and to see whose
audit trail the writes will land under. The tools act as the signed-in user, so
the desk records the person, not "an automation".

## The id, and the local key

ServiceDesk Plus request ids are bare numbers (`40219`). Crew's local key for one
is `SDP-<id>` — `SDP-40219` — and that is what goes in `.work/INDEX.md`, in the
cache filename, and in branch names and commit messages. Two reasons: a bare
number in an index line is unreadable a week later, and the rest of crew
recognises a ticket by the `LETTERS-digits` shape, so a bare number is invisible
to the session brief and to `/crew:work`.

Accept either form as `$1`. Write `SDP-<id>`.

## Pull (default)

Fetch request $1 with `sdp_get module=request id=<id>`, and its discussion with
`sdp_list_notes` when the ticket has any. Write `.work/cache/SDP-<id>.md` in the
same shape a files-mode ticket uses.

**Store only these fields:**
id, subject, status, requester, priority, category/subcategory, the description,
and the last 3 notes.

**Discard everything else** — the full note history, resolution HTML, attachments,
approval chains, SLA and OLA timers, every UDF the desk has ever defined, the
audit trail, and the account/site metadata.

This is the whole game. A single SDP request payload runs several thousand tokens
and about forty of them affect what you build. `/crew:work` reads the cache,
never the API, so that payload is paid for once instead of on every pickup,
retry, and context reset.

Searching for a ticket: `sdp_search module=request value="<terms>" open_only=true`.
Never list a whole queue to find one request.

## Push (`--push`)

Two writes at most, and only at a boundary:

1. **One note** — `sdp_add_note module=request id=<id>`, with
   `public=false` unless `sdp.noteVisibility` is `"public"`:

   > files touched, smoke result, reviewer used (Codex or Claude), BLOCK count.
   > Two sentences.

2. **The status**, via `sdp_transition`.

Never paste diffs, review output, or agent reasoning into the desk. That is what
the repo and the pull request are for, and it makes the request more expensive
for the next person to read.

### Four SDP-specific traps

- **Notes are visible to the requester** unless marked private, and a requester is
  often not an engineer. Scrub before writing: no hostnames you were not given, no
  credentials, no secret values, no internal IPs, no customer names from other
  tickets. `public=false` is the default here for that reason, and it is not a
  substitute for scrubbing — a private note is still in the desk's record.
- **A bad field value rejects the whole write.** SDP does not partially apply an
  update. Resolve names first with `sdp_list_metadata` (`collection=status`,
  `category`, `priority`) and send what the desk will actually accept, rather than
  what the local ticket happens to call it.
- **Closing is not crew's decision by default.** `sdp.closeOnDone` is `false`:
  push transitions the request and leaves closure to whoever owns the queue.
  Set it to `true` only for a queue that is genuinely yours, and even then use
  `sdp_close` (which goes through the desk's closure endpoint and satisfies
  mandatory closure fields) rather than an `sdp_update` that fakes it.
- **A failed write is simply gone.** There is no local outbox. If a note fails,
  say so in the session rather than assuming the desk has it — and re-read with
  `sdp_get` before retrying, so a partial success is not duplicated.

## Sync at boundaries only

Pickup and completion. Never mid-task. If one ticket causes three SDP calls, the
cache is wrong — fix the cache rather than adding calls.

## Configuration

```json
"tracker": "sdp",
"sdp": { "portal": null, "noteVisibility": "private", "closeOnDone": false }
```

`portal` is only needed where the connector serves more than one SDP
instance/portal; leave it `null` otherwise. Write it once, from
`sdp_whoami`/`sdp_list_metadata`, rather than looking it up per ticket.
