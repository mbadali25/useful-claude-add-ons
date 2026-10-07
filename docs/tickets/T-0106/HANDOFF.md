# Cloud handoff: T-0106

**`crew_autoclear_setup.py apply-migrate --scan-root` finds every repo with `autoClear.enabled` for the `onlyRepos` widening, and its notes name their file**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children). One of five siblings from the same report (T-0104, T-0105, T-0106, T-0107, T-0108); they share no files with this one.
- **INDEX status:** direction (first handed to cloud on 2026-09-30; spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0106-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0106/direction.md`, `docs/tickets/T-0106/spec.md`
- **Size:** about 120 added production lines, all in `plugin/crew/hooks/scripts/crew_autoclear_setup.py` (the walker about 60, the proposal and message about 25, the two refusals about 15, the CLI flags about 15, the note prefix about 5).
- **Harness:** no harness path. One feature PR; the tooling-PR rule does not apply.
- **Breaking change:** `apply-migrate --yes-widen` exits 1 instead of writing `onlyRepos: []`, and `apply-migrate` notes gain a file prefix. Both must be stated in the PR body and the CHANGELOG.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0088 | merged | Added the config-reader count in `plugin/crew/tests/test_worktree_config.py` (`crew_autoclear_setup.py` = 2) that the scan's new `.crew` join must keep true. |
| T-0006 | merged | Auto-clear and auto-resume, the feature `onlyRepos` narrows. |

Nothing open blocks this ticket and it blocks nothing. It can be worked at any time.

Related, no forced order:

- T-0105 (direction, handed to cloud): same `/crew:migrate` command, different file (`crew_migrate.py`). Whichever lands second re-bumps crew and merges `commands/migrate.md` if both edit it.
- T-0038 (approved): also edits `commands/migrate.md`. A text merge at most; re-check the 120-line budget (the file is at 111).
- T-0046 (in progress): BUDGETS.md bookkeeping. Until it lands, the BUDGETS.md count update is in scope here by standing rule.
- T-0048 (spec) and T-0054 (ready): if T-0048's configuration reference lands first, it also needs the `--scan-root` sentence.
- T-0096 (direction): does not touch this module.
- T-0104 (approved), T-0107 (done), T-0108 (direction): siblings, no shared files.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`). The spec gives the test: re-check the line numbers if `git diff --name-only 155fe6d8..origin/main -- plugin/crew/hooks/scripts/crew_autoclear_setup.py` prints the file. Re-check the anchors in the other files in any case.
- No plan.md is published. The implementing session writes the plan.
- `docs/handoff/cloud/T-0106.md` and its row in `docs/handoff/cloud/README.md` are on main from the first hand-off (2026-09-30). The spec is newer and wins where they differ. This ticket's PR deletes that file and its row.
- The report's line numbers at the top of direction.md are the reporter's at crew 1.0.59. Use the spec's.
- The scan is read-only and opt-in: no scan without `--scan-root`, no default roots, no write to any repo other than `--root`.
- An unreadable candidate is its own result. It is never counted as "not opted in", and it blocks `--yes-widen`.
- A repo that was already converted by an earlier `apply-migrate` has lost its `enabled: true` and cannot be found by any scan. The output and the docs must say so.
- Keep the function names `detect_onlyRepos_widening` and `apply_migrate_to_repo` and their positional parameters; new parameters are keyword-only with defaults that give today's behaviour.
- `plan-migrate` output must not change. New messages go into `check_no_forbidden_words`'s samples.
- The new tests build their repos under `tmp_path`; none reads a real config.
- `plugin/crew/commands/migrate.md` must stay at or under 120 lines.
- No edit to `plugin/crew/tests/sabotage*.py`; each new test is shown to fail by hand and reported in the PR body.
- The two "Owner decision 2026-09-30" sections in direction.md were written for local lanes. Merge, never rebase, still applies. The heavy-run wrapper they and the acceptance checks name is a local tool and is not in the repo; whether a cloud session needs an equivalent could not be told.

## Open questions for the owner (recommended option taken)

1. Default scan depth: 3 levels below each `--scan-root`, settable with `--scan-depth`. Alternative: unlimited depth with the same pruning.
2. `--yes-widen` with an empty proposal: refuse (exit 1, nothing written) instead of writing `onlyRepos: []`, which disarms every repo. This changes an existing flag's behaviour in one case. Alternative: keep the write and only reword the message.
3. `--yes-widen` when a scanned candidate could not be read: refuse, so a possibly opted-in repo is not silently left out. Alternative: write the readable ones and warn.
4. Repos already converted cannot be found by any scan. Taken: out of scope, stated in output and docs. Is a follow-up ticket wanted (recording opt-ins in the machine file during migration)?
5. Linked worktrees under a scan root are listed like any other directory when their own file carries the opt-in. Taken: accept, since the list is shown before anything is written.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0106/` in the final PR unless the owner wants it kept.
