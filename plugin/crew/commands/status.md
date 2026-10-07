---
description: Read-only crew status for this repo - config, roster, tickets, review budget, gate, codemap, gitignore, handoff
argument-hint: "[--memory | --approvals | --owner]"
allowed-tools: Bash, Read
---

Show where this repo's crew stands. **Read-only**: this command dispatches
nothing, edits nothing and writes no file. It replaces what the 0.20 PM, roster
and scale commands reported, and none of what they did.

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_status.py" --root . $ARGUMENTS
```

On Git Bash without `python3`, use `python` or `py -3` with the same arguments.
If none resolves, say so and stop - do not reconstruct the report by hand.

Print its output as-is. It is at most 40 lines by construction; do not add a
summary above or below it, and do not pad it with advice.

## What each line means

| Line | Source | When it says "unknown" |
|---|---|---|
| header | `git rev-parse`, `git status --porcelain` (no index refresh) | not a git repo |
| `inert` | `crew_config.inert_settings`: each setting this crew does not act on, `key=value (ticket)`; absent when none (CONFIG.md §20) | `could not tell (...)` when the check failed |
| `config` | `.crew/crew.json` (1.0) or `.crew/config.json` (0.20) - in a linked worktree with neither, the main checkout's, shown on a second `config` line (`inherited from the main checkout (<path>) ...`, or `could not tell (...)` when git cannot name it); a linked worktree whose own file is in force while the main checkout also has one gets `... the main checkout's (<path>) is not read ...` there, naming the delete that inherits (a crew <= 1.0.59 heal wrote such defaults) | JSON unreadable |
| `roster` | `agents` in crew.json, or `roles` measured against the 1.0 four | - |
| `tickets` / `open` / `owner` | `.work/tickets/`, `.work/INDEX.md`; `owner` lists `needs-owner` rows, and `cancelled` / `superseded` rows are on no line | - |
| `waiting` | `crew_autopilot_owner.owner_items` (L-0551): how many open tickets are stopped on you, from autopilot's own phase read; `, C in review not read` and `, U could not tell` only when non-zero | no `.work/INDEX.md`, or autopilot's module cannot be read |
| `review` | review ledgers under the git common dir, newest three: state, rounds used of the budget, and refunded tool-failure rounds (`review_ledger.summary`) | a ledger that will not parse |
| `in-flight` | T-0049's markers under `<git-common-dir>/crew/inflight/` (`crew_inflight.survey`): ticket, state, runner, since, and for stale or unknown the owner's `clear` command; at most 5, then `+N more`; `none` when there are none | the directory unreadable, or `crew_inflight` not importable |
| `verify` | `.crew/.verify-gate.record.json`, counted by status | record unreadable |
| `shell` | Windows only: `shellRoute` config and the `crew_shell.py probe` cache; runs no `wsl.exe` or `pwsh` | never probed - run /crew:config |
| `codemap` | anchors checked by path diff, as `crew_freshness.read_knowledge` does | no git |
| `gitignore` | `crew_gitignore.py summary`: `current` (`current except N conflict(s)` when a human `!` line kept a row out), `N missing (<langs>)`, or `owner: ...` (a tracked secret-shaped file); measured with `git check-ignore`, read-only | git failed or timed out, `.gitignore` not UTF-8, a malformed managed block |
| `graph-ignore` | `crew_graph_ignore.py`: a secrets-denylisted path on disk that `.graphifyignore` does not exclude reads `UNCOVERED` with the paths and the `--write` fix (which never overrides a `!` line of yours: it names the line instead) | git missing, a settings file that will not parse, a nested `.graphifyignore`, an unexcluded nested repository, a symlink leaving the repo, a deny-all `Read` rule |
| `metrics` | `.crew/metrics.jsonl`, else `.crew/metrics.md` - in a linked worktree, the main checkout's `.crew/`, named by its path; this worktree's own copies, if any, are named on the same line as `not counted` | `could not tell (...)` when git cannot name the main checkout; nothing is read, and the worktree's own copy is never the fallback |
| `handoff` | `.work/HANDOFF.md` present | - |
| `migrate` | a backup under `.crew/backups/` whose apply never finished | - |
| `memory` | `crew_context.py --stats`, only with `--memory` | hook not installed |

## `--memory`

Adds the context hook's own numbers - what it injects and how often - by
running `crew_context.py --stats` from the plugin's scripts directory. When
that script is not installed the line reads `context hook not installed`;
when it fails, the exit code and its first stderr line are shown. Neither
case is reported as zero.

## `--owner`

Lists what waits on the owner: the `waiting` count line, then one line per
ticket stopped on a person, `<id>  <phase>  <command or question>`, from
autopilot's own phase read (`/crew:autopilot status <id>` agrees). It runs
nothing, reads no policy and never reads a finished review round or a ship's PR
(those are `review-unread`, pointing at `/crew:autopilot status <id>`). At most
40 lines. Not with `--memory` or `--approvals`. Offer it only when asked.

## `--approvals`

Prints only the open tickets whose spec and plan exist and validate and whose
approval is missing, stale or unaccepted, one ready-to-paste
`/crew:approve <id>` line each with `  why: <why>` under it, then a count of any whose spec and
plan do not validate. Merged, current and spec-only tickets are left out;
none pending prints `nothing needs approval`; no readable `.work/INDEX.md`, or an unreadable main-checkout one in a linked
worktree, prints `could not tell (<reason>)`; a main checkout with no INDEX adds a `note:` line. Read-only.

## What to do with it

The report is facts, not instructions. When a line points somewhere:

- `run /crew:migrate` - the repo is still on the 0.20 layout.
- `run /crew:init` - no crew config at all.
- `INTERRUPTED apply` - run `/crew:migrate --rollback <dir>` before anything else.
- `gitignore N missing` - `crew_gitignore.py apply --root .` outside a ticket, or the next `/crew:onboard`.
  `owner:` - a secret is committed: rotation and history are the owner's call, never an ignore line.
- `behind: <subsystem>` - `/crew:onboard --refresh <subsystem>` when the
  path diff says the cited files moved.

Do not act on any of these unasked. Offer the one command and stop.
