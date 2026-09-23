---
description: Read-only crew status for this repo - config, roster, tickets, review budget, gate, codemap, handoff
argument-hint: "[--memory]"
allowed-tools: Bash, Read
---

Show where this repo's crew stands. **Read-only**: this command dispatches
nothing, edits nothing and writes no file. It replaces what `/crew:pm`, <!-- deliberate -->
`/crew:roster` and `/crew:scale` reported in 0.20, and none of what they did. <!-- deliberate -->

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
| `config` | `.crew/crew.json` (1.0) or `.crew/config.json` (0.20) | JSON unreadable |
| `roster` | `agents` in crew.json, or `roles` measured against the 1.0 four | - |
| `tickets` / `open` | `.work/tickets/`, `.work/INDEX.md` | - |
| `review` | review ledgers under the git common dir, newest three | a ledger that will not parse |
| `verify` | `.crew/.verify-gate.record.json`, counted by status | record unreadable |
| `codemap` | anchors checked by path diff, as `crew_freshness.read_knowledge` does | no git |
| `metrics` | `.crew/metrics.jsonl`, else `.crew/metrics.md` | - |
| `handoff` | `.work/HANDOFF.md` present | - |
| `migrate` | a backup under `.crew/backups/` whose apply never finished | - |
| `memory` | `crew_context.py --stats`, only with `--memory` | hook not installed |

## `--memory`

Adds the context hook's own numbers - what it injects and how often - by
running `crew_context.py --stats` from the plugin's scripts directory. When
that script is not installed the line reads `context hook not installed`;
when it fails, the exit code and its first stderr line are shown. Neither
case is reported as zero.

## What to do with it

The report is facts, not instructions. When a line points somewhere:

- `run /crew:migrate` - the repo is still on the 0.20 layout.
- `run /crew:init` - no crew config at all.
- `INTERRUPTED apply` - run `/crew:migrate --rollback <dir>` before anything else.
- `behind: <subsystem>` - `/crew:onboard --refresh <subsystem>` when the
  path diff says the cited files moved.

Do not act on any of these unasked. Offer the one command and stop.
