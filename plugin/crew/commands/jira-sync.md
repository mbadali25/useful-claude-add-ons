---
description: Sync a ticket between Jira (via MCP) and the local cache
argument-hint: <ISSUE-KEY> [--push --to in-progress|done]
allowed-tools: Read, Write, Edit, Bash, ToolSearch
---

Sync $ARGUMENTS.

## Preconditions

1. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py resolve --root .` must say `jira`.
2. The Atlassian MCP server must be connected. Check your available tools for
   `mcp__atlassian__*`. If tool search is active you may need to search for them
   rather than seeing them listed.

If either is missing, say exactly which one and stop. Do not fall back to file
tickets — a silent fallback splits the source of truth and you will not notice
until two people have divergent ticket state.

## Discover tools, do not assume names

Atlassian's Rovo MCP server has changed tool names between versions. Find the
read, edit, comment, and transition tools for Jira issues before calling them.
Cloud instances also require a cloudId — fetch the accessible resources once and
cache it in `.crew/config.json` under `jira.cloudId` so you never look it up twice.

## Pull (default)

Fetch issue $1. Write `.work/cache/<KEY>.md` in the same shape a files-mode
ticket uses.

**Store only these fields:**
key, title, status, description, acceptance criteria, labels, and the last 3
comments.

**Discard everything else** — reporter, watchers, sprint and board metadata,
custom fields, attachments, changelog, full comment history, rendered ADF.

This is the whole game with Jira. A single Jira issue payload can run several
thousand tokens and roughly forty of them affect what you build. `/crew:implement`
reads the cache, never the API, so that payload gets paid once instead of on
every pickup, retry, and context reset.

When you query for multiple issues, use JQL with an explicit field list and a
`maxResults` cap. Never fetch a board or a whole sprint to find one ticket.

## Push (`--push --to <status>`)

`--to` names the destination, and only two exist: `in-progress` (pickup) and
`done` (completion) — the two moves `crew_tracker.py` delegates. The move that
delegated printed the Jira status on its next line, `jira: target: <name>`;
`crew_tracker.py map --to <word>` prints it again. Never guess a status.

1. Read the issue's current status, then run
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py transition --root . --ticket $1 --to <word> --seen "<status>"`.
   `go: <name>`: transition to that name. `unchanged:`: skip the transition.
   `refused: <why>`: stop and report `tracker not updated: <why>`.
2. If the workflow has no direct transition from the current status to the
   target, stop and report it; never chain transitions you were not given.
3. On `--to done`, and only then, post exactly ONE comment by `Posting once`
   below, event kind `done`:

   > files touched, smoke result, reviewer used (Codex or Claude), BLOCK count.
   > Two sentences.

`--push` with no `--to`, or any other target: say which status is missing and
stop. Never guess the destination from the issue's current state.

Never paste diffs, review output, or agent reasoning into Jira. That is what the
repo and the PR are for, and it makes the issue more expensive to read back later.

## Posting once

Both sync commands post through this one procedure (sdp-sync points here), so
a post that timed out is searched for before it is ever posted again. Each post
has a durable event id. Here the marker search is `listJiraIssueComments` on
the issue and the post is the comment tool; sdp-sync names its own two.

1. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py event begin --root . --ticket <KEY> --event done`
   prints `<answer>: <id>`. `skip`: already posted, stop. `in-flight` or
   `could not tell`: do not post; report it.
2. `post` or `check-remote`: run the marker search for the line
   `crew-event: <id>`. Found: record it `posted` (step 4) and stop.
3. `check-remote` and absent: search once more, as the last call before the
   repost. Found: record it `posted` and stop.
4. Post the body with `crew-event: <id>` as its plain last line, then run
   `crew_tracker.py event record --root . --ticket <KEY> --event done --state posted --ref <post id>`.
5. A timeout or no answer is `--state unknown`, never `failed`: it may have
   landed. Record it, run `event begin` again and go on from step 2, posting
   at most once more. If that fails too, record `unknown` and report
   `tracker not updated: event <id> not posted`.

## Sync at boundaries only

Pickup and completion. Never mid-task. The call budget for one ticket: pickup
read 1; push `--to in-progress` 2 (read status, transition); push `--to done` 4
(read status, transition, marker search, post); done after one timed-out post
at most 7 (the 4, the check-remote search, the last search, the one repost).
More calls than this budget for one ticket means the cache or the procedure is
wrong — fix that rather than adding calls.

## Auth note

Anthropic and Atlassian both moved off the old SSE endpoint; `/v1/sse` was retired
mid-2026. Use the `/v1/mcp` HTTP endpoint. If you hit repeated mid-session
re-authentication with OAuth, switch to API token auth, which does not drop the
way the OAuth flow does.
