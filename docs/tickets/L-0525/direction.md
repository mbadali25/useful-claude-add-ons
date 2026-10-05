# L-0525 direction - sabotage suite: 13 vacuous entries (STILL GREEN), 1 unproven (exit 4, docs.theme), and the cloud guard r1 OOM (T-0080) keep the whole run from going green

Status: approved 2026-10-05 for cloud hand-off (orchestrator, owner's standing self-approve authority). Was: seed.

Owner decision 2026-09-30 (~10:05 CDT, T-0086 round-1 BLOCK 2, "Waive + L- ticket"). T-0086 round-1 review
(Codex gpt-5.6-sol) blocked on "required whole sabotage run is not green". The owner waived it for T-0086
on this evidence: T-0086's own 49 STANDARDS_MUTATIONS are all RED (/root/crew-tmp/t-0086/sabotage-std.log,
`SABOTAGE SUITE: PASS`), and the identical non-RED list appears on T-0094's branch (non-RED lines of
/root/crew-tmp/t-0086/sabotage.log diffed against /root/crew-tmp/t-0094/sabotage-r4.log, and
sabotage-rest.log against sabotage-r4-rest.log: both diffs empty). So these entries are pre-existing on main,
not T-0086's. This ticket makes the whole run green.

## Entries, verbatim from the run (with the sabotage file that defines each)

STILL GREEN -- TEST IS VACUOUS (13):

1. `promote-gate.ps1 reads an unreadable map as one that gates nothing` - plugin/crew/tests/sabotage.py
2. `the frozen artifact path is stored with native separators` - plugin/crew/tests/sabotage.py
3. `the schema 5 migration lands install.policy above the floor` - plugin/crew/tests/sabotage.py
4. ``the PowerShell gate stops rejecting a `run` entry it cannot represent`` - plugin/crew/tests/sabotage.py (:2457, string split across two lines)
5. `the PowerShell Stop budget charges each command the rule's cost` - plugin/crew/tests/sabotage.py
6. `the PowerShell deadline read overflows Int32 again` - plugin/crew/tests/sabotage.py
7. `the bash gate stops publishing a deadline at all` - plugin/crew/tests/sabotage.py
8. `the PowerShell gate stops publishing a deadline at all` - plugin/crew/tests/sabotage.py
9. ``the PowerShell budget lets a priced rule defer an `always` command`` - plugin/crew/tests/sabotage.py
10. `the PowerShell gate stops making an unpriced rule unconditional` - plugin/crew/tests/sabotage.py
11. `the PowerShell gate charges a mandatory command twice` - plugin/crew/tests/sabotage.py
12. `the PowerShell gate hoists a mandatory command out of its rule` - plugin/crew/tests/sabotage.py
13. `Get-CrewChildTabRecheck skips the post-delay tab check again` - plugin/crew/tests/sabotage_autocycle.py

RED BUT UNPROVEN (1):

14. `RED BUT UNPROVEN -- exit 4, not a test failure docs.theme default goes back to the string neutral` - plugin/crew/tests/sabotage.py

Run stopped / skipped (1, T-0080):

15. `cloud guard r1: azureProfile.json opened whatever it is` (index 406) - plugin/crew/tests/sabotage_cloud.py:565.
    The run is killed there (`exit=143`, sabotage.log line 407; T-0094 `rc=143`), and the rest is only reachable by
    resuming after index 406 with that entry skipped (sabotage-rest.log: "running 973 mutations after 'cloud guard r1:
    azureProfile.json opened whatever it is' (index 406), which is skipped; total 1380"). The unbounded read is T-0080's
    (sabotage harness bounds memory; sabotage_cloud.py:544, :564).

## Acceptance (seed)

- One uninterrupted `python3 plugin/crew/tests/sabotage.py` run under heavy-run ends `SABOTAGE SUITE: PASS`, exit 0,
  no index skipped, on a Linux host with pwsh (the vacuous PowerShell entries may need pwsh present to go RED - measure
  whether each is vacuous or merely unexercised without pwsh, and say which).
- Each of the 13 entries is either made RED by a real test or removed with the reason stated; the docs.theme entry fails
  a test (not exit 4).
- T-0080's bound lands or is depended on; this ticket does not duplicate it.

## Not in scope

- T-0086's standards content. Any new sabotage entries beyond these 15.

## Ask

Make one uninterrupted `python3 plugin/crew/tests/sabotage.py` run end `SABOTAGE SUITE: PASS` on Linux with
no entry skipped, by dealing with the entries above that are not `RED (good)`. Re-measured on origin/main
`a555ff37` (2026-10-05):

- Entry 15 (the cloud guard OOM) is **already fixed**: T-0080 landed in PR #399 (crew 1.0.337, harness PR
  H2a). `sabotage_bound.py` caps each entry with `RLIMIT_DATA` and a wall clock, and the azureProfile entry
  now reads RED under the 4096 MiB default (`plugin/crew/tests/sabotage_cloud.py:566-575`). Nothing is left
  to do for it except confirm it in the full run.
