# L-0665 plan (implementing session, 2026-10-05, rush/g4-deploy)

1. RED: `test_promote_gate_rows.py`, one table over row sequences and both real gates (`ps1` slow,
   skipped without pwsh): fail-then-pass admits, pass-then-fail blocks naming the newest row, no row,
   another sha only, a newest row with one cell not pass, a single all-pass row, `PASS` in capitals,
   a newer all-pass row for another environment or sha does not clear this one.
2. promote-gate.sh `passed()` keeps the last matching row's verdict (None for no row); the requires
   loop says "no all-pass row" for None and "the newest row is not all-pass" for False.
   promote-gate.ps1 `Test-Promoted` returns 'pass' / 'fail' / 'none' the same way.
3. Two mutations per flavour (first-match put back) in `promote_tree_mutations.py`.
4. L-0647's real-gate tests: the forged-row case now meets the revoked-pass message, and a pass
   recorded after record's not-run row admits.
5. Docs: promote.md (no net growth), crew-verification, README, troubleshooting (rebuilt), CHANGELOG.
