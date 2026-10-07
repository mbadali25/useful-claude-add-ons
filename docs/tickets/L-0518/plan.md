# L-0518 plan            spec: docs/tickets/L-0518/spec.md

Risk: medium. Feature half only: no HARNESS path (the Tooling half, F2/N4/`commands/review.md:531`/sabotage
entries, is built by another lane). Crew version at land (the release lane's placeholder in its last commit).

### Step 1: F1, proposals reads the round's recorded verdict
Files: plugin/crew/hooks/scripts/crew_standards.py, plugin/crew/tests/test_crew_standards.py
Where: `proposals`; ledger via `review_ledger.status` (read only)
Test: python3 -m pytest plugin/crew/tests/test_crew_standards.py -q -k proposals
Risk: medium - proposals now refuses more
Standards: GEN-01, GEN-04, GEN-07
- [ ] ledger fixture for the existing proposals tests (round N recorded FINDINGS or CLEAN)
- [ ] `test_proposals_refuses_a_round_the_ledger_records_incomplete`, `test_proposals_refuses_without_a_ledger_row` (no ledger, unreadable ledger, no row, reserved row), red first
- [ ] the ledger row for `--round N` must be completed with verdict CLEAN or FINDINGS before `out.txt` is parsed; anything else refuses naming what the ledger says, nothing written

### Step 2: F3, a SHA-256 stamp base
Files: crew_standards.py (`_STAMP_RE`), test_crew_standards.py
Test: -k "test_stamp_and_gate_in_a_sha256_repository or test_stamp_base_of_another_length_refuses"
Risk: medium - the gate reads this regex in every repo
Standards: GEN-07, GEN-04
- [ ] `base=` is exactly 40 or exactly 64 lowercase hex

### Step 3: F4, `sets --touch`
Files: crew_standards.py (`_sets`, `effective_set`, `main`), test_crew_standards.py, crew-plan/SKILL.md, crew-standards/SKILL.md
Test: -k "test_sets_touch_needs_no_scope_base or test_sets_touch_unknown_lists_every_set or test_stamp_refuses_without_a_scope_base"
Risk: low
Standards: GEN-01, GEN-07
- [ ] Touch entries matched by overlap (`recurring_findings.matches(..., touch=True, root=root)`); no scope base needed
- [ ] unreadable spec or Touch list: `UNKNOWN:`, every stack set, exit 1; plain `sets` unchanged

### Step 4: N5 and the NITs
Files: crew_standards.py (`_scope`), test_crew_standards.py, crew-standards/SKILL.md (N2), CHANGELOG.md (N1), .crew/codemap/INDEX.md (N3)
Test: -k test_stamp_scope_fallback_when_the_record_is_unusable; the spec's grep checks
Risk: low
Standards: GEN-09
- [ ] "(fallback)" once on a line

### Step 5: docs
Files: plugin/crew/README.md, docs/guides/crew/src/daily-workflow.md (+ rebuilt HTML), .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md, .claude/rules (regenerated)
Test: whole suites per the spec; `python3 scripts/check-tooling-pr.py`; `check-marketplace.py` after the commit
Risk: low
Standards: GEN-09
