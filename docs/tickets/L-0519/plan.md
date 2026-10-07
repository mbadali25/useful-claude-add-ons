# L-0519 plan            spec: docs/tickets/L-0519/spec.md

Risk: low. No harness path. Crew version at land (the release lane's placeholder in its last commit).

### Step 1: the id cross-reference test, red first
Files: plugin/crew/tests/test_recurring_findings.py
Where: beside `test_shipped_checklist_pins_the_seven_classes`
Test: python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_recurring_findings.py -q -k test_every_class_names_a_standard_that_exists
Risk: low
Standards: GEN-04, GEN-09
- [ ] `test_every_class_names_a_standard_that_exists`: ids in each shipped section's `seen:` (`\b[A-Z]{2,6}-\d{2}\b`) are non-empty and each is in a `crew-standards/references/*.md` set or this repository's `.crew/standards.md`, read through `crew_standards.parse_set`
- [ ] run it: red on RF-07 only

### Step 2: RF derived, RF-07 re-pointed, probes read against their standards
Files: plugin/crew/skills/crew-qa-standards/references/recurring-findings.md
Test: the Step 1 test green; `pytest_rule.py R plugin/crew/tests/test_review_prompt.py -q`
Risk: low
Standards: GEN-09
- [ ] intro: RF is derived from crew-standards; each `seen:` names the standard; the standard wins on a conflict
- [ ] RF-07 `seen:` names GEN-09 and this repository's REPO-03
- [ ] read all probes against the cited Self-checks; record "agrees" or the edit (the PR body)
- [ ] sabotage by hand: GEN-09 -> GEN-99 on RF-02 goes red naming RF-02 and GEN-99; restore

### Step 3: the split, stated in both skills and the process rules
Files: crew-standards/SKILL.md, crew-qa-standards/SKILL.md, references/harness.md (H8), references/review.md (R10, R12)
Test: the spec's grep checks
Risk: low
Standards: GEN-09
- [ ] same wording of the split in both SKILL.md files, each naming the other
- [ ] one "Code-level standard:" line each on H8 (GEN-01), R10 (GEN-04), R12 (GEN-12)

### Step 4: docs
Files: plugin/crew/README.md, plugin/PLUGINS.md, docs/guides/crew/src/working-with-codex.md (+ rebuilt guides), .crew/codemap/crew.md, CHANGELOG.md, plugin/crew/BUDGETS.md
Test: `python3 docs/guides/crew/src/build.py`; crew-standards / QA suites; `python3 scripts/check-tooling-pr.py`; `python3 scripts/check-marketplace.py` after the commit
Risk: low
Standards: GEN-09
- [ ] README "Development standards" paragraph; PLUGINS.md `crew-qa-standards` row beside `crew-standards`; codex guide paragraph; codemap; CHANGELOG; BUDGETS re-measured
