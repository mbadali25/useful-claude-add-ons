# T-0056 a running autopilot goal is written into every handoff: goal run state and `handoff_resume`          status: spec   risk: high
## Refreshed 2026-10-04
First spec for this ticket (there was only direction.md, and no plan.md). Written against origin/main
`155fe6d8` (crew 1.0.322); see direction.md "Direction check 2026-10-04".

- **Narrowed.** The INDEX title covers three gaps. This spec is the first slice: the goal file records
  whether a goal is running, and every handoff writer that exists on main asks one function for the
  `resume:` line. The other two gaps and the sabotage entries are L-0658, 2 and 3 (`children/`).
- **Not buildable yet.** There is no goal file on main. T-0012 and L-0541 land first (see Dependencies).
  Every name below that belongs to them is marked, and is re-found by content before planning.
- **Renamed.** direction.md calls the function `crew_autopilot.resume_line()`. `_resume_line` already
  exists with another meaning (`crew_autopilot.py:1478`), so it is `handoff_resume` here.

## Intent
While an autopilot goal is running in this checkout, a handoff written for any reason names the goal
(`resume: /crew:autopilot --goal <slug>`), not the one ticket in hand, so a resume after `/clear` continues
the goal instead of stopping when that ticket closes. The goal file `.work/autopilot/<slug>.json` records the
run state (`running`, `stopped`, `done`) and the current ticket, written atomically at every phase boundary.
One function, `crew_autopilot.handoff_resume`, reads it and is the only place that decides the line. When
it cannot tell which goal is running, it says so and writes `resume: none`: never the ticket form.

## Exclusions
- No change to how a `--goal` handoff is **read**. The `branch:`/`head:` checks in `_handoff_ticket`,
  `_resume_line` and `crew_resume.decide` are unchanged here: L-0658.
- No goal discovery on a bare `/crew:autopilot`: L-0659. `resume_target` is not edited here.
- No edit to `plugin/crew/tests/sabotage*.py` (harness; `scripts/check-tooling-pr.py`): L-0660.
- No change to the `resume:` grammar, the allowlist, `parse_resume` or `render` in `crew_resume.py`.
  `handoff_resume` renders through `crew_resume.render`, so there is still one definition of the line.
- No change to T-0012's proposal, split approval or minting, or to L-0541's picker and caps. This ticket
  adds one block (`run`) to the goal file and one writer for it.
- No wiring of T-0017's wrap-up writer: it is not on main. Whichever lands second wires it.
- The PreCompact skeleton is unchanged when no goal is running, when python is missing, or when the
  answer is anything but one exact goal line. It never gains a ticket-form `resume:` line here.
- No new config key, no new hook, no new hook registration.
- No resuming of a `stopped` or `done` goal by any writer: only `running` produces the goal line.

## Evidence
All at origin/main `155fe6d8`, read 2026-10-04.
- No goal support yet: `SUBCOMMANDS`/`AVAILABLE`/`ARRIVES`/`GOAL_FLAG` `plugin/crew/hooks/scripts/crew_autopilot.py:224-227`;
  `route` stops `--goal` `:1311-1313`; `_handoff_ticket` stops a goal handoff `:645-647`; status reads
  it as "not usable" `:1500-1501`. The module docstring states the order and "`--goal` stops until T-0012" `:104-111`.
