# T-0045 crew runs GitHub Actions deployments          status: direction   risk: high   priority: high

## Problem
crew can decide whether `gh workflow run` is allowed (T-0009, approved, depends on T-0005), but it has no ability to carry out a GitHub Actions deploy. `/crew:promote` (`plugin/crew/commands/promote.md`) runs a deploy command from `.crew/verify.json`'s `environments` block. It cannot dispatch a workflow, identify the run that dispatch created (`gh workflow run` prints no run id), watch that run to completion, or report which job failed. autopilot stops after the merge (T-0011), so nothing deploys unattended.

## Decisions (owner, the owner, 2026-09-26)
- **Where:** extend `/crew:promote`. A verify.json environment gains a `github` deploy type (workflow, ref, inputs). Promote dispatches it, identifies the run it created, watches it with `gh run watch --exit-status`, and records pass or fail, with a failed job's log excerpt, in `.work/PROMOTIONS.md`. It reuses promote's requires, rollback and requireHuman.
- **Authority:** T-0009's rules. Listed nonProd workflows run unattended. Production stops for the owner's per-run yes unless `environments.prodUnattended` is true in both layers. A workflow crew cannot map to an environment is never run unattended.
- **Autopilot:** new `autopilot.deploy: none | nonprod`, default `none`. With `nonprod`, after T-0011 merges, autopilot promotes to the first nonProd environment, watches the run, and stops for the owner on any failure. It never deploys to production.
- **First real target:** another repository's deploy workflow (workflow_dispatch), nonProd only.
- **Priority:** high. The chain is T-0005 -> T-0009 -> T-0045.

## Recommendation
Identify the run by dispatching with a correlation input when the workflow accepts one. Otherwise take the newest `workflow_dispatch` run for that workflow, on that ref, by this actor, created after the dispatch timestamp. More than one candidate, or none within a timeout, is could-not-tell: stop, never guess. Watch with `gh run watch <id> --exit-status`. On failure, `gh run view <id> --log-failed` gives the excerpt. The environment comes from T-0005/T-0009's layer, never from reading workflow YAML.

## Open questions (resolve at spec)
- Does the first target's deploy workflow accept an input that can carry a correlation id? If not, is adding one to that repository in scope? Owner's call; the default is no and the timestamp rule applies.
- Rollback for a GitHub deploy: re-dispatch the previous good sha, or a separate rollback workflow? Read that repository's workflow and promote's rollback contract.
- How long to watch before `unknown` (runs can queue behind concurrency groups).

## Depends on
T-0005 (environment layer), T-0009 (the `gh workflow run` guard), T-0011 (ship, for the autopilot hook only).

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
Checked against origin/main `155fe6d8` (crew 1.0.322, `plugin/crew/.claude-plugin/plugin.json:3`). The owner was not available; every question below took the recommended option and is listed again under "Open questions for the owner".

**Still true.** The problem is real and nothing on main fixes it.
- `/crew:promote` gate 2 is one sentence, "Run the `deploy` commands" (`plugin/crew/commands/promote.md:69`). Nothing dispatches a workflow, finds the run, watches it or records it: `git grep -n ghdeploy origin/main -- plugin scripts` prints nothing.
- Autopilot still deploys nothing. `crew_autopilot.settings` warns that `autopilot.deploy` is inert and names this ticket as the consumer (`plugin/crew/hooks/scripts/crew_autopilot.py:809-812`); the consumer contract is written down at `:137-140`.
- The owner's four decisions of 2026-09-26 stand: extend `/crew:promote`; authority is T-0009's; autopilot is opt-in and never production by this ticket's own doing; could-not-tell stops.

