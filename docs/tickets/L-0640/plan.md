# L-0640 plan (written by the implementing session, 2026-10-05, on rush/g3-contracts)

Base: rush/g3-contracts, which carries L-0639 (`crew_ticket_state.py`, `view`) and has merged
origin/release/1.2.0 `a555ff37` (crew 1.1.0). `view` gains a `today` parameter (default the local
date) and two keys, `next` and `revisit_due`; its problems list carries next.md's problems.

Owner question 4 (successor in spec.md line 2, as #394 shipped, or in next.md) had no option taken.
Taken here, to be confirmed: next.md's `superseded-by:` is read, and the "superseded: cannot tell
what replaced it" problem is raised only when neither it nor a `split-into:` / `superseded-by:` line
under the spec header names a successor, so tickets split by `/crew:split` (T-0052) do not all
report a false problem.

### Step 1 - tests first
Files: plugin/crew/tests/test_ticket_state.py
Test: every must-block and must-allow name in the spec's acceptance list, plus a non-`key: value`
line, an empty value, clipping, needs-owner with `next:`, and the spec-successor must-allow;
`test_view_is_read_only` now runs with a next.md present.

### Step 2 - read_next and the view join
Files: plugin/crew/hooks/scripts/crew_ticket_state.py
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_ticket_state.py -q
Risk: med - a parse that drops a bad value silently would read as "nothing asked".

### Step 3 - docs, version
Files: plugin/crew/README.md, docs/guides/crew/src/daily-workflow-scope.md (and the rebuilt
crew-daily-workflow HTML/DOCX/PDF), CHANGELOG.md, version files
Test: python3 scripts/check-marketplace.py; python3 scripts/check-tooling-pr.py