- The low-context writer is prose: `plugin/crew/commands/autopilot.md:104-109` ("run `/crew:handoff` with
  `resume: /crew:autopilot <ticket>`"). The file is 109 lines and has a line budget in `plugin/crew/BUDGETS.md`.
- `/crew:handoff` step 5 writes `resume:` from the allowlist, with the Write tool so the note has an author
  record: `plugin/crew/commands/handoff.md:17-23`.
- The grammar's prose home: `plugin/crew/skills/crew-context/SKILL.md:96-106` (`--goal <slug>` is already listed).
- The PreCompact skeleton writes `branch:` and `head:` and no `resume:` line, and only when no handoff
  exists: `plugin/crew/hooks/scripts/handoff-write.sh:87-109`, `handoff-write.ps1:385-415`. The two are a
  matched pair; both resolve python (`crew_py`, `Resolve-CrewPython`) and already call
  `crew_resume.py precompact` (`handoff-write.sh:59`, `handoff-write.ps1:336-341`).
- The reading side already takes the goal form: `_GOAL_SLUG_RE` `plugin/crew/hooks/scripts/crew_resume.py:85`;
  `parse_resume` `:126-133`; `render` `:148-149`; goal-file existence `:706-707`; the goal file is part of
  the progress fingerprint `:525-529`, so a `run` block that changes at each phase boundary also moves it.
- CLI shape to extend: `main` builds its subparsers from a name tuple at `crew_autopilot.py:1668-1683`.
  "Exit 0 always, the answer is in the output; a crash is `stop=1`, never silence" `:120-122`.
- Unreadable-is-unknown precedent: `_read_handoff` `:608-625` (`HANDOFF_ABSENT` against `HANDOFF_UNREADABLE` `:604-605`);
  `_read_json` `:729`.
- Module size: `crew_autopilot.py` is 1768 lines, limit 3400 (`.pylintrc:140`). `plugin/crew/tests/sabotage.py` is at 3400.
- Verification map: autopilot rule `.crew/verify.json:348-359`; resume and handoff-write rule `:336-347`.
- Harness and seam lists: `scripts/check-tooling-pr.py` `HARNESS` (holds `plugin/crew/tests/sabotage*.py`,
  `crew_ticket.py`, `scope_guard.py`) and `SEAM` (holds `crew_autopilot.py`, `crew_resume.py`, `autopilot.md`).
- Not on main, from the tickets (re-find after they land): goal file schema 1 "goal, slug, proposal with
  `done_condition`, tickets with `depends_on` and risk, approval, caps, runs" (`.work/tickets/T-0012/spec.md`
  Acceptance checks); `next_goal_ticket(root, slug)` and the `--goal` branch of `resume_target`
  (`.work/tickets/L-0541/direction.md`, quoted Step 3).

## Unknowns
- **The goal file's real shape and its writer.** Resolved before plan: read T-0012's and L-0541's merged
  code. If either already writes a run state or a current ticket, this ticket reuses that field and adds
  only what is missing; it does not add a second one. If the schema number must move, say so in the plan.
- **Where the phase boundary is.** `goal-mark` is called from `autopilot.md`'s loop as L-0541 leaves it.
  Resolved at plan by reading that section. If L-0541 drives the loop from python, the call moves there
  and the command text does not change.
- **"Running here".** `.work/` belongs to one worktree, so a goal file under this checkout's
  `.work/autopilot/` is this checkout's goal. Accepted as the definition; no session id is recorded.
- **A goal file with no `run` block** (proposed, not yet started) reads as not running. A `run` block that
  is present and malformed reads as unknown. Accepted.
- **PowerShell leg.** The `.ps1` change is tested only where `pwsh` is installed; on a host without it the
  test skips and the report must say so. A native Windows run is asked for before merge.
- **Two writers at once.** `goal-mark` is temp file plus `os.replace` in the same directory. Two sessions
  driving one goal in one worktree is not supported and not detected here. Accepted as risk.
- **T-0017 order.** See Exclusions. Open question for the owner in direction.md.
- The next free crew patch version is set at implement time.

## Size and split
- This slice: about 170 added production lines. `crew_autopilot.py` about 135 (`goal_mark`, `running_goals`,
  `handoff_resume`, two CLI names), `handoff-write.sh` about 15, `handoff-write.ps1` about 20. Under 300.
