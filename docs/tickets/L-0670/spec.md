# L-0670: autopilot approves a successor plan after an automatic reject only when it quotes every BLOCK and FIX line          status: spec   risk: high
Split from T-0074. Written 2026-10-04 against origin/main `155fe6d8` plus T-0074's spec. Line numbers in `crew_autopilot.py` move when T-0074 lands: re-read before planning.

## Intent
After T-0074's automatic reject, `crew_autopilot.py approve` refuses a successor plan whose `plan.md` does not hold every `BLOCK|` and `FIX|` line of the rejected round verbatim. A new read-only subcommand, `replan-check`, gives the same answer without approving, so the procedure can check the plan before it asks for approval. The owner's own approval route is unchanged.

## Design
- `crew_autopilot.replan_check(root, ticket)` returns `{"applies", "ok", "reason", "missing"}`.
  - `applies` is false, and `ok` true, when the ledger is not NEEDS_REPLAN or its `rejected.by` is not `AUTO_REJECT_BY`.
  - Otherwise it reads the row whose `round` equals `rejected.round`. The required lines are that row's `findings` entries that start with `BLOCK|` or `FIX|`, compared without stripping.
  - It reads `.work/tickets/<id>/plan.md` as UTF-8 with `newline=""`, splits on `\n` only, drops one trailing `\r` per line, and counts lines. `ok` is true only when every required line is present as a whole line at least as many times as the round carries it.
  - Could-not-tell is `ok` false with a reason: an unreadable ledger, a missing row, `findings` not a list of single-line strings, no BLOCK line in a round rejected for a BLOCK, `plan.md` missing, unreadable or not UTF-8.
- `approve` calls it after `approval_policy` allows and before `crew_ticket.approve`. When `applies` and not `ok`: exit 2, `refused: successor plan lacks <n> of <m> finding line(s), first: <line>`, nothing written.
- `replan-check` prints `applies= ok= missing=` and the reason, exit 0 when `ok`, 1 when not. It writes nothing.
- `commands/autopilot.md`: after `/crew:plan` on a non-stop `replan`, run `replan-check`; on exit 1 fix the plan once, then stop if it still fails.

## Exclusions
- No change to `crew_ticket.py`, `review_ledger.py`, `scope_guard.py` or any other harness path. `/crew:approve` and `crew_ticket.py approve --by` do not run this check.
- No requirement to quote NIT lines. No judgement of whether a plan step actually fixes the finding: only that the line is quoted.
- No check after an owner's reject, and none on a ticket's first plan.
- No sabotage entries (L-0671).
- No new config key.

## Evidence
Read at origin/main `155fe6d8` on 2026-10-04.
- plugin/crew/hooks/scripts/crew_autopilot.py:1129-1151 `approve`: `approval_policy` at :1142, `crew_ticket.approve` at :1145. :1602 `_policy_main`; :1674 and :1703 register and dispatch the policy subcommands.
- plugin/crew/hooks/scripts/review_ledger.py:399 a round row keeps `findings`. :803-821 `reject` writes `rejected: {by, at, round}`. :757-800 `check_follow_up`, the verbatim whole-line counted comparison this copies (newline handling at :781-789).
- plugin/crew/hooks/scripts/review_ledger.py:887-904: a successor plan must differ from every plan approved before, so the plan checked here is always a new file state.
- scripts/check-tooling-pr.py:89-95: `crew_autopilot.py` and `commands/autopilot.md` are seam paths, not harness.
- Nothing on main implements this: `git grep -n "replan-check\|replan_check" origin/main -- plugin scripts` prints nothing.

## Unknowns
- Whether `plan.md`'s validator (`crew_ticket.validate`) accepts raw `BLOCK|...` lines anywhere in a plan (for example inside a step body or a fenced block). Resolved at plan: run `crew_ticket.py validate` on a fixture plan that quotes three finding lines; if a placement is refused, the procedure text names the placement that passes.
- A finding line that contains a backtick or a pipe is quoted as is; no escaping. Accepted.
- The read of `plan.md` and the approval are not one atomic step. Accepted: `crew_ticket.approve` binds the receipt to the plan hash, and a plan edited afterwards stales the approval.