- Entry 14 (`docs.theme`, exit 4) names a test that no longer exists. `test_upgrade_config_adds_the_docs_and_bitbucket_blocks`
  was renamed to `test_upgrade_config_recognises_the_docs_and_bitbucket_blocks` (`plugin/crew/tests/test_upgrade.py:219`),
  and the renamed test no longer checks the default. pytest exits 4 when the node id cannot be found.
- Entries 4-12 (nine PowerShell/bash verify-gate entries) target tests that are `skipif` off Windows even
  when pwsh is present (`plugin/crew/tests/test_verify_gate_stop_budget.py:61-62`, `test_verify_gate_lock_window.py:66-67`, `:309-310`,
  `test_verify_gate_rule_framing.py:285`). On Linux they are **unexercised, not proven vacuous**. A
  skipped-only pytest run exits 0, so `sabotage_bound.verdict` (`plugin/crew/tests/sabotage_bound.py:129-130`) calls it
  `STILL GREEN -- TEST IS VACUOUS`.
- Entry 13 (`Get-CrewChildTabRecheck`) targets a Windows-only test. It already has a Linux structural twin
  (`plugin/crew/tests/sabotage_autocycle.py:480-494`).
- Entries 1-3 run on Linux and need a measurement each: the promote-gate.ps1 test is `needs_pwsh`
  (pwsh resolves on this host, `/snap/bin/pwsh`); the separator test cannot see a backslash on POSIX; the
  `INSTALL_DEFAULTS` mutation (`plugin/crew/hooks/scripts/crew_guards.py:48`) is aimed at a migration test that no longer reads that
  constant (`plugin/crew/tests/test_install_policy.py:235-252`).

## Options

1. **Teach the runner "not run on this host", and re-point the Linux entries (recommended).** A Windows-only
   entry is declared Windows-only by label (a set kept outside `sabotage.py`, which has 19 lines of room
   under pylint's 3400). On a non-Windows host it prints `NOT RUN -- windows-only` and is listed in a footer.
   An entry whose target is entirely skipped *without* that declaration is a new verdict,
   `NOT EXERCISED -- target skipped`, and it fails the suite. Entries 1-3 and 14 are re-pointed at a test
   that really fails, with a new test where none exists. Tradeoff: the Linux PASS does not prove the
   Windows entries. The footer says so, and they are proven on the Windows matrix (win-repo-2).
2. **Make the Windows-only tests run under Linux pwsh.** Lift the `sys.platform` skip where pwsh and bash
   are both present. Tradeoff: verify-gate.ps1 is written for Git Bash on Windows, path and process
   semantics differ, and making it portable is production work in a harness file. That makes it bigger and
   riskier than the ticket, and its own suites may go red for reasons that have nothing to do with sabotage.
3. **Delete the nine Windows-only entries.** Tradeoff: the Windows defects they pin lose their only
   mutation coverage. This is the outcome the "a skip is a finding" rule exists to prevent.

## Recommendation

Option 1. It keeps every entry, and it makes "skipped" its own value instead of collapsing it into either
"vacuous" or "pass" (CLAUDE.md: an unknown must not collapse into the safe-looking value). It also keeps the
change inside the sabotage harness. All of it is in `HARNESS` (`plugin/crew/tests/sabotage*.py`), so this
is a **tooling-only PR**.

## Open questions (default taken)

- Should a Linux run that skips Windows-only entries print PASS? **Default taken:** yes, as
  `SABOTAGE SUITE: PASS (N windows-only entries not run on this host)`, exit 0. An undeclared skip still
  fails.
- How is a skip detected? **Default taken:** pytest's summary line (`N skipped` with no `passed`/`failed`).
  pytest's `-rs` output is parsed by the runner, not guessed from the exit code. If the summary cannot be
  read, the verdict is "could not tell" and fails.
- What if entry 1, 2 or 3 turns out to be a real production defect rather than a weak test?
  **Default taken:** the entry is marked with the measured reason and a production fix is filed as a new
  ticket, because production code is not allowed in a tooling-only PR.
- Is entry 15 in scope? **Default taken:** no. T-0080 owns it, and it is already fixed. This ticket only
  confirms it in the full run.
