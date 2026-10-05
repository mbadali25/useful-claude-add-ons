---
description: Sync a ticket between an Obsidian Kanban board and the local cache
argument-hint: <ID> [--push]
allowed-tools: Read, Bash
---

Sync $ARGUMENTS.

The lifecycle commands already move the card at every transition through
`crew_tracker.py` — brainstorm creates it, spec, plan, implement and done move
it. This command is for looking, and for repairing a board that fell behind.

## Preconditions

1. `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py resolve --root .`
   must say `obsidian`. It reads `.crew/crew.json` (`tracker.kind`,
   `tracker.obsidian`) and `.crew/config.json` (`tracker`, top-level
   `obsidian`) alike; `could not tell` means the two disagree — show me its
   line and stop, never pick one.
2. `obsidian.vaultPath` (else `memory.vaultPath`) must be an existing
   directory holding `.obsidian/`, and the board must exist at
   `<vaultPath>/<obsidian.boardDir>/<obsidian.board>`.

The script checks all of this and names what failed. Do not fall back to file
tickets — a silent fallback splits the source of truth, and here both sides
are local markdown that look equally authoritative.

## What is authoritative

`.work/INDEX.md` is the session's view; the board is the human's. Both are
written by the same `move`, and each half reports its own result.

| | Wins |
|---|---|
| Status, on pull | Nothing is changed. `read` reports the board lane beside the INDEX status and says when they disagree — a human dragging a card is a question to put to me, not an instruction. |
| Status, on push | Crew. `move` writes the lane the INDEX status maps to and reports the lane it moved the card from. |
| The ticket note | Written once, at create, and never rewritten; moved, never rewritten, to `<boardDir>/Complete/` by `crew_tracker.py archive`. |

There is no `.work/cache/` mirror: the ticket's content lives in
`.work/tickets/$1/`, which no tracker writes.

## Pull (default)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py read --root . --ticket $1
```

Print its lines verbatim. When the board lane and the INDEX status disagree,
say so and ask which is right. Do not move anything on a pull.

## Push (`--push`)

The INDEX status names the destination; `--push` does not take a lane and does
not infer one from context. Read `$1`'s status cell from `read`'s `files:` line,
then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tracker.py move --root . --ticket $1 --to <that status>
```

Print its lines verbatim. On exit 1 tell me `tracker not updated: <reason>`.

| INDEX status | Lane (`obsidian.columns` key) |
|---|---|
| `direction`, `ready`, `needs-owner` | `backlog` |
| `spec`, `planned` | `ready` |
| `in-progress` | `inProgress` |
| `review` | `review` |
| `done` | `done` (checked, below `**Complete**`) |
| `cancelled`, `superseded` (closed; leaving one needs `--reopen`) | `done` (checked) |

Any other status maps to no lane and is refused with nothing written: say which
value you found and stop. Guessing a lane moves a card a human is looking at.
The table lives in `crew_tracker.py` as `LANE_FOR_STATUS`; this is a copy.

## The board file format — the module owns it

An Obsidian Kanban board is markdown the plugin round-trips. `kanban-plugin:
board` in the frontmatter, the trailing `%% kanban:settings` block and
`**Complete**` in the done lane are load-bearing, and a naive rewrite leaves a
file that opens as plain text. So never edit the board with `Edit` or `Write`:
`crew_tracker.py` cuts the one card and inserts it under the target heading,
leaves every other byte — archive included — as it was, and refuses a board
that is missing its frontmatter key, a configured lane, or has one twice, or
whose done lane lacks exactly one `**Complete**`.

Lane names come from `obsidian.columns` rather than being hardcoded — a user
with an existing board renames lanes in config, not in the vault. A lane named
in config that is absent from the board is a setup error the script reports;
do not create the lane.

## Writes stay in the vault

The script is the only crew code that writes outside the repository, and it
refuses — writing nothing, INDEX included — when the vault is missing or has no
`.obsidian/`, `boardDir` is absolute or contains `..`, `board` contains a
separator, the board or note resolves outside the vault through a symlink, or
the board or note sits inside this worktree without git ignoring it (it would
enter the review bundle), or the ticket's note names another repo (a shared
board, `boardDir` unset). Every board write is an exclusively created temp file
plus `os.replace`, keeping the board's mode and owner, re-reading it first and
recomputing if Obsidian saved it meanwhile. A card whose owner cannot be told —
no note, or a note with no `repo-id:` — is refused by `create` and `move`
alike, whatever its text says; `read` says `whose card could not tell`.

## When the vault is a git repo of its own

Common, and worth stating during setup rather than discovering at merge time.
Crew does not commit the vault. If it is versioned, the board's history is the
user's to manage, and a board edited in two places at once conflicts the way any
markdown file does.
