# Review harness cleanup from #781 (checklist)

Priority: P3 (maintenance; #781 has its own PR, so this tracks only the leftovers).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

All items VERIFIED by tonight's review, not re-run here. Harness paths land alone (CLAUDE.md, T-0087).
- [ ] Stale line citations in `external-tool-formats.md`.
- [ ] `optin_inventory` (tests/data/optin_inventory.json) out of date.
- [ ] `review-prepare` goldens out of date.
- [ ] Long lines in `sabotage_scope.py`.
Acceptance: each box closed in one harness-only PR with the harness rule's checks (check-tooling-pr.py, tooling-pr suite, golden replay, seam contracts, canary review) green. Related: `investigate-781-ten-failing-checks.md`.
