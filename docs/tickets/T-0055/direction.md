# T-0055 direction          status: ready   risk: med

## Ask
Owner (the owner, 2026-09-26): "Please make some kind of rule or note that every time we make
changes to the crew plugin, all documentation needs to be updated." Then: "Maybe that's a GitHub
action. I don't know."

The rule itself is in `CLAUDE.md` ("Scope discipline", 2026-09-26). This ticket makes CI enforce it.

## What exists
- `.github/workflows/marketplace.yml` already runs `scripts/check-marketplace.py` on every push and
  PR, so a new check there needs no new workflow.
- Freshness checks already exist for some docs: claim markers (`check_self_claims`) and codemap
  anchors (`crew_freshness.py`). T-0048 adds `build.py --check` for the guides and a generated
  config block in `CONFIG.md`. CI cannot import `markdown` today (`.pylintrc:59-64`, per T-0048).

## Options
1. **Two checks in the existing gate (recommended).**
   - (a) **Docs-touched-or-declared:** a PR whose diff changes non-doc files under `plugin/crew/`
     must also change at least one file in the doc set named in CLAUDE.md, or carry a
     `Docs: none - <reason>` line in its PR body or a commit trailer. An empty reason fails.
   - (b) **Docs-fresh:** the guides' built outputs match their sources, using T-0048's
     `build.py --check`. The workflow installs `markdown` for that one step.

   (a) forces a decision and (b) catches stale output. Neither can prove the prose is right; review
   still judges that.
2. **A separate GitHub Action that comments on the PR with the doc files it expects.** Friendlier,
   but advisory. The rule is "must", and a comment does not block a merge.
3. **Rely on `/crew:docs` in `/crew:implement` plus review.** No new code, but that is how docs have
   drifted so far: T-0048 found `CONFIG.md` stating 44 global keys where the code has 66.

## Recommendation
Option 1. It blocks in CI, where autopilot merges are gated (T-0011 merges only on green checks), so
the rule holds even when no human reads the PR. It needs a must-fail / must-pass suite in
`scripts/_test/`, sabotage-tested per the repo's guard rule.

## Open questions (recommendation applies)
- Which paths count as "non-doc" under `plugin/crew/`: `hooks/`, `commands/`, `skills/`, `agents/`
  and `templates/`, excluding tests and `.md` files that are themselves docs? Recommendation: code
  and templates only, since a `commands/*.md` edit is already a doc edit.
- Where the declaration lives: PR body (needs `gh`/event payload in CI) or commit trailer (works
  locally too). Recommendation: accept either; check the trailer locally and both in CI.

## Depends on
T-0048 for (b). (a) can land first.

## Approval
Direction approved under the owner's standing authorization (2026-09-26).

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
the owner, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
the owner, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); <local-tmp>/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.

## Direction check 2026-10-04
Checked against origin/main `155fe6d8`.

Still true:
- Nothing on main enforces the rule. `git grep -n -i "Docs: none" origin/main -- scripts .github plugin/crew/commands plugin/crew/hooks` prints nothing; the only mention is `.crew/standards.md:118-119`. No commit on origin/main mentions T-0055.
- The drift is real. Of the last 60 first-parent merges on origin/main, 31 changed code under `plugin/crew/` (not `.md`, not tests, not `plugin.json`). 4 of those 31 changed no narrative doc (#380, #328, #317, #302), and none of the four PR bodies has a `Docs:` line (`gh pr view <n> --json body`).
- `.github/workflows/marketplace.yml` still runs on every pull request with `fetch-depth: 0`, so a new step there needs no new workflow.
- `docs/guides/crew/src/build.py` still has no `--check` (`:245-262`), and T-0048 is still at `spec`. Part (b), docs-fresh, stays blocked on it.

Changed since the direction was written:
- **The rule's paragraph is not on origin/main.** `CLAUDE.md` "Scope discipline" on main (`:24-29`) goes from the registration rule straight to the claim-marker rule. The paragraph "A change to `plugin/crew/` updates every document that describes it" exists only as an uncommitted edit in one local checkout (`git log origin/main -S"updates every document" -- CLAUDE.md` prints nothing). `.crew/standards.md:118-119` points at a list main does not have. This ticket now commits the paragraph.
- **"At least one file in the doc set" is too weak as written.** All 31 measured PRs changed `plugin/PLUGINS.md` and `CHANGELOG.md` (the version bump), and most changed `.crew/codemap/` and `docs/diagrams/` (re-anchoring). If those count, the check passes every PR and checks nothing. The counting set has to be the narrative docs only.
- `scripts/check-tooling-pr.py` (T-0087, merged) is now the model for a branch-diff check with a commit trailer: merge-base diff, `crew_ticket.path_matches`, exit 77 for a missing ref. It did not exist when option 1 said "in `check-marketplace.py`".
- `scripts/gate-runner.py --check-ci` now fails when a workflow `run:` line is missing from its step table, so a new CI step also needs a table entry.
- The Stop-time verify gate runs rules on changed paths while work is in progress. A docs-touched rule there would block every stop before the docs step is reached.

Recommended option: option 1, with these adjustments.
- Part (a) is this ticket: a new `scripts/check-crew-docs.py` beside `check-tooling-pr.py`, not a function inside `check-marketplace.py`. It runs in CI and in `gate-runner.py`, and not as a Stop-gate rule.
- The counting set is narrative docs only. Version, changelog, budget, code map and diagram files neither trigger nor satisfy the check.
- The declaration is accepted as a commit trailer (works locally and in CI) or a PR-body line (CI only).
- Part (b) is split out as L-0657, blocked on T-0048.

## Open questions for the owner (default taken in each)
1. Should a code map or diagram edit count as "docs touched"? Default: no, because re-anchoring changes them in nearly every crew PR. A PR whose only real doc change is code map prose declares `Docs: none - <reason>` naming that.
2. Should editing the PR body re-run the check? GitHub does not re-run on a body edit, and a manual re-run reuses the old event payload. Default: leave the workflow's triggers alone; a declaration added after the run goes in a commit trailer (an empty commit is enough). The alternative is adding `edited` to `pull_request.types`, which re-runs the whole Marketplace workflow on every body edit.
3. Should the check also run at Stop through `.crew/verify.json`? Default: no (see above). It runs in CI and in the pre-push `gate-runner.py` run.
4. Should prompt files (`commands/*.md`, `agents/*.md`, `SKILL.md`) trigger the check when they change alone? Default: no; they are themselves in the doc set, as the original direction said.
5. Should the sabotage rows for the new checker also be registered in `plugin/crew/tests/sabotage_tooling.py`? Default: no. That file is review/gate harness, so it would need its own tooling-only PR. The suite carries its own mutation cases instead.
