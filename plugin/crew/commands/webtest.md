---
description: Drive Playwright's Test Agents inside the ticket lifecycle - a healer skip is a finding, never accepted
argument-hint: "<ticket id> [--stage spec|implement|heal|evidence]"
allowed-tools: Read, Edit, Write, Bash, Grep, Glob, Agent
---

Web tests for ticket $1. This is an EXECUTE step inside crew's lifecycle, not a
second planner: `/crew:spec` owns the acceptance criteria and `/crew:plan` owns
the plan. Playwright's three agents are invoked as they ship - never re-author,
wrap or paraphrase their prompts. Hand each one its input and its output path,
nothing else.

Background: `docs/review/07-web-testing-research.md` section 2.

## 0. Preconditions - stop and say which one failed

- A `playwright.config.*` at the root. None: point at `/crew:init`'s web phase
  (`webtest_scaffold.py`) and stop.
- `.claude/agents/playwright-test-planner.md`, `-generator.md`, `-healer.md`.
  Missing: same pointer. They must be regenerated on every Playwright upgrade.
- `.work/tickets/$1/spec.md` exists. Without a spec there is nothing to plan
  tests from - run `/crew:spec $1` first.

## 1. `--stage spec` - acceptance criteria to the planner

Run after `/crew:spec $1`, before `/crew:plan $1`. Read the spec's
`## Acceptance checks` and dispatch `playwright-test-planner` with exactly:
those checks, the seed test (`tests/seed.spec.ts`), and the output path
`specs/$1.md`. It needs the app running; if it is not, say so and stop rather
than letting it plan against an error page.

Then `/crew:plan $1` runs as normal. `specs/$1.md` is an input to it, and the
plan's Touch must name the spec files the generator will write.

## 2. `--stage implement` - the generator writes the tests

Inside `/crew:implement $1`, at the plan step that calls for web tests,
dispatch `playwright-test-generator` on `specs/$1.md`. The generated files are
the step's failing tests: run them, watch them fail for the right reason, then
implement. Check the files were actually written (a known Generator failure
mode is reporting success with no file on disk).

## 3. `--stage heal` - locator and wait repairs ONLY

A failing test goes to `playwright-test-healer` only when the failure is a
locator or a wait: a selector that no longer resolves, a race a web-first
`expect` fixes. An assertion that fails because the app is wrong is a bug in
the app - fix the app, never the test.

After EVERY healer run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_guard.py" skips --root . --ticket "$1"
```

Exit 1 means a skip site (`.skip`, `.fixme`, `test['skip']`, `test.fail(`, or a
`type: 'skip'|'fixme'|'fail'` annotation, split across lines or not) appeared
since the ticket's base in a JS/TS spec, a file under a test directory, or a
helper a spec imports - each file is read in full, renames included. **A
healer skip is reported as a finding, never accepted.** Print every
`FINDING|...` line verbatim to the user. Do not delete the skip quietly and do
not add it to the spec yourself: either the test is restored and the bug
fixed, or the owner adds a list item directly under the spec's `## Exclusions`
that begins `- skip: <path>` (or `- skip: <path> "<title text>"`) and
re-approves the plan; prose there is not an exclusion. Exit 2 means the check
could not tell - say so; it is not a pass.

## 4. `--stage evidence` - what the reviewer gets

```bash
npx playwright test --reporter=blob
npx playwright merge-reports --reporter html ./blob-report
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_guard.py" auth-leak --root .
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_guard.py" skips --root . --ticket "$1"
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_guard.py" visual --root .
```

Quote each exit code. `visual` exits 77 off the pinned image
(`mcr.microsoft.com/playwright:v1.63.0-noble`) - the env var alone is not
evidence; it needs a container marker and the image's `/ms-playwright`
browsers - report it as **UNVERIFIED**, never as passed. To verify, run the
suite in that image with Docker or Podman (same image, same flags; either's
marker counts): `podman run --rm --ipc=host -v "$PWD":/work -w /work -e
CREW_PLAYWRIGHT_IMAGE=<image> <image> npx playwright test --project=visual`.
With neither runtime installed the check says so. `auth-leak` exit 1
is a stop: a session file is tracked, or a `storageState` it cannot resolve
needs declaring as `webtest.storageState` in `.crew/config.json`.

Then `/crew:review $1`. Nothing extra to pass: `review_patch.py` lists the
newest trace zips and axe results under `test-results/` in the manifest
(bounded, the rest counted), and `review_prompt.py` hands the reviewer those
paths plus every healer-skip row as a FINDING. `review_run.py` re-runs the
skip check against the reviewed bundle before the verdict; any open row makes
the round FINDINGS, never CLEAN, and `review.json` carries them as
`webtest_findings`.

## 5. The verify rules

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_rules.py"
```

prints the canonical rules - suite exit code, merge-reports, axe with zero
violations, auth-leak, healer skips, visual-in-image-only. Merge them through
`/crew:verify`; do not hand-write variants.

## Report

One line per stage run: the stage, the agent dispatched (or none), files
written, each guard's exit code, and every FINDING line verbatim. End with
what was NOT verified - visual diffs on a host always are not.