## Size
About 80 added production lines, all in `crew_autopilot.py`. One guard. No harness path.

## Touch
- `plugin/crew/hooks/scripts/crew_autopilot.py`
- `plugin/crew/commands/autopilot.md`
- `plugin/crew/tests/test_crew_autopilot_replan.py`
- `plugin/crew/tests/test_crew_autopilot_policy.py`
- `plugin/crew/tests/test_lifecycle_commands.py`
- `plugin/crew/README.md`
- `plugin/crew/BUDGETS.md`
- `plugin/PLUGINS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `CHANGELOG.md`
- `docs/guides/crew/src/daily-workflow.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-*` - the rebuilt HTML, DOCX and PDF
- `.crew/codemap/**`
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt

## Acceptance checks
`.crew/verify.json` rule: the autopilot policy rule (`crew_autopilot.py` with `test_crew_autopilot_policy.py`), which T-0074 extends with `test_crew_autopilot_replan.py`.
- [ ] `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_autopilot_replan.py plugin/crew/tests/test_crew_autopilot_policy.py -q` passes with these new tests:
  - `test_replan_check_passes_when_every_block_and_fix_is_quoted`
  - `test_replan_check_does_not_require_nit_lines`
  - `test_replan_check_fails_on_a_missing_line` (names the first missing line)
  - `test_replan_check_counts_duplicates` (a line the round carries twice must appear twice)
  - `test_replan_check_needs_whole_lines` (the finding as a substring of a longer line fails)
  - `test_replan_check_accepts_crlf_plan`
  - `test_replan_check_could_not_tell` (parametrised: corrupt ledger, rejected round row missing, `findings` not a list, `findings` with a multi-line string, no `BLOCK|` line, `plan.md` missing, `plan.md` not UTF-8): `ok` false, reason says could not tell
  - `test_replan_check_not_applicable_after_owner_reject` and `test_replan_check_not_applicable_when_not_needs_replan`
  - `test_approve_refuses_successor_that_drops_a_block`: exit 2, `refused:`, `approval.json` and the ledger unchanged byte for byte
  - `test_approve_allows_successor_that_quotes_all`: exit 0, ledger IN_REVIEW
  - `test_owner_cli_approve_is_not_checked`: `crew_ticket.py approve --by` on the same dropped-line plan still succeeds
  - `test_replan_check_writes_nothing`
- [ ] `python3 scripts/check-tooling-pr.py` exits 0 with no harness path changed.
- [ ] `git diff origin/main...HEAD -- plugin/crew/hooks/scripts | grep -c '^+[^+]'` is under 300.
- [ ] `commands/autopilot.md`, README's autopilot section and the two guide sources (with rebuilt outputs, `python3 docs/guides/crew/src/build.py`) describe `replan-check` and the refusal; `grep -n "replan-check" plugin/crew/commands/autopilot.md plugin/crew/README.md docs/guides/crew/src/troubleshooting.md` prints a line per file.
- [ ] crew bumped one patch past origin/main in both version files, CHANGELOG entry; after the commit `python3 scripts/check-marketplace.py` exits 0.
- [ ] `python3 -m pylint plugin/crew/hooks/scripts/crew_autopilot.py` scores 10.00; ruff reports no new finding against the merge base.
- [ ] PR body says the sabotage run for this guard is not done here (L-0671) and that `scripts/_test/drift-detection.sh` was not run.

## Dependencies
- T-0074, direction (spec written 2026-10-04): must be merged first; this reads its `AUTO_REJECT_BY` and its test file.
- T-0010, merged; L-0510, done: as for T-0074.
- Blocks: L-0671 (its mutations for this check).

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