- It holds one fail-closed reader (`running_goals`, feeding `handoff_resume`). No second one.
- The whole of direction Option 1 is about 360 production lines with three fail-closed pieces, and its
  sabotage entries are harness paths. So it is split:
  1. **T-0056 (this spec)**: writers. Gap 1.
  2. **L-0658** (`children/1/`): a `--goal` handoff is checked against the goal file. Gap 2. About 80 lines.
  3. **L-0659** (`children/2/`): bare resume finds running goals. Gap 3. About 110 lines.
  4. **L-0660** (`children/3/`): sabotage mutations for the three. Tooling-only PR, no production lines.
- Harness rule: nothing in this slice's Touch is in `HARNESS`. `python3 scripts/check-tooling-pr.py` must
  print `tooling-pr: OK`.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/hooks/scripts/handoff-write.sh`
- `plugin/crew/hooks/scripts/handoff-write.ps1`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/commands/handoff.md`
- `plugin/crew/skills/crew-context/SKILL.md`
- `plugin/crew/tests/test_crew_autopilot_goal_resume.py` - new
- `plugin/crew/tests/test_crew_resume_hook.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `.crew/verify.json`
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

Not in Touch, stated: `plugin/crew/hooks/scripts/crew_resume.py` (read side, L-0658);
`plugin/crew/tests/sabotage*.py` (L-0660); `docs/diagrams/` (no box or edge changes; a regenerated anchor
is a refresh artifact); the autopilot guide (T-0054, not written yet: it takes this as a worked example).

## Acceptance checks
Commands run from the repo root. On a memory-bound host each pytest command goes through the repo's
heavy-run wrapper. `T` below is `plugin/crew/tests/test_crew_autopilot_goal_resume.py`.
- [ ] `goal_mark(root, slug, state, ticket=None, reason="")` writes the goal file's `run` block
  (`state`, `ticket`, `reason`, `at`) through a temp file in the same directory and `os.replace`. A state
  outside `running|stopped|done`, a slug outside T-0006's grammar, or a goal file that is missing or not a
  JSON object is refused and nothing is written. Every other key of the file is byte-for-byte preserved.
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "goal_mark"`
- [ ] A write that fails part-way leaves the old file intact (test: `os.replace` raising leaves the
  previous content and no temp file behind). `-k test_goal_mark_failed_replace_keeps_the_old_file`
- [ ] `running_goals(root)` returns `running`, `stopped`, `done` and `unknown` lists. No `.work/autopilot/`
  directory is empty lists. A file that cannot be read, is not JSON, is not an object, or has a `run` block
  with a missing or unlisted `state` is in `unknown`, never dropped and never `done`. A file with no `run`
  block is in none of the lists. `-k "running_goals"`
- [ ] `handoff_resume(root, ticket=None)` returns `{"line", "kind", "reason"}`:
  - exactly one running goal and no unknown: `resume: /crew:autopilot --goal <slug>`, `kind=goal`, even
    when `ticket` is given;
  - no running goal and no unknown, a `ticket` that has a folder: `resume: /crew:autopilot <ticket>`, `kind=ticket`;
  - no running goal, no unknown, no ticket: `resume: none`, `kind=none`;
  - two running goals: `resume: none`, `kind=unknown`, reason names both slugs;
  - any unknown goal file, with or without a running one: `resume: none`, `kind=unknown`, reason names the file;
  - a `stopped` or `done` goal alone: the ticket form or `none`, never the goal form.
  One parametrised test, `-k test_handoff_resume_cases`
- [ ] Every line `handoff_resume` returns round-trips: `crew_resume.parse_resume` accepts it (or refuses
  `resume: none` with its fixed reason) and `crew_resume.render` gives back the same command.
  `-k test_handoff_resume_line_parses_with_crew_resume`
- [ ] CLI: `crew_autopilot.py handoff-resume --root . [--ticket <id>]` prints the `resume:` line first, then
  `kind=<k> reason=<r>`, exit 0. An exception inside prints `resume: none` and `kind=unknown`, never a
  traceback alone. `crew_autopilot.py goal-mark --root . --goal <slug> --state <s> [--ticket <id>] [--reason <r>]`
  prints `marked=1` or `marked=0 reason=<r>`. `-k "cli"`
