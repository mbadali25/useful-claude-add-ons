---
description: Take a repository's merge gate down and put it back, from the export
argument-hint: <disable | enable | status> <github | bitbucket>
allowed-tools: Read, Bash, Grep, Glob
---

Merge gate: $ARGUMENTS

This command changes **branch protection on a live repository**. Nothing below
happens because a config file said so — config is intent, not consent.

## 0. Read `guards.mergeGate` first, before anything else

Not after resolving the provider, not after finding the script. First.

```
python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_config.py --root . --guard mergeGate --json
```

That prints `policy`, `decision`, `heldDownBy`, `repo` and `global`. Read
`policy`, and read it from **this** command — not from `.crew/config.json`,
because the effective value is the NARROWER of the repo and machine-global
layers and the repo file cannot show you the other one.

- **`block`** — the shipped default. **Refuse, and say why.** Print the exact
  words: `guards.mergeGate is` `block`, so crew may not change this
  repository's merge gate. Name the two fixes — set `guards.mergeGate` to `ask`
  or `allow` with `/crew:config`, or run `merge_gate.sh` yourself — and stop.
  Do not run `status`. Do not run `export`. `export` is a real API call
  needing admin scope, and "I only looked" is not a thing a refusal gets to do.
- **`ask`** — print the exact command you are about to run (script path,
  subcommand, owner/workspace, repository, and every flag resolved from
  config), then wait. Do not proceed on silence. Ask again for each invocation:
  one yes is one command, not a session.
- **`allow`** — run it without asking, and say what you ran and what it
  returned. Under `allow` nothing is silent: `allow` removes the question, not
  the record.

If `heldDownBy` is set, say which layer is holding it down in the same breath.
A user who set `allow` in the repo and is being refused needs to be told their
machine-global `block` is why, or the key looks broken.

## 1. Resolve the provider's script — a missing skill is a STOP

| provider | script |
|---|---|
| `bitbucket` | `skills/bitbucket/scripts/merge_gate.sh` |
| `github` | `skills/github/scripts/merge_gate.sh` |

**crew bundles neither.** They belong to other marketplace entries, and crew
references them; it never reimplements them. If the script for the named
provider is not on this machine, that is a **stop** — the same shape as an
absent `rollback` key in `/crew:promote`, not a warning to walk past. Say
"`/crew:gate <provider>` needs the `<provider>` skill and it is not installed",
name the two fixes (install it, or run the script yourself), and stop.

Do not hand-roll a `branch-restrictions` or a `branches/*/protection` API call.
Do not let "could not check" become "checked, and fine" — that collapse is the
bug this repo keeps rediscovering, and here it would report a gate as down when
nothing was read.

## 2. The two scripts are NOT interchangeable, and the differences bite

Same four exit codes, a different argument surface. Read the provider's own
`--help` before you compose a command; the table below is what to expect, not a
substitute for asking the script.

| | bitbucket | github |
|---|---|---|
| `status` | — | `status <owner> <repo> [--branch NAME]`, read-only, prints both surfaces |
| `export` | `export <ws> <repo> <outfile>` — repo-wide | `export <owner> <repo> <outfile> [--branch NAME]` — **branch-scoped**, because GitHub's classic protection is per-branch in the URL |
| `disable` | `disable <ws> <repo> [--branch NAME] [--export-to FILE] [--branch-type LIST\|none] [--dry-run]` | `disable <owner> <repo> [--branch NAME] [--export-to FILE] [--allow-inherited] [--dry-run]` |
| `enable` | `enable <ws> <repo> [--branch NAME] [--from-export FILE]` | `enable <owner> <repo> --from-export FILE` — **`--from-export` is REQUIRED and `--branch` is a usage error (exit 2)** |
| a bare `enable` | applies a hardcoded four-kind preset | refused: "This script has no preset and will not invent a merge gate" |

