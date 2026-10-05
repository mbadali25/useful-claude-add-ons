# A GitHub Actions deploy under `/crew:promote`

_Read from `SKILL.md` section 4 and from `/crew:promote` gate 2 when the
environment carries a `github` entry in `.crew/verify.json`. The helper is
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_ghdeploy.py`; every
subcommand takes `--root . --env <name> [--index N]` (N picks one entry of a
list, default 0) and ends its output with one `result=...` line._

## Gate 2 for a `github` environment: the five steps

Run them in order, one entry at a time. **Stop at the first step that does not
say what the table below lets you continue on**, and report the step and its
last line verbatim.

| Step | Command | Exit codes and what to do |
|---|---|---|
| 1. prepare | `crew_ghdeploy.py prepare` | 0: the dispatch is the line before `result=`; go on. 2: refused by name (an entry problem, `unmapped-workflow`, `class-mismatch`, `sha-not-on-remote`, ...): fix what it names, then start again. 3: could-not-tell: stop. |
| 2. dispatch | the printed `gh workflow run ...`, **as its own Bash call**, exactly as printed | The cloud guard and promote-gate judge it there. A block is gate 1 failing: fix the precondition it names. A non-zero exit is a stop. |
| 3. identify | `crew_ghdeploy.py identify` | 0: the run is named; go on. 3: could-not-tell (two candidates, none in time, unreadable): **stop**. Do not pick a run from the Actions tab yourself; go to step 5. |
| 4. watch | `crew_ghdeploy.py watch` | 75: the slice ended with the run unfinished: **run watch again**. 0: pass. 1: fail. 3: unknown (unreadable, or still running at the deadline: the run is left running and named). Go to step 5 on 0, 1 or 3. |
| 5. record | `crew_ghdeploy.py record` | 0: written to `.work/PROMOTIONS.md`. 3, by reason: `record-without-verdict` - run watch first, then record; `state-file-missing` / `state-file-unreadable` - prepare never ran or its file is damaged: nothing can be recorded from it, so stop and report that the deploy is unrecorded; `promotions-unreadable` - `.work/PROMOTIONS.md` cannot be read (a directory, permissions): fix that file, then run record again. |

After a pass, gates 3 to 5 run as for any environment and promote writes the
table row as today. On fail, unknown or could-not-tell, the sequence stops at
gate 2: `record` has already written a `not-run` row (the deploy is recorded
and is never a pass) and names the previous all-pass sha. **There is no
automatic rollback, re-dispatch of an older sha, or cancel**: say which
happened, quote the record's lines, and give the owner the two options -
roll back (re-promote the previous good sha) or fix forward. A person chooses.

`--dry-run` prints `crew_ghdeploy.py check`'s output (the dispatch for HEAD
and every environment the gates apply to it) and runs nothing else.

## What `record` writes

One detail line, always, with no pipe character:

```
- deploy <env> <sha40> github <workflow>@<ref> run <id|none> <pass|FAIL|unknown|could-not-tell> <url|-> at <UTC> - <reason>
```

On anything but pass, also: `previous all-pass sha for <env>: <sha|none>`,
the last 40 lines of `gh run view <id> --log-failed` (colour codes removed,
every `|` shown as `/`, each line clipped to 300 characters, indented), and
the row `| <UTC> | <env> | <sha40> | not-run | not-run | not-run | <actor> |`.
The file is rebuilt whole and replaced, never written in place. `.work/` is
gitignored, so the excerpt is never committed; it relies on GitHub's secret
masking and is bounded to 40 short lines.

## What is enforced, and what is prose

- **Hook-enforced:** the dispatch in step 2 is a Bash call, so the cloud guard
  (T-0009, while armed: the workflow's environment class) and
  promote-gate (T-0062: the declared deploy's `requires`, `rollback`,
  `requireHuman`, the clean tree at the sha) judge it like any deploy, and
  promote-gate holds the sha rule (L-0648): with `shaInput` set, the dispatch
  must give `-f <shaInput>=<sha>` exactly once, 40 lowercase hex, equal to the
  full HEAD of the tree it runs from - a substitution, a short or uppercase
  sha, a branch name, or another commit blocks. A
  `not-run` row never satisfies `requires`, and nothing `record` writes can be
  read as a pass row.
- **Helper-enforced, not a hook:** `prepare`'s refusals, `identify`'s
  never-guess rule, `watch`'s verdict from the run view (never the watch exit
  code) and `record`'s format. They hold only if the steps are run.
- **Prose only:** running the five steps in order, running watch again on 75,
  and not picking a run by hand when identify could not tell. Nothing stops a
  session that skips them, except that promote-gate still judges the dispatch.
