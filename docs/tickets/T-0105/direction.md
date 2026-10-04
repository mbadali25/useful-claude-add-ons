# T-0105 direction - crew migrate (plugin/crew/hooks/scripts/crew_migrate.py)

Status: seed (not yet approved; the Brainstorm phase settles it under the owner's standing authority).

## Ask
the owner, 2026-09-29 ~05:15 CDT, verbatim: "@<another-session> reporting gizmo duck plugin issues please take that, and address them at the same time as this , put them in a workflow brainstorm -> spec -> approve -> implement -> fix -> gate -> land"

## Report (verbatim, from a session in another repository (crew 1.0.59, gizmoduck 0.5.3), found 2026-09-28/29, relayed cross-session 2026-09-29 ~05:10 CDT; its line numbers are the reporter's at crew 1.0.59 / gizmoduck 0.5.3 - re-verify against origin/main)
6. crew_migrate.py carried config key `autopilot` ({"mode":"off","maxPhases":12,"deploy":"none"}) into crew.json `unmapped.autopilot`, although 1.0 has a top-level autopilot key - a user who later edits it there gets no effect.

## Notes
- Every claim above is the reporter's; Brainstorm verifies each against the code before designing.
- Siblings from the same report: T-0104 (items 1-5), T-0105 (6), T-0106 (7), T-0107 (8, 12), T-0108 (9-11).

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
Checked against origin/main `155fe6d8` (crew 1.0.322). Owner not available; the recommended option is taken and the questions are listed in spec.md.

**Still true.** The reported behaviour is on main, unchanged since crew 1.0.41 (`git log origin/main -- plugin/crew/hooks/scripts/crew_migrate.py` ends at `ecf69e43`; no commit on origin/main names T-0105).
- `MAPPING` (`plugin/crew/hooks/scripts/crew_migrate.py:90-117`) has no `autopilot` row, so `to_crew` (`:286-288`) carries the key under `unmapped.autopilot` and `render_plan` (`:537-538`) prints `unmapped  config key 'autopilot' carried under crew.json unmapped.autopilot`.
- Measured with origin/main's module on `{"schema": 7, "tracker": "files", "autopilot": {"mode": "off", "maxPhases": 12, "deploy": "none"}}`: crew.json holds `"unmapped": {"autopilot": {...}}`.

**What the report got wrong.** "1.0 has a top-level autopilot key" is true of `.crew/config.json`, not of `.crew/crew.json`. Crew reads `autopilot` from `.crew/config.json` only (`plugin/crew/hooks/scripts/crew_autopilot.py:791`, `plugin/crew/CONFIG.md:2610-2616`). An `autopilot` block in crew.json is never read; `settings` warns about it only when it is top-level and config.json has none (`crew_autopilot.py:814-818`). So moving the key to top-level alone does not make an edit in crew.json take effect. Measured, origin/main's `crew_autopilot.settings` in a throwaway directory:

| crew.json shape | config.json | crew.json warning |
|---|---|---|
| `unmapped.autopilot` | kept | no |
| `unmapped.autopilot` | removed | no (autopilot silently reads `off`) |
| top-level `autopilot` | kept | no |
| top-level `autopilot` | removed | yes ("move it to .crew/config.json") |

**What changed since the seed.** `autopilot` gained `approval` and `questions` (T-0010) and `deploy` (T-0072); all are read from config.json the same way. Seven other live 1.0 keys land under `unmapped` for the same reason (`resume`, `shellRoute`, `cloud`, `environments`, `scope`, `tickets`, `route`; measured by passing `crew_config.default_config()` through `to_crew`). T-0038 (approved, not started) also edits `crew_migrate.py`.

**Options.**
1. **Recommended, taken: map and say which file is read.** Add the row `autopilot -> autopilot`, so the key stops being reported as unmapped and the existing `settings` warning fires once config.json is retired. Add a migrate note, in the report and in crew.json `notes`, saying crew reads this key from `.crew/config.json` and the crew.json copy is not read. About 12 production lines, one file.
2. Map only, no note. Matches the ticket title, but the user who edits crew.json still gets no effect and no word while config.json exists. Rejected: it does not fix the reported harm.
3. Make crew read `autopilot` from crew.json. Rejected here: it changes which file arms a driver, touches `crew_autopilot.py` and the approval policy path, and belongs to the wider two-file question (`.crew/codemap/crew.md:527-542`).
4. Map all eight live keys. Rejected for this ticket: each sibling has its own reader rules (`resume.auto` is read from both repo files for a veto, `plugin/crew/CONFIG.md:1132-1142`), so each needs its own check. Listed as an open question.

**Split.** The feature is far under the size rule. Sabotage rows live in `plugin/crew/tests/sabotage_migrate.py`, a review/gate harness path (`scripts/check-tooling-pr.py:79`), so they are a separate tooling-only PR: `children/1`.
