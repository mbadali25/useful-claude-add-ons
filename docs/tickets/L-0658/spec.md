# L-0658: a `--goal` handoff is checked against the goal file, not the branch and head          status: spec   risk: high
Split from T-0056 (2026-10-04). Written against origin/main `155fe6d8`. Not buildable until T-0056 and
L-0541 have merged; re-find every line by content then.

## Intent
A handoff whose `resume:` line is `/crew:autopilot --goal <slug>` is accepted or refused by reading the
goal file: usable when the file is readable and its run state is `running`. Its `branch:` and `head:` lines
are not compared, because a goal moves across ticket branches. A ticket-form handoff is checked exactly as
today. This closes the case where a goal handoff written on one ticket's branch is discarded after the
next ticket's branch is checked out.

## Exclusions
- No change to the ticket form: its `branch:`, `head:` and folder checks stay, in all three sites.
- No change to the grammar, allowlist, author record, consumed-once rule, loop guard, manual-`/compact`
  rule or the armed setting in `crew_resume.py`. Only the two branch/head comparisons gain a goal branch.
- No goal discovery without a handoff (L-0659). No writer changes (T-0056).
- No resuming of a `stopped` goal: it is named with its reason. A human stop is never passed silently.
- No edit to `plugin/crew/tests/sabotage*.py` (L-0660).
- No new config key.

## Evidence
origin/main `155fe6d8`:
- `_handoff_ticket`: goal stop `plugin/crew/hooks/scripts/crew_autopilot.py:645-647`; branch and head
  comparison `:650-661`; folder check `:662-663`. L-0541 replaces the goal stop; the comparison below it
  is what this ticket routes around for `kind == "goal"`.
- Status's `_resume_line`: goal "not usable" `:1500-1501`; branch and head `:1507-1513`. It repeats
  `_handoff_ticket`'s checks on its own read of the file (comment at `:1502-1504`), so both move together.
- `crew_resume.decide`: branch `plugin/crew/hooks/scripts/crew_resume.py:694-697`, head `:698-701`,
  both before the goal-file existence check `:706-707`. Every "cannot tell" returns `wait` (`:671-673`).
- The handoff regexes are `crew_state._HANDOFF_BRANCH_RE` / `_HANDOFF_HEAD_RE`
  (`plugin/crew/hooks/scripts/crew_state.py:663-664`); unchanged.
- The goal file is already in the progress fingerprint (`crew_resume.py:525-529`), so a resume that made
  no progress is still caught by the loop guard.
- Docs that state the rule: `plugin/crew/commands/autopilot.md:48-49`; `plugin/crew/README.md:913` and
  `:2109-2112`; `plugin/crew/CONFIG.md:1158-1160`; `docs/guides/crew/src/auto-cycle.md:41-43`;
  `.crew/codemap/crew.md:687`.
- From T-0056 (not on main): `running_goals(root)` and the goal file's `run.state`.

## Unknowns
- L-0541's shape of the goal branch in `_handoff_ticket` and `resume_target`. Resolved before plan by
  reading it on main.
- `crew_resume.py` must not import `crew_autopilot.py` if that makes a cycle (`crew_autopilot` imports
  `crew_resume` lazily at `:634`). Resolved at plan: either a lazy import the same way, or the small
  run-state reader lives in a module both can import. State which in the plan.
- Whether the owner wants auto-typing for a cross-branch goal handoff (direction.md). Default: yes.
- The next free crew patch version is set at implement time.

## Size and split
About 80 added production lines (`crew_autopilot.py` about 45, `crew_resume.py` about 35). One fail-closed
check (the goal-state gate), applied at three call sites through one helper. No harness path. No further split.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/crew_resume.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/skills/crew-context/SKILL.md`
- `plugin/crew/tests/test_crew_autopilot_goal_resume.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_crew_resume.py`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `docs/guides/crew/src/auto-cycle.md`
- `docs/guides/crew/**` - the HTML, DOCX and PDF rebuilt by docs/guides/crew/src/build.py
- `.crew/codemap/crew.md`
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`

Not in Touch: `.crew/verify.json` (the rules at `:336-359` already map these files, once T-0056 has added
its test file); `docs/diagrams/` (no box or edge changes).

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
- [ ] Must-allow: a goal handoff whose `branch:` and `head:` differ from the checkout, with a readable goal
  file in state `running`, is taken by `resume_target` (source `handoff`) and resumes at the goal's next
  ticket. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_goal_resume.py -q -k test_goal_handoff_survives_a_branch_switch`
- [ ] Must-allow: the same handoff, read by `crew_resume.decide` with every other condition met, returns
  `run` with the goal prompt. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_resume.py -q -k test_decide_runs_a_goal_handoff_across_branches`
- [ ] Must-block, one test each, in both `resume_target` and `decide` (`decide` answers `wait`, never `run`):
  - the goal file is missing;
  - the goal file is unreadable or not JSON (reason says "could not read", not "no goal");
  - run state `done`;
  - run state `stopped` (the reason carries the recorded stop reason and the `--goal` command);
  - a `run` block with an unlisted state;
  - a goal file with no `run` block.
- [ ] Must-block: a **ticket** handoff with a different branch or head is still refused, in all three
  sites. `-k "ticket_handoff_branch"` in `test_crew_autopilot.py`-style tests and `test_crew_resume.py`
- [ ] Must-block: for a goal handoff, `decide` still waits on each of: another session's author record,
  an already-consumed handoff, an unchanged progress fingerprint, an unarmed setting, a non-manual compact.
  Parametrised, `-k test_goal_handoff_keeps_every_other_resume_condition`
- [ ] Status: `crew_autopilot.py status` shows `resume: /crew:autopilot --goal <slug> (usable)` for the
  must-allow case and a fixed "not usable" reason for each must-block case, with nothing echoed from the
  file. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_status.py -q -k goal`
- [ ] The owner's scenario, part (b): goal at ticket 2 of 3, handoff written, ticket 3's branch checked
  out, resume continues the goal. `-k test_goal_resumes_after_switching_to_the_next_ticket_branch`
- [ ] Existing suites pass unchanged:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_resume.py plugin/crew/tests/test_crew_resume_hook.py plugin/crew/tests/test_auto_cycle.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Docs: each place listed under Evidence says the branch and head rule applies to the ticket form, and
  that a goal handoff is judged by the goal file. Guide outputs rebuilt
  (`python3 docs/guides/crew/src/build.py`). Crew bumped to the next free patch with a CHANGELOG entry;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Dependencies
- T-0056 (`ready`): `running_goals` and the `run` block. Must land first.
- L-0541 (`direction`): the `--goal` branch of `resume_target`. Must land first.
- T-0012 (`approved`), T-0006 (`merged`), T-0004 (`merged`).
- Blocks: L-0660 (its mutations).

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