Neither script has a `--preset` flag. `bitbucket.mergeGate.preset` is therefore
wired to nothing — say so whenever you show a Bitbucket `enable`, or the
`"standard"` in the config reads as a choice that was honoured (CONFIG.md §8).
`github.mergeGate` has no `preset` key at all, which is that decision made once
rather than inherited.

`branch` binds the same way in both: `null` — the shipped default — means pass
no `--branch` and let the script ask the API which branch this repo calls main.
Never substitute `main` yourself. On a repo still on `master`, or a Gitflow
`develop`, a gate on `main` looks configured and watches a branch nobody merges
into.

## 3. `status`

Read-only, and still gated by step 0: `block` refuses it.

- **github** — `status <owner> <repo>`. It reports both surfaces, classic branch
  protection and rulesets, each with its own state. Relay all of it. A surface
  whose state is `unreadable` is **not** "none configured": a classic read
  without admin answers 404 `Not Found`, the same status as an unprotected
  branch, and only the exact message `Branch not protected` means absent.
- **bitbucket** — there is no `status` subcommand. Use `export` to a temporary
  file and report what it holds, and say that you made a real API call to find
  out, because you did.

## 4. `disable` — export, then delete, and the export is the only way back

The order is not negotiable, and it is one invocation, not two: pass
`--export-to FILE` on the `disable` itself so the backup and the delete cannot
come apart. A `disable` that ran without an export is a gate you cannot restore.

1. Run with `--dry-run` first. Show the plan it prints.
2. Under `ask`, wait for the yes on the real command. Under `allow`, run it and
   report. Under `block` you never got here.
3. Name the export file's path in your report, in full. The merge happens
   **outside this command** — crew does not merge here — so the path has to
   survive into whatever does, and a path nobody wrote down is an export nobody
   can restore from.

## 5. `enable` — restore from the export, never a bare re-enable

**Never `disable` and then a bare `enable`.** Bitbucket's `disable` removes more
kinds than its `PRESET` creates — `restrict_merges` and
`require_no_changes_requested` among them — so the pair silently drops whatever
those were, and the repository ends up with a gate that looks restored and is
weaker than the one its owner built. GitHub's script refuses the shape outright
rather than documenting against it.

**The only restore is `enable --from-export <the file disable wrote>`.** If you
do not have that file, say so and stop. Do not reconstruct a gate from what you
remember of the `status` output, and do not offer a preset as a substitute — it
is a different gate wearing the old one's name.

GitHub's `enable --from-export` hard-refuses an export holding an `unreadable`
surface, and that refusal is correct: restoring half a gate while reporting
success is worse than restoring none.

`--branch` is **ignored** with `--from-export` on Bitbucket (each exported
object carries its own scope) and is a **usage error** on GitHub. Either way, do
not report a restore as having been scoped to the configured branch.

## 6. Relay the script's outcomes; do not re-summarise them

Four exits, and three of them are not "failed":

- **exit 0** — did what it said. Report the counts it printed.
- **exit 1** — an API or IO failure. Quote it.
- **exit 3 — nothing was deleted.** Bitbucket: the branch's scope could not be
  resolved against the branching model, and the script refuses to guess which
  `--branch-type` values cover your branch. GitHub: the same, plus two more
  causes — an org or enterprise ruleset that gates the branch and cannot be
  deleted through the repo endpoint (escape hatch: `--allow-inherited`), or a
  gate surface that could not be READ at all. Quote the message and stop. Do
  not pick a `--branch-type` on the user's behalf, and do not reach for
  `--allow-inherited` without asking — it widens what gets deleted.
- **exit 4 — one or more writes failed.** The live repository is now
  **partially** changed. Say which kinds landed and which did not. "Failed" on
  its own reads as "nothing happened", which is false and is the reading that
  gets someone to re-run it.

`not-available-on-this-plan` on a Premium-only Bitbucket kind is its own
outcome — neither applied nor failed. Report it as itself.

## What this command does not do

It does not merge anything. It does not decide that a gate should come down. It
does not restore a gate it did not export. And it does not run at all while
`guards.mergeGate` is `block`, which is what it ships as.
