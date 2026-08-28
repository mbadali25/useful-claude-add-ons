---
description: Sync a ticket between an Obsidian Kanban board and the local cache
argument-hint: <T-####> [--push]
allowed-tools: Read, Write, Edit, Bash, Glob
---

Sync $ARGUMENTS.

## Preconditions

1. `.crew/config.json` -> `tracker` must be `"obsidian"`.
2. `obsidian.vaultPath` must resolve to a directory that exists. If it is
   `null`, fall back to `memory.vaultPath`; if that is also null or missing,
   stop.
3. The board file must exist at
   `<vaultPath>/<obsidian.boardDir>/<obsidian.board>`.

If any of those is missing, say exactly which one and stop. Do not fall back to
file tickets — a silent fallback splits the source of truth and you will not
notice until two people have divergent ticket state. That hazard is *worse*
here than with Jira, not absent: both sides are local markdown and both look
equally authoritative.

## What is authoritative

The board and the ticket note in the vault are the remote, exactly as Jira is.
`.work/cache/T-####.md` is a terse local mirror that `/crew:work` reads so the
vault is touched at boundaries only.

| | Wins |
|---|---|
| Status, on pull | The card's **lane**. Dragging a card in Obsidian is how a human changes status, and it has to mean something. |
| Content, on pull | The ticket note. |
| Both, on push | Crew. Push writes the lane and appends to the note. |

Never write the board and the note in one direction and the cache in the other.

## The board file format — do not reconstruct it

An Obsidian Kanban board is a markdown file the plugin round-trips. Three parts
are load-bearing and a naive rewrite destroys them, after which the file
silently stops rendering as a board and opens as plain text:

````markdown
---

kanban-plugin: board

---

## Backlog


## Ready

- [ ] [[T-0042]] Fix token refresh on 401


## In Progress


## Review


## Done

**Complete**

- [x] [[T-0039]] Bump pinned deps




%% kanban:settings
```
{"kanban-plugin":"board"}
```
%%
````

- `kanban-plugin: board` in the frontmatter is what makes it a board.
- The trailing `%% kanban:settings` block holds the board's own settings. Keep
  it byte-for-byte and keep it last.
- `**Complete**` is the marker the plugin looks for in the done lane. Removing
  it turns finished cards back into open ones.
- An archive, when one exists, is a `***` thematic break followed by
  `## Archive`. Leave everything below that break alone.

So: read the file, edit the one card or the one lane, write it back. Edit in
place with `Edit`; never regenerate the whole board from the cache.

## Lanes

Read the names from `obsidian.columns` rather than hardcoding them — a user with
an existing board renames lanes in config, not in the vault.

| Config key | Default | Means |
|---|---|---|
| `backlog` | `Backlog` | Deferred or untriaged. Where the PM parks a non-blocking finding. |
| `ready` | `Ready` | Scoped by `/crew:ticket` and pickup-able. |
| `inProgress` | `In Progress` | `/crew:work` has it. |
| `review` | `Review` | Implementation done, `/crew:review` outstanding. |
| `done` | `Done` | Complete and verified. Carries `**Complete**`. |

A lane named in config that does not exist on the board is a setup error. Say
so and stop; do not create the lane, because the likelier cause is a typo than a
missing column.

## Pull (default)

1. Find the card for $1 in the board — a list item whose text contains `[[$1]]`
   or the bare key. Note which lane it is in.
2. Read `<vaultPath>/<obsidian.boardDir>/$1.md`.
3. Write `.work/cache/$1.md` in the same shape a files-mode ticket uses.

**Store only these fields:** key, title, status (derived from the lane), the
Want / Scope / Done when sections, and the last 3 notes.

**Discard everything else** — Dataview blocks, card metadata the plugin appends
(dates, tags, per-card settings), backlink lists, and anything the vault's own
templates injected. Those belong to Obsidian, not to the work.

If no card exists for $1, say so and stop. A ticket note with no card is not
tracked by anything, which is the failure this command is supposed to surface.

## Push (`--push`)

**The cache names the destination.** `--push` does not take a lane and does not
infer one from context: it reads `status:` from `.work/cache/$1.md` and maps
that through `obsidian.columns`. So the caller changes the status in the cache
first, then pushes. Without that rule the destination lane is whatever the
session happened to be thinking about, which is how a card ends up in `Done`
because the turn went well.

| `status:` in the cache | Lane |
|---|---|
| `open` | `ready` |
| `deferred` | `backlog` |
| `in-progress` | `inProgress` |
| `review` | `review` |
| `done` | `done` |

A `status:` that maps to no lane is an error: say which value you found and
stop. Guessing a lane moves a card a human is looking at.

1. Move the card to that lane. Moving means cutting the one line and inserting
   it under the target heading — not rewriting the file.
2. If the target is the done lane, the card becomes `- [x]` and goes below
   `**Complete**`.
3. Update `.work/cache/$1.md` so its `status:` and the board agree. A push that
   moves the card and leaves the mirror stale recreates the divergence this
   command exists to prevent, in one file instead of two.
4. When and only when the status is `done`, append exactly ONE note to the
   ticket note in the vault:

> files touched, smoke result, reviewer used (Codex or Claude), BLOCK count.
> Two sentences.

Never paste diffs, review output, or agent reasoning into the note. That is
what the repo and the PR are for, and it makes the note more expensive to read
back later. Intermediate pushes move the card and write nothing — a note per
lane change is noise, and the board already shows the movement.

## Sync at boundaries only

Pickup and completion. Never mid-task. The vault is a folder of files, so there
is no rate limit to respect and no payload to amortise — the reason to hold the
line is different and better: every mid-task write is a chance to corrupt a
board that a human is looking at in another window.

## When the vault is a git repo of its own

Common, and worth stating during setup rather than discovering at merge time.
Crew does not commit the vault. If it is versioned, the board's history is the
user's to manage, and a board edited in two places at once conflicts the way any
markdown file does.
