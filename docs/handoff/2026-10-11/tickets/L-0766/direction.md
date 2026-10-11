# L-0766: repair or retire the 12 sabotage entries that stay green on main

Type: task (review harness: lands alone, per the T-0087 rule)
Status: direction
Filed by: the L-0753 lane, 2026-10-10, at the coordinator's request (owner decision on #593).
Related: L-0753 (where this was found), L-0709 (hermetic homes: may explain the host-config cases), L-0756.

## What was seen

`plugin/crew/tests/sabotage.py` in the local gate at L-0753 head `1b4c8f8f`
(`/root/crew-tmp/l-0753/gate-r1/logs/sabotage.log`) reported `SABOTAGE SUITE: FAIL` with 12 entries
`STILL GREEN -- TEST IS VACUOUS`. Exactly those 12 entries were re-run on a clean origin/main `d8de3daf`
worktree with sabotage.py's own apply/run/restore functions, under heavy-run, and all 12 stayed green
there too. Two control entries ("doc-builder is dropped from the routing table", "the findings-report
script stops accepting --brand") went RED the same way, so the re-run harness can see a red. This is not
caused by L-0753: none of the mutated files or their target tests are in L-0753's diff.

The 12 entries (label, file that defines it):

1. the promote gate reads an unparseable map as `not a deployment` (sabotage.py)
2. auto-accept defaults a missing ignored_lines to 0 (sabotage_review.py)
3. the context hook stays silent with memory.inject unset (sabotage_context.py)
4. cloud guard r5: PowerShell never unseen (sabotage_cloud.py)
5. cloud guard r5: PowerShell launchers not read (sabotage_cloud.py)
6. cloud guard r7: a lone quoted PowerShell string read as a program (sabotage_cloud.py)
7. cloud guard r7: PowerShell's colon-bound values not read (sabotage_cloud.py)
8. cloud guard r7: a string piped into Invoke-Expression not read (sabotage_cloud.py)
9. the scope base record loses its protection (sabotage_scope.py)
10. the marker's shape check is dropped (sabotage_limit_worktree.py)
11. a round of true passes for round 1 (sabotage_limit_worktree.py)
12. sabotage bound: a timed-out entry counts as RED (sabotage_tooling.py)

## Unknowns

- Whether each one is vacuous everywhere, or only on this host. #3 is very likely the host
  `~/.claude/crew/config.json` leak that L-0709 removes; re-check after L-0709 lands before changing it.
- The sabotage suite is not in CI (only `scripts/gate-runner.py` runs it), so CI never shows this.

## Acceptance (draft)

- Every entry that stays green on main is either repaired (its target test goes red under the mutation,
  seen by hand) or retired with a stated reason, in a harness-only PR.
- `python3 plugin/crew/tests/sabotage.py` on main reports no `STILL GREEN` line on Linux.

## Note 2026-10-11 (L-0777 lane, #600)

Entry 3 (`the context hook stays silent with memory.inject unset`) is still green on main 987ea4fb8 on
2026-10-11 (`.work/tickets/L-0777/gate-ee19528bf/sabotage-subset17-main-987ea4fb.log`), and RED on lane A's
hermetic branch bdc7bc55 (L-0709, #584). Its target is in `plugin/crew/tests/test_crew_context_wrappers.py`, the
same file as the two pytest failures of the L-0753 precedent. All 12 entries above stayed green on 987ea4fb8 in
that run.

## Added 2026-10-11: five `RED BUT UNPROVEN` entries (owner decision: accept and ticket)

Owner decision, Matthew, 2026-10-11, through AskUserQuestion, relayed by the lead to the coordinator
(ac5b48330c1347c0d): the five entries below are ACCEPTED on #600 (L-0777) and #584 (L-0709) as pre-existing on
main 987ea4fb, and are added to this ticket to be repaired or retired with the 12. The repair is harness work
(`sabotage*.py`) and lands alone, later. No lane is started for it by this note.

Why they sit here and not in a sibling ticket (coordinator's choice): they are the same defect class as the 12,
a sabotage entry on main that does not prove its target test caught the mutation; they live in the same suite;
and one harness-only PR can then make `sabotage.py` report nothing but `RED (good)` on main.

They were NOT covered by this ticket's original list of 12, nor by the L-0753 waiver, which names
`STILL GREEN` entries only.

What the verdict means, from `plugin/crew/tests/sabotage_platform.py`: "`RED BUT UNPROVEN`: any other non-zero
exit, or exit 1 with an error, a skipped case or an unreported collected case beside the failure."

Reproduced on main 987ea4fb by two lanes with the same verdicts:
`.work/tickets/L-0709/gate-bdc7bc55/sabotage-subset-main-987ea4fb.log` (lane A) and
`.work/tickets/L-0777/gate-ee19528bf/sabotage-subset17-main-987ea4fb.log` (lane D). Neither PR's diff touches
the mutated lines, the target tests or the sabotage entries.

Per entry, as measured by lane A on bdc7bc55 and lane D on ee19528bf:

1. `the deploy default is all` - `RED BUT UNPROVEN -- exit 4, not a test failure`. Mutates the
   `AUTOPILOT_DEFAULTS` line in crew_state.py. Its target id,
   `tests/test_crew_autopilot_deploy.py::test_deploy_only_in_machine_layer_reads_none`, does not exist; the
   function is now `test_deploy_only_in_machine_layer_is_the_default_since_t0050`. Unmutated pytest says
   `no tests ran`. A dangling target: it exits 4 whatever the mutation does, so the mutation is never tested.
2. `approve writes beside the receipt` - `RED BUT UNPROVEN -- exit 4, not a test failure`. Mutates
   crew_autopilot.py; target `tests/test_crew_autopilot_policy.py::test_approve_is_the_only_writing_subcommand`
   exists and passes unmutated. The mutation inserts a line between a `try:` body and its `finally:`, and
   compiling the mutated file gives `SyntaxError: expected 'except' or 'finally' block (crew_autopilot.py,
   line 2392)`. The red is a collection error, not the assertion, so the mutation is never tested.
3. `the gate does not export CLAUDE_PLUGIN_ROOT to its rule commands` - `exit 1, partial: 2 skipped`.
4. `the gate replaces a CLAUDE_PLUGIN_ROOT its caller set` - `exit 1, partial: 1 skipped`.
5. `the gate keeps an empty CLAUDE_PLUGIN_ROOT` - `exit 1, partial: 2 skipped`.
   Entries 3 to 5 mutate verify-gate.sh, with targets in `tests/test_verify_gate_plugin_root.py`, parametrized
   over sh and ps1. On Linux the ps1 cases skip ("the .ps1 gate is the native-Windows flavour"), so the run is
   red with skips beside it. Lane A infers the sh case is the one that fails; no lane re-ran a mutation to see
   the failing id. Proof on Linux only.

Not established: whether an older ticket or waiver already names these five. Lane A found none, and words that
as "not found": it did not read every older hit or grep INDEX.md for the labels.

Acceptance, added: every one of the five is either repaired (entries 1 and 2 actually test their mutation;
entries 3 to 5 are judged in a way that does not read a platform skip as "unproven", or are declared in
`PLATFORM_ONLY` terms) or retired with a stated reason, in the same harness-only PR as the 12.
