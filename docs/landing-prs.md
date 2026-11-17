# Landing a pull request: bump and regenerate once, at merge time

A branch does not carry a version bump or a regenerated file while it is open. One
command, `scripts/land-pr.py`, writes both as a single commit when the PR is about to
merge. The owner then merges; the script never does.

## Why

Every open PR used to bump the plugin version and commit about a dozen generated files
(the README "What's new" block, the standards exports, `.claude/rules/`, the built
guides, the opt-in inventory, the `BUDGETS.md` line count, changelog re-bump lines). A
one-file fix touched thirteen files, and every PR conflicted with every other in exactly
those files. Each time `main` moved, a branch re-bumped, and
`scripts/check-changelog.py` then owed a `re-bump only` line for the number it replaced.

## While the PR is open

- **Keep it a draft.** On a draft, CI's `check-draft (version bump pending at land)` job
  reports version drift and a stale generated file as `pending at land` instead of
  failing. A ready PR, a push to `main` and a manual run take the full check.
- **Do not bump** `version` in `.claude-plugin/marketplace.json` or a `plugin.json`.
- **Do not commit regenerated files** for a change to something else. Edit the source
  (the guide Markdown, the standards, the code map); leave the outputs to the lander.
- **Write the changelog entry with `NEXT` for the number**, in either place:
  - a fragment, `changelog.d/<anything>.md`, holding one entry:
    `### Fixed — crew NEXT: <title>` and its bullets. Fragments never conflict with
    another PR's; the lander folds them into `CHANGELOG.md` and deletes them.
  - or directly under `## [Unreleased]` in `CHANGELOG.md`.

  Prose the PR adds may say `crew NEXT` too (a README paragraph, a guide). The lander
  replaces `<name> NEXT` with the real number on the Markdown lines the PR added, and
  nowhere else. A PR with no entry gets one written from its title.

What is pending on a draft: version drift and an out-of-date `BUDGETS.md` total
(`check-marketplace.py --pending-bump`), and a stale result from the guide build, the
configuration reference, the standards export, the README blocks and the
changelog-per-version check (`scripts/pending-at-land.py`).

What stays red on a draft: everything that is not staleness. A check that did not run
(exit 2), could not tell (exit 77), or failed for another reason still fails. So does
the opt-in inventory, which `plugin/crew/tests/test_optin_inventory.py` compares in the
pytest jobs; this relaxation does not reach it.

## Landing

```
python3 scripts/land-pr.py <PR>            # dry run: prints what it would change
python3 scripts/land-pr.py <PR> --push     # pushes the land commit to the PR branch
```

In a throwaway LF clone (never your worktree) it:

1. merges `origin/main` into the PR branch, as a merge commit. Conflicts are resolved only
   where the file is generated or the two sides differ in nothing but a version or a
   count; anything else stops the run and names the files for a person to merge;
2. sets the version of every plugin or skill the PR changes to one patch above `main`
   **and above every other open PR head**, in `marketplace.json`, `plugin.json` and the
   `<!-- claim: plugin-version:<name> -->` rows;
3. numbers the changelog entry and the PR's own prose, and writes one `re-bump only` line
   for each interim number a branch that bumped early already set;
4. runs the generators and re-measures `BUDGETS.md`;
5. commits, then runs the checks a ready PR faces (`check-marketplace.py` without
   `--pending-bump`, `check-changelog.py`, the freshness checks, `check-crew-docs.py`
   with the PR body, `check-tooling-pr.py`, `check_instructions.py`, pylint);
6. with `--push`, and only if every check passed, pushes with a plain `git push`.

Then mark the PR ready, wait for CI on the pushed head, and merge it
(`gh pr merge --merge`). Land one PR at a time: the next PR's number depends on the one
before it being on `main`.

It never merges the PR, never pushes to `main`, never force-pushes (a branch that moved
rejects the push), never marks a draft ready, and never runs `graphify update .`.

A second run on a landed PR changes nothing. If `main` moves after the land commit and
brings changes to the same plugin, run it again: it merges and re-bumps.

### Exit codes

| Exit | Meaning |
|---|---|
| 0 | Landed (`--push`), or a clean dry run. |
| 1 | A conflict needs a person, a generator or a check failed, or the push was rejected. |
| 2 | Refused, nothing changed: the PR is closed or from a fork, its head is `main`, its head moved, another open PR's version could not be read, or `main` moved before the push. |
| 3 | Could not tell: a check was skipped or did not run, or the guides' DOCX/PDF pass had no Word or LibreOffice. Nothing is pushed unless each such step is named with `--accept-skip`. A failed check is never accepted. |

### Options worth knowing

- `--trailer "Key: value"` (repeatable) adds trailer lines to the land commit, for
  example a `Docs: none - <why>` declaration or a session trailer.
- `--skip-check NAME` does not run a check; `--accept-skip NAME` pushes although a step
  gave no verdict. Both are reported as NOT VERIFIED.
- `--keep` keeps the scratch clone for inspection; `--report FILE` writes a JSON report.
- `--in-place DIR` lands in an existing clean checkout of the PR branch instead of a
  scratch clone. It refuses a dirty tree, another branch, `main`, and a checkout with
  `core.autocrlf` set (generated files there would not be the bytes CI compares).
- `--pr-json FILE` supplies the PR data on a host without `gh`.

## What it does not do

- It does not rebuild `graphify-out/`; a conflict there takes `main`'s copy.
- It does not rebuild DOCX and PDF without Word (Windows) or LibreOffice (Linux): that
  run ends with exit 3 and says so.
- It does not judge the changelog text or re-pin the README install URLs (CLAUDE.md,
  "Promotion").
- Between its last fetch and its push, another PR can take the same number. The next
  land of either PR corrects it; `check-marketplace.py` on the merged result is the gate.
- A harness PR still lands alone (`scripts/check-tooling-pr.py`); the lander runs that
  check, it does not relax it.

The suites: `python3 scripts/_test/land-pr.py` and
`python3 scripts/_test/pending-at-land.py`.
