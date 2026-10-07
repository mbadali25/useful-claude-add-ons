# L-0666: autopilot stop messages name only owner decisions (a contract test over every stop)          status: spec   risk: med
Split from T-0067 on 2026-10-04. Written against origin/main `155fe6d8` (crew 1.0.322). Line numbers below are main's; T-0067 lands first and moves them, so re-read before planning.

## Design (for the owner to confirm at approval)
- `OWNER_DECISIONS` in `crew_autopilot.py`: a closed tuple of `(id, what the owner decides, command template or "")`. The ids, one per kind of stop main has:
  - `direction` (brainstorm, or say the direction is approved) - `/crew:brainstorm`
  - `answer-question` - no command
  - `fix-contract` (spec.md or plan.md fails validation) - `/crew:spec <id>` or `/crew:plan <id>`
  - `approve-plan` - `/crew:approve <id>`
  - `replan` - `/crew:plan <id>`
  - `accept-review` (accept or reject FINDINGS) - no command; the reason names `review_ledger.py --accept --by <owner>`
  - `spend-round-or-replan` (an INCOMPLETE round, a reserved round with no result) - no command
  - `revert-or-replan` (no round left, no receipt) - no command
  - `look` (could-not-tell: unreadable ledger, unsettled artifact, refresh check unavailable, a crash, no progress) - no command
  - `stale-after-review` - no command
  - `activate-ticket` - no command; the reason names `crew_ticket.py activate --ticket <id>`
  - `continue` (maxPhases reached) - `/crew:autopilot <id>`
  - `closed` - no command, nobody waits
- Every stop `next` returns carries `decision`, one of those ids. The CLI prints `decision=<id>` on the `phase=` line and in `--json`. `stops` prints the list as a fourth-style group, `decisions`.
- `MECHANICAL` in `crew_autopilot.py`: a closed tuple of command shapes a stop may not hand the owner: `graphify update`, `graphify . --`, `/crew:onboard --refresh`, `/crew:diagram refresh`, `/crew:graph --refresh`, `--auto-accept --follow-up`, `crew_autopilot.py resume`, `crew_refresh_check.py`, `then /crew:review`.
- Rewording this forces:
  - the FINDINGS stop names the accept command and says that `autopilot.reviewPolicy: fix-and-rereview` makes autopilot fix and re-review itself; it no longer says "or fixes then /crew:review" or "run review_ledger.py --auto-accept";
  - the ticket-mismatch stop names only `crew_ticket.py activate --ticket <id>`;
  - an unsettled-artifact stop lists only the artifacts a refresh cannot settle, each with its reason; the `(refresh: <command>)` suffix stays on the non-stop `refresh` phase only.
- `resume` and `route` stops carry no `decision` (they pick a ticket, they do not drive one). Their reasons are held to `MECHANICAL` too.
- `commands/autopilot.md` section 3 prints the decision with the reason; section 5's report says "the decision the owner makes next".

## Intent
Every stop `/crew:autopilot` prints asks the owner for a decision only they can make, names which decision it is, and never tells them to run a refresh, a graph build, a review round within budget, a suite or a crew helper. A test walks every stop site in `crew_autopilot.py` and fails when one breaks that rule or when a stop is added without a case.

## Exclusions
- No behaviour change: every stop that stops today still stops, with the same `phase`. Only `reason` text, the new `decision` field and (for one stop) the listed artifacts change.
- No new non-stop phase. Finishing an interrupted auto-accept unattended is T-0073's.
- No change to `HUMAN_STOPS`, `FIXED_STOPS` or `PROCEDURE_STOPS` texts, which README.md:915 and the command quote.
- No edit to any harness path (`plugin/crew/tests/sabotage*.py`, `review_*.py`, `commands/review.md`). Lines existing mutations anchor stay byte-identical, including `        return answer("approve", True, ` (sabotage_autopilot.py:34).
- No change to `crew_refresh_check.py`'s own reason strings.
- `/crew:status` output keeps its 12-line limit; the decision is not added there.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:414-416 the `answer` closure (`ticket`, `phase`, `stop`, `reason`, `command`, `evidence`). Stop sites: :421, :426, :429, :434, :437, :445, :449, :458, :465, :479, :495, :498, :508, :522, :528, :541, :553, :562 (and :556, which stops when no command settles), :588, :594, :598.
- :519-525 the FINDINGS stop text. :591 the ticket-mismatch text. :368-371 the `(refresh: ...)` suffix built in `_refresh_state`. :570-571 the docstring rule. :1283-1288 `stops()`. :1598 `_line`. :668-727 `resume_target` and its `stopped` helper.
- plugin/crew/commands/autopilot.md:69-70 "any other `stop=1` - print the phase, the reason and the command the human types (may be empty), then stop". :108-109 the report.
- plugin/crew/tests/test_crew_autopilot.py:1229 `test_stops_lists_every_autonomous_stop`, :1256 `test_command_names_every_fixed_and_human_stop`, :1310 `test_code_enforced_stops_are_not_procedure_stops`.
- plugin/crew/tests/sabotage_autopilot.py:33-36 anchors the `approve` stop's first line.
- scripts/check-tooling-pr.py:89-95: `crew_autopilot.py` and `commands/autopilot.md` are seam paths; with no harness path changed the check prints `tooling-pr: no harness path changed` (:189).

