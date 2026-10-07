# L-0518 tooling half - plan (rush/h3-review)

The spec's "Tooling half" section, built on its own (harness only). The feature half is another lane's.

1. F2, test first: `rl.reserve(..., gated=False)` refuses with `GATE_CHANGED`, writing nothing, when the
   locked ledger would reserve; a spent budget still answers as spent. `run` passes `gated` and maps
   `GATE_CHANGED` to exit 2 (not 4: nothing is spent and the budget is not the reason). Must-block: an
   in-process run with `review_ledger.status` patched to NEEDS_REPLAN over a ledger with rounds left.
   Must-allow: `test_run_reports_a_spent_budget_before_the_selfcheck` unchanged.
2. N4: `_incident` / `_log_skip` wrap the incident read and the skip log for both gates; OSError and
   ValueError print `review-run: <gate> gate could not run: ...` and exit 2.
3. Sabotage (sabotage_standards.py): F2's check removed, and each N4 catch narrowed to
   ZeroDivisionError. Two existing entries re-anchored onto the new lines.
4. Not built (feature not on main): the F1/F3/F4/N5 sabotage entries and review.md's F1 wording.
