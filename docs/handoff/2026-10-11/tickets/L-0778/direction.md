# L-0778: [harness] L-0777 tooling half: crew:reviewer as a Kimi dispatcher outside a reserved /crew:review round (Claude in step 2c), review.md step 2c wording, committed sabotage entries for the L-0777 suites

Source ticket: L-0777 (move crew's four subagents to Kimi K3; owner decision 2026-10-11, option A, an
explicit exception to the 2026-10 crew feature freeze). The paths below are HARNESS
(`scripts/check-tooling-pr.py`), so under the standing split rule they land alone, after L-0777:

- `plugin/crew/agents/reviewer.md`: a thin dispatcher like the other three. Dispatched ad hoc it hands the
  review to `crew_kimi_agent.py --role reviewer` (family-guarded through `qa.roles.review`); inside a
  reserved `/crew:review` step 2c round (provider `claude`) it reviews itself and never dispatches, so the
  ledger records the provider that actually ran.
- `plugin/crew/commands/review.md` step 2c: tell the reviewer it is the reserved Claude round.
- `plugin/crew/tests/sabotage_*.py`: the committed sabotage entries for L-0777's suites (tree check, KIMI
  UNAVAILABLE fallback, the security family guard), from `.work/tickets/L-0777/notes.md`.
