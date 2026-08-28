---
description: Scope a request into a ticket
argument-hint: <what needs doing>
allowed-tools: Read, Write, Edit, Bash, Agent
---

Turn this into a ticket: $ARGUMENTS

Scope it first. Use `crew:explorer` to check what it touches and whether it
crosses repo boundaries. Then ask me about genuine ambiguity — one round of
questions, not three.

Read `.crew/config.json` -> `tracker`.

**Files mode.** Write `.work/tickets/T-####.md` (next free number), under 20 lines:
```
# T-#### <title>
status: open
repos: <this-repo>[, other-repo]
risk: low | medium | high

## Want
<2-3 sentences: outcome and why>

## Scope
- touch: <paths>
- do not touch: <paths>

## Done when
- [ ] <observable, testable condition>
- [ ] smoke passes
- [ ] <new smoke check, if this is new behavior>

## Notes
<landmines explorer found, ADR links, cross-repo dependencies>
```
Append to `.work/INDEX.md`: `T-#### | open | <risk> | <repos> | <title>`

**Jira mode.** Same content, created via the Jira MCP tools. Summary = title,
Description = the Want/Scope/Done sections, Labels = repos. Then write the same
markdown to `.work/cache/<KEY>.md` so `/crew:work` never has to call the API to
read it back.

**ServiceDesk Plus mode.** Same content, created with `sdp_create module=request`.
Subject = title, description = the Want/Scope/Done sections. Resolve category,
priority and status against `sdp_list_metadata` before writing - SDP rejects the
whole request on an unrecognised value rather than partially applying it. The
description is visible to the requester, so scrub it the way `/crew:sdp-sync`
describes. Then write the same markdown to `.work/cache/SDP-<id>.md`, and use
`SDP-<id>` as the local key everywhere - the bare number the desk returns is
invisible to the rest of crew, which recognises a ticket by its `LETTERS-digits`
shape.

**Obsidian Kanban mode.** Same content, written as a note in the vault:
`<obsidian.vaultPath>/<obsidian.boardDir>/T-####.md`, using the next free
number the way files mode does. Then add one card to the `ready` lane of the
board file — or to `backlog` when the caller says this is deferred rather than
scoped, which is how `crew:pm` files a non-blocking finding:

```
- [ ] [[T-0042]] <title>
```

Insert the line under that lane's heading and change nothing else — the
frontmatter, the trailing `%% kanban:settings` block and the `**Complete**`
marker are all load-bearing, and `/crew:obsidian-sync` explains why. Then write
the same markdown to `.work/cache/T-####.md` so `/crew:work` never has to open
the vault to read it back. The key keeps the `T-####` shape, which the rest of
crew already recognises.

Then append to `.work/INDEX.md` exactly as files mode does:
`T-#### | open | <risk> | <repos> | <title>`. This is the one place Obsidian
mode differs from Jira and ServiceDesk Plus, and deliberately: the session brief
finds the open ticket by reading `INDEX.md`, and a key shaped `SDP-40219` was
never going to be in there, but `T-0042` can be. The board is the human's view
of the work; `INDEX.md` is the session's. Keeping both costs one line and is
what makes the brief name a real ticket instead of nothing.

Terseness is the point either way — this file is re-read on every pickup.

Multi-repo work gets one ticket per repo, cross-referenced by ID in Notes.
Never write a ticket that silently spans repos.