**What changed since the direction was written.**
- T-0072 merged (PR #250). `autopilot.deploy` already exists with the values `none | nonprod | all` (`plugin/crew/hooks/scripts/crew_state.py:1134`, `crew_autopilot.py:162`), and `deploy_allowed` answers `allow | ask | refuse` per environment (`crew_autopilot.py:957`). So this ticket no longer adds the key, its default, its template rows or its config tests. It consumes `deploy_allowed`. Under `all`, T-0072's policy can allow production; this ticket's autopilot slice still proceeds only on the exact verdict `allow`.
- T-0005 merged. The environment layer (`environments.nonProd`, `environments.prodUnattended`) is on main (`plugin/crew/templates/config.template.json:199-202`).
- T-0505 merged (PR #296). promote-gate now judges the tree the deploy runs from, and a literal sha in the command must be that tree's HEAD (`plugin/crew/hooks/scripts/promote-gate.sh:19-26`, `:376-384`). The false block that the first consumer repository hit is fixed. The 2026-09-26 decision "a github deploy skips the local dirty check and requires the sha on origin instead" is superseded: main keeps the clean-tree check for every deploy, on the right tree. The sha-on-remote check stays, in the helper's `prepare`.
- T-0062 (ready) now owns two things the old spec carried: promote-gate recognising the `gh api ... /dispatches` form through T-0009's parser, and the first-row `passed()` behaviour. Both are removed from this ticket.
- T-0009 is not on main. PR #336 is open at `f08ae7fb`, round 6 accepted by the owner, landing. `deployWorkflow` appears on main only in golden review output. Its classifier is `crew_guards.dispatch_scopes` and `crew_guards.dispatch_environment` on that branch.
- T-0011 is still `approved` and unbuilt on main; `origin/T-0011-build` is at crew 1.0.42 and far behind.
- The tooling-PR rule (T-0087) landed: `plugin/crew/tests/sabotage*.py` is harness (`scripts/check-tooling-pr.py:79`) and cannot ride in a feature PR. `plugin/crew/tests/sabotage.py` is at the 3400-line pylint limit. T-0505 set the pattern: mutations ship in an unwired `*_mutations.py` file and a tooling PR wires them (`plugin/crew/tests/promote_tree_mutations.py:1-10`).
- `promote.md` is 380 lines against an allowance of 380 (`plugin/crew/.budget-allowance.json`), and `autopilot.md` is 109 against a tested cap of 110 (`plugin/crew/tests/test_lifecycle_commands.py:112-119`). Neither has room for the github sequence.

**Options.**
1. **Keep the 2026-09-26 design, cut into eight small landings (recommended).** The read-only helper `crew_ghdeploy.py` lands one subcommand at a time (`check`, `prepare`, `identify`, `watch`, `record`), then the promote-gate entry rule, then the autopilot phase, then a tooling-only PR that wires the mutations. Each landing holds one parser, guard or fail-closed state machine and stays under 300 production lines. The first four need nothing unmerged except T-0009 for `prepare`.
2. Wait for T-0009 and T-0011, then build it as one PR, as plan.md describes. About 950 production lines, three state machines, a guard change in two flavours and harness files in one review. The split rule and the tooling-PR rule both refuse it.
3. Drop the helper and keep the sequence as prose in promote.md. No code to review, but "which run did my dispatch create" stays a guess, which is the failure the direction exists to remove.

**Recommendation: option 1.** T-0045 itself becomes the first slice: the `github` entry in `.crew/verify.json` and `crew_ghdeploy.py check`. The rest are L-0644 to L-0650 under `children/`.

**Open questions for the owner** (defaults taken as shown)
- Is cutting T-0045 into eight landings acceptable? Default: yes.
- Should L-0648 (promote-gate reads the `github` entry) be folded into T-0062, which changes the same two files? Default: keep it separate and land it after T-0062.
- `promote.md` is at its 380-line allowance. Default: the github sequence goes in a new sibling file of the crew-verification skill, and promote.md gains a pointer by rewording existing lines with no net growth. The alternative is raising the allowance, as the owner did for T-0505.
- T-0072's `autopilot.deploy: all` can allow production. The 2026-09-26 direction says autopilot never deploys to production. Default: L-0649 follows `deploy_allowed` exactly, so production runs only under T-0072's two-layer opt-in.
- The pre-existing text of this file and of plan.md names the first consumer repository, its local path and its workflow's inputs. The repository is public. Default: left untouched here (this pass only appends); they need scrubbing before these files are published.
- Carried from 2026-09-26, defaults unchanged: no correlation input is added to the consumer repository; rollback is not automated; `watchMinutes` 60 and `identifySeconds` 120.
