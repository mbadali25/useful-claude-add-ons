---
name: crew-qa-standards
description: Harness, QA-review and environment standards plus a report-only audit (parallel tests, pinned linters CI really runs, gate rules that can fail, QA environment isolation, rehearsed rollback, deploys that fail loudly) and a generated QA-process doc with diagrams. Use when setting up, onboarding or upgrading a repo, when the qaAuditStale trigger fires, or when asked to audit the harness or QA environments, apply QA standards, document the QA process, or why CI or QA is slow, flaky or burning tokens.
---

# QA and harness standards

Three standards, each rule carrying the measurement that earned it and how to check and apply
it:

- [`references/harness.md`](references/harness.md): H1-H11, the test-and-lint harness, including the setup
  script that installs its tools (H8).
- [`references/review.md`](references/review.md): R1-R12, how an LLM review is run and how a PR reports.
- [`references/environments.md`](references/environments.md): G1-G5 and E1-E7, gate rules that
  can fail and QA environments that are isolated, rehearsed and deployed loudly (L-0618).
- [`references/steward-template.md`](references/steward-template.md): the repo's PR-loop skill.
- [`references/recurring-findings.md`](references/recurring-findings.md): the defect classes earlier
  reviews kept finding, keyed by path globs. Not read whole: `hooks/scripts/recurring_findings.py`
  prints the classes a change's paths meet, to the implementer (`/crew:implement` step 2). Edit it in place; its suite holds each class to four probes and the block to its cap.

Which skill owns which rule (L-0519): code-level rules and the self-check are
crew-standards; harness, review-process, gate and environment rules are
crew-qa-standards. crew-qa-standards' `recurring-findings.md` (RF) is a
probe index derived from crew-standards: each class names the standard ids it
echoes, and on a conflict the standard wins and the probe is corrected.

Read only the rule you are applying. The files are long, and loading them whole to fix one
gap costs the tokens the standards exist to save.

## Applying them to a repo

1. **Audit.** It writes nothing:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-qa-standards/scripts/qa_audit.py --root .
   ```

   `--all-repos <dir>` prints one line per crew checkout under `<dir>` instead: setup phase,
   GAP and UNKNOWN counts, and whether D10 (rules skipped on every Stop) is live.

   Every audited rule comes back PASS, GAP, N/A or **UNKNOWN**. UNKNOWN means the check could
   not tell (a pytest behind `make test`, no CI file found). Report it as unknown, never as a
   pass.
2. **Measure before fixing** (H1). Time the serial suite once before enabling parallelism,
   and time a linter before and after `-j`. A fix without a before/after number is not done.
3. **Fix one GAP at a time**, each through the repo's own gate, with the rule's evidence in
   the commit message. H4 and R10 fixes need a test that goes red with the fix removed.
4. **Record what you did not apply**, and why, in `.crew/STATUS.md`. A GAP left silently reads
   as one nobody saw. During setup, a phase with an open GAP is `partial`, never `done`.
5. **Stamp and document.** `qa_audit.py --root . --stamp` records the audited HEAD in
   `.crew/.qa-audit-at`; the `qaAuditStale` session trigger fires when there is no stamp, or when
   `.crew/verify.json`, `_verify/`, CI or `.gitignore` moved since it. Then
   `qa_doc.py --root .` (dry run; `--write` to apply) writes `docs/qa/README.md` with its Mermaid
   diagrams embedded, `docs/qa/qa-process.html`, and the `.mmd` sources under `docs/diagrams/`.
   It refuses to overwrite a file it did not generate.

## When it runs

| Trigger | What runs |
|---|---|
| `/crew:init` Phase 5 and Phase 8 | the audit; a phase with an open GAP is `partial`, never `done` |
| `/crew:init --audit` | the audit alone, then the doc dry run |
| `/crew:upgrade` | the audit as a report, after the codemap migration |
| `qaAuditStale` at session start | no stamp yet, or an audited path moved since the stamp |

None of these is a hook that blocks. The audit reports; the gate stays what `.crew/verify.json` says.

## What the audit does not see

It reads CI files as text and Python tests as text. Other stacks' rules (paratest, JUnit
parallel mode, PHPStan baselines) and every rule not marked **[audited]** need a reader:
H1, H8-H11, R1-R8, R10, R12, and the reader items in `environments.md`. Anything that needs the
deployed target to answer (deployed identity, alarm subscriptions, test identities) is a reader's
item: the audit never calls a remote host. For a crew repo, R1-R8 are what crew's own `/crew:review` enforces.
