---
name: crew-qa-standards
description: Harness and QA-review standards plus a report-only audit (parallel tests, serial wall-clock tests, fixture git isolation, pinned linters CI really runs, gate-first review). Use when setting up or onboarding a repo, or when asked to audit the harness, apply QA standards, or why CI or QA is slow, flaky or burning tokens.
---

# QA and harness standards

Two standards, each rule carrying the measurement that earned it and how to check and apply
it:

- [`references/harness.md`](references/harness.md): H1-H11, the test-and-lint harness, including the setup
  script that installs its tools (H8).
- [`references/review.md`](references/review.md): R1-R12, how an LLM review is run and how a PR reports.
- [`references/steward-template.md`](references/steward-template.md): the repo's PR-loop skill.
- [`references/recurring-findings.md`](references/recurring-findings.md): the defect classes earlier
  reviews kept finding, keyed by path globs. Not read whole: `hooks/scripts/recurring_findings.py`
  prints the classes a change's paths meet, to the implementer (`/crew:implement` step 2). Edit it in place; its suite holds each class to four probes and the block to its cap.

Read only the rule you are applying. Both files are long, and loading them whole to fix one
gap costs the tokens the standards exist to save.

## Applying them to a repo

1. **Audit.** It writes nothing:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-qa-standards/scripts/qa_audit.py --root .
   ```

   Every audited rule comes back PASS, GAP, N/A or **UNKNOWN**. UNKNOWN means the check could
   not tell (a pytest behind `make test`, no CI file found). Report it as unknown, never as a
   pass.
2. **Measure before fixing** (H1). Time the serial suite once before enabling parallelism,
   and time a linter before and after `-j`. A fix without a before/after number is not done.
3. **Fix one GAP at a time**, each through the repo's own gate, with the rule's evidence in
   the commit message. H4 and R10 fixes need a test that goes red with the fix removed.
4. **Record what you did not apply**, and why, in `.crew/STATUS.md`. A GAP left silently reads
   as one nobody saw.

## What the audit does not see

It reads CI files as text and Python tests as text. Other stacks' rules (paratest, JUnit
parallel mode, PHPStan baselines) and every rule not marked **[audited]** need a reader:
H1, H8-H11, R1-R8, R10, R12. For a crew repo, R1-R8 are what crew's own `/crew:review` enforces.
