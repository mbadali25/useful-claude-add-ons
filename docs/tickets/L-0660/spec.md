# L-0660: sabotage entries for goal resume (writers, handoff validation, discovery)          status: spec   risk: med
Split from T-0056 (2026-10-04). Written against origin/main `155fe6d8`. Tooling-only PR. Not buildable
until T-0056 and its children L-0658 and L-0659 have merged.

## Intent
Each fail-closed rule added by T-0056 and its children L-0658 and L-0659 gets a sabotage mutation that reintroduces
the bug and turns one named, existing test red. No production code changes. The mutations are added to the
lists the sabotage runner already imports, so the runner file itself is not edited.

## Exclusions
- No production code, command, skill or prompt edit. If a mutation shows a rule is untested, the missing
  test is added here (tests may ride along); a production fix is a new ticket.
- No edit to `plugin/crew/tests/sabotage.py`: it is at the module line limit, and the lists below are
  already imported by it.
- No crew version bump unless the gate requires one for a tests-only change; say which in the PR.
- No new mutation list name (it would need an import in `sabotage.py`).

## Evidence
origin/main `155fe6d8`:
- `plugin/crew/tests/sabotage*.py` is in `HARNESS` (`scripts/check-tooling-pr.py`); tests and docs may ride
  along, feature code may not.
- `plugin/crew/tests/sabotage.py` is 3400 lines, the limit (`.pylintrc:140`). It imports `RESUME_MUTATIONS`
  (`:76`) and `AUTOPILOT_MUTATIONS, POLICY_MUTATIONS` (`:77`).
- `AUTOPILOT_MUTATIONS` is defined at `plugin/crew/tests/sabotage_autopilot.py:28` and extended by
  concatenation at `:473`; the file is 1118 lines. `RESUME_MUTATIONS` is at `plugin/crew/tests/sabotage_resume.py:32`.
- The harness rule's suites run whenever a harness path changes (repo CLAUDE.md, "A change to the
  review/gate harness lands alone"): the tooling checker, `scripts/_test/tooling-pr.py`, the golden replay,
  the seam contracts and the canary review.

## Unknowns
- The exact anchor text of each mutation: taken from the merged code of T-0056 and L-0658 and L-0659.
  Each anchor must appear exactly once in its file, as the existing entries require.
- Whether `sabotage_autopilot.py` stays under the line limit after the additions (1118 now; about 150 added). Expected yes.
- Whether the whole sabotage run fits the host: run it through the heavy-run wrapper, serially.

## Size and split
No production lines. About 150 lines of mutation entries in two existing harness files. No parser, no
guard. No further split. `python3 scripts/check-tooling-pr.py` must print `tooling-pr: OK`.

## Touch
- `plugin/crew/tests/sabotage_autopilot.py`
- `plugin/crew/tests/sabotage_resume.py`
- `plugin/crew/tests/test_crew_autopilot_goal_resume.py` - only if a mutation finds an untested rule
- `plugin/crew/tests/test_crew_resume.py` - only if a mutation finds an untested rule
- `.crew/codemap/verification-harness.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`

Docs: none beyond the code map and CHANGELOG - no behaviour changes. The PR body says
`Docs: none - sabotage entries only` if the code map needs no edit either.

## Acceptance checks
Commands from the repo root, through the heavy-run wrapper on a memory-bound host.
- [ ] Each mutation below is registered and turns its named test red when run through
  `python3 plugin/crew/tests/sabotage.py` (the run reports every new entry RED and none "survived"):
  - (a) `handoff_resume` returns the ticket form when two goals are running;
  - (b) `handoff_resume` returns the ticket form when a goal file is unreadable;
  - (c) `running_goals` drops an unreadable file instead of listing it as unknown;
  - (d) `handoff_resume` emits the goal form for a `stopped` goal;
  - (e) `goal_mark` writes in place instead of temp file plus replace;
  - (f) the goal-handoff gate accepts a `stopped` goal (L-0658);
  - (g) the goal-handoff gate accepts a missing or unreadable goal file (L-0658);
  - (h) the branch and head check is skipped for a **ticket** handoff too (L-0658), in `crew_autopilot.py`;
  - (i) the same in `crew_resume.decide`, registered in `RESUME_MUTATIONS`;
  - (j) bare resume picks the first of two running goals instead of stopping (L-0659);
  - (k) bare resume treats an unreadable goal file as "no goal" and drives the active ticket (L-0659);
  - (l) bare resume resumes a `stopped` goal (L-0659).
- [ ] The harness's own checks still pass: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q`.
- [ ] Every anchor is present exactly once in its target file (the runner refuses otherwise; the run
  output shows no "anchor not found" or "anchor ambiguous" line).
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and
  `python3 scripts/_test/tooling-pr.py` passes.
- [ ] `python3 -m pylint plugin/crew/tests/sabotage_autopilot.py plugin/crew/tests/sabotage_resume.py`
  reports no new finding (both under `max-module-lines`).
- [ ] If the version is bumped: `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0056 (`ready`), L-0658, L-0659: must all have merged (or the PR states which
  mutations are deferred).
- T-0087 (the tooling-PR rule; on main).
- Blocks nothing.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