- [ ] `autopilot.md` section 5 takes the line from `handoff-resume --ticket <ticket>` and writes it as
  printed; it no longer states the ticket form as the only form. The goal loop calls `goal-mark` at each
  phase boundary: `running` with the ticket when a phase starts, `stopped` with the reason at any stop,
  `done` when the goal completes. `handoff.md` step 5 and the `crew-context` skill say: run
  `handoff-resume` first when the plugin ships autopilot, and a goal line it prints wins over the next
  command. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_lifecycle_commands.py -q`
  (new tests `test_autopilot_low_context_handoff_uses_handoff_resume`, `test_handoff_command_asks_handoff_resume`)
- [ ] PreCompact skeleton, both flavours: with one running goal the skeleton has exactly one line
  `resume: /crew:autopilot --goal <slug>` after `head:`; with no goal, with two running goals, with an
  unreadable goal file, and with no python, the skeleton is byte-identical to today's apart from the
  timestamp. An existing handoff is still never overwritten.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_resume_hook.py -q -k "skeleton"`
  (the `.ps1` cases skip without `pwsh`; say so in the report)
- [ ] The owner's scenario, part (a): a goal at ticket 2 of 3, a handoff written by each writer in turn
  (low-context stop, `/crew:handoff`, PreCompact skeleton), each carries the goal line.
  `-k test_goal_survives_a_handoff_from_every_writer` in `T`
- [ ] Existing suites pass unchanged:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_resume.py plugin/crew/tests/test_crew_resume_hook.py plugin/crew/tests/test_auto_cycle.py -q`
- [ ] `.crew/verify.json` maps `T` into the autopilot rule (`:348-359`). `python3 scripts/check-tooling-pr.py`
  prints `tooling-pr: OK`.
- [ ] Docs: README (the "Which ticket" paragraph near `:913` and the auto-resume section near `:2093-2160`),
  CONFIG.md near `:1121-1160`, `docs/guides/crew/src/auto-cycle.md` and `.crew/codemap/crew.md` state that
  a handoff written while a goal runs names the goal, and what `resume: none` with "could not tell" means.
  Guide outputs rebuilt with `python3 docs/guides/crew/src/build.py`. `plugin/crew/BUDGETS.md` re-measured.
  Crew bumped to the next free patch in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`, with a
  CHANGELOG entry. After the commit, `python3 scripts/check-marketplace.py` passes.

## Dependencies
Must land first:
- T-0012 (`approved`, not merged): the goal file `.work/autopilot/<slug>.json`, the slug and the `goal` subcommand.
- L-0541 (`direction`, split from T-0012): the loop that drives a goal's tickets and the `--goal` branch
  of `resume_target`. Without it nothing is "running" and there is no phase boundary to mark.
- T-0019 (`in-progress`), T-0010 (`merged`), T-0018 (`merged`): T-0012's own dependencies.
- T-0006 (`merged`): the `resume:` grammar, `parse_resume`, `render`.
- T-0004 (`merged`): `resume_target`, the low-context handoff in `autopilot.md`.

Coordinates with, neither blocks:
- T-0017 (`approved`): auto wrap-up writer. Whichever lands second calls `handoff_resume`.
- T-0049 (`in-progress`) and L-0589 (`direction`): in-flight markers; a goal that skips a ticket still marks its state.
- T-0053 (`ready`): sleep mode re-checked on resume; no rule here.

This ticket blocks:
- L-0658, L-0659 and L-0660.
- T-0054 (`ready`): the autopilot guide carries this as a worked example.

## Split
- L-0658 (child 1 of T-0056, filed 2026-10-04): A `--goal` handoff is checked against the goal file, not the branch and head
- L-0659 (child 2 of T-0056, filed 2026-10-04): Bare `/crew:autopilot` finds a running goal when there is no usable handoff
- L-0660 (child 3 of T-0056, filed 2026-10-04): Sabotage entries for goal resume: writers, handoff validation, discovery (tooling-only PR)

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
