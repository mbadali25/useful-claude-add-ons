# #780 (verify.stopBudgetSeconds key): full crew suite never completed, one failure unidentified

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.
Siblings: `follow-up-777-ci-timing-slow-suite.md`.

## Problem

#780 makes `verify.stopBudgetSeconds` a settable, bounded (1..600) repo config key. Its verification is partial: the full `plugin/crew/tests` suite never completed on the author's host, and one of three failures seen in a targeted run was never identified.

## Evidence

VERIFIED by `gh pr view 780` on 2026-11-17: head `f53d6532e`, draft, base `main`, DIRTY, last PR update 2026-11-15T23:34Z; all 30 checks SUCCESS (so CI covers more than the author's host did). Crew 1.3.127 per the PR body.

From the PR body (read, not re-run): failures seen in a targeted run and said not to be caused by the change:
- `test_autoclear_sendkeys_removed::test_the_owner_repo_config_loads_...` fails identically on main (it loads the real owner `.crew/config.json`).
- `test_ci_receipt::test_build_after_a_real_gate_that_could_not_tell_lists_the_rule_unknown` hit the 120 s Git Bash `verify-gate.sh --all` timeout on a loaded host; not re-run to green.
- The cloud_guard tests hit the author's 300 s per-file bound and did not complete.
That is two named failures plus an incomplete file. The owner reports three failures with one never identified: which of these is the third, or whether a different one exists, is UNKNOWN.

Also not done (PR body): the published Claude Docs "Configuration Guide" was not updated (the repo template and guide source were). The `verify-gate.sh` reader still turns an unusable hand-edited value into 60; it is a HARNESS path and must land alone.

## Recommended next step

Run the full `plugin/crew/tests` suite in CI-sized shards (or read the CI result, which is green) and list every non-pass. Identify the third failure by re-running the targeted selection and recording each node id. Re-run the first failure on main to confirm it is unrelated.

## Acceptance criteria

- A complete list of failing, skipped and not-run tests for the head, with the host named.
- Every failure is tied to this change, to main, or to the host, with the run that shows it.
- The unidentified failure has a node id.

## Owner questions

1. Is green CI on all 30 checks enough to call the unrun suite covered?
2. Should the `verify-gate.sh` reader fix be a separate harness ticket now?

## Out of scope

Merging; the Configuration Guide refresh (see `housekeeping-breach-note-vault-docs-dashboards.md`).

## Related

#780 (`fix/verify-stop-budget-key`), `plugin/crew/hooks/scripts/crew_state.py` (`VERIFY_DEFAULTS`), `crew_config.py` (`INT_BOUNDS`), `test_verify_stop_budget_key.py`.