## Unknowns
- Whether `crew_status.py` or `crew_resume.py` parse `next`'s one-line output by position. Resolved at plan: `git grep -n "crew_autopilot" origin/main -- plugin/crew/hooks/scripts/crew_status.py plugin/crew/hooks/scripts/crew_resume.py`. `decision=` is appended after the existing fields so a prefix reader is unaffected.
- The exact decision id per stop site is settled at plan from the table above; a site the table does not fit gets `look`, never a new id invented in a test.
- How the completeness test counts sites: recommended is an `ast` walk for calls to `answer` whose second argument is `True` (or not a literal `False`), `dict(result, stop=True, ...)` and `stopped(...)`. If a site is built another way at plan time, the walk is extended, not the site exempted.
- The next free crew patch version is set at implement time.

## Size and split
About 80 added production lines (`crew_autopilot.py` about 70, `autopilot.md` about 10). No parser, no new fail-closed state. No harness path.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_stop_contract.py` - new
- `plugin/crew/tests/test_crew_autopilot.py`
- `plugin/crew/tests/test_crew_autopilot_status.py`
- `plugin/crew/tests/test_crew_autopilot_review_policy.py` - where it pins the FINDINGS stop text
- `.crew/verify.json` - the new test file joins the autopilot rule
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `.crew/codemap/**`
- `docs/diagrams/**`
- `.claude/rules/**` - regenerated, never hand-edited
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

Not in Touch, stated: `docs/guides/crew/**` (no guide describes autopilot; the PR body says so); every harness path.

## Acceptance checks
Commands run from the repo root. `T` is `plugin/crew/tests/test_crew_autopilot_stop_contract.py`. All map to the autopilot rule in `.crew/verify.json`.
- [ ] Every stop carries a decision. One parametrised case per stop site builds the state that reaches it and asserts `stop` is true and `decision` is the expected id from `OWNER_DECISIONS`. `python3 -m pytest T -q -k test_every_stop_names_an_owner_decision`
- [ ] The command of a stop is empty or the decision's registered command for that ticket. `-k test_a_stop_command_is_the_decisions_own_command`
- [ ] No stop reason contains a `MECHANICAL` shape, for every case above and for every `resume` and `route` stop. `-k test_no_stop_hands_the_owner_a_mechanical_step`
- [ ] Completeness. The number of stop sites found by walking `crew_autopilot.py`'s source equals the number of cases; the failure message lists the uncovered sites by line. `-k test_every_stop_site_has_a_case`
- [ ] Must-block (the contract can fail). With `monkeypatch`, a stop whose reason is given "run graphify update ." fails the mechanical check, and one given a `decision` outside the list fails the decision check. `-k test_the_contract_rejects`
- [ ] The three reworded stops, one test each: the FINDINGS stop names `--accept --by` and the policy, and not `--auto-accept --follow-up`; the ticket-mismatch stop names `crew_ticket.py activate` and not `crew_autopilot.py resume`; an unsettled-artifact stop lists no `(refresh:` suffix while the non-stop `refresh` phase still carries its command. `-k "findings_stop or mismatch_stop or unsettled_stop"`
- [ ] The CLI prints `decision=` on a stop and `stops --json` has a `decisions` group. `-k test_cli_prints_the_decision`
- [ ] The command prints the decision and never tells the human to run a refresh. `-k test_command_reports_the_decision`
- [ ] No behaviour change: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_autopilot_status.py plugin/crew/tests/test_crew_autopilot_policy.py plugin/crew/tests/test_crew_autopilot_review_policy.py -q` passes, with only reason-text assertions edited.
- [ ] Existing anchors intact: `python3 -m pytest plugin/crew/tests/test_sabotage_harness.py -q -k test_every_shipped_anchor_is_present_in_its_target_exactly_once`, and `git diff --name-only origin/main...HEAD -- 'plugin/crew/tests/sabotage*.py'` prints nothing.
- [ ] Not a tooling PR: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: no harness path changed`.
- [ ] Docs: README (stops paragraph), CONFIG.md section 20, the code map's autopilot section and the lifecycle diagram describe the decision field. Crew is bumped to the next free patch with a CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` passes. `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` passes.

## Dependencies
Must land first: T-0067 (ready; the parent slice - same function, and the FINDINGS stop refers to its policy). T-0004, T-0010, T-0018 (all merged).
Related: T-0073 (direction; acceptance policy), T-0070 (spec; `/crew:status --approvals`).
Blocks: L-0668 (sabotage for this contract).

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
