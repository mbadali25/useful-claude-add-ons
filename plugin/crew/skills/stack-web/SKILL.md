---
name: stack-web
description: |
  Playwright web UI testing pitfalls, checks and verify.json wiring - role/testid locators,
  web-first assertions, trace and visual-baseline discipline, accessibility via axe. Use when
  the repo has playwright.config.* or @playwright/test, an Angular e2e suite, or the user asks
  to write, review or debug a browser/UI test, a flaky selector, a screenshot diff, or web
  accessibility checks.
---

# Stack: Web testing (Playwright)

## When this applies

Any repo with `playwright.config.*` or `@playwright/test` in `package.json`, including an
Angular e2e suite. Pin `@playwright/test@1.63.0` and `@axe-core/playwright@4.13.0` - both
version-gate flags and fixtures used below.

## Pitfalls that cost time

- **Locate by role or test id, never by CSS/XPath.** `getByRole`/`getByTestId` survive a
  markup refactor; a class-name selector does not, and it fails silently as "element not
  found" rather than naming what changed.
- **Web-first `expect` (`await expect(locator).toBeVisible()`), never a bare assertion on a
  value read once.** Playwright's web-first matchers auto-retry until the page settles; reading
  a value first and asserting on it races the render.
- **`trace: 'on-first-retry'`, not `'off'` and not `'on'` for every run.** `'off'` leaves a
  flaky failure with nothing to open; `'on'` for every run makes the report enormous. CI uses
  `reporter: 'blob'` per shard, merged afterward - the default HTML reporter does not merge
  across shards.
- **Auth goes through a `setup` project that writes `playwright/.auth/*.json`, and that path is
  gitignored.** A committed storage-state file leaks session tokens and goes stale the moment
  the account's session rotates; `git ls-files playwright/.auth` must return nothing.
- **Visual baselines are generated ONLY inside `mcr.microsoft.com/playwright:v1.63.0-noble`.** A
  baseline captured on a host OS (font hinting, subpixel rendering) never matches CI's container
  and `toHaveScreenshot` fails on every run afterward for reasons unrelated to the change under
  test. `snapshotPathTemplate` includes `{platform}` so a host-captured baseline cannot silently
  shadow the container one under the same filename.
- **Accessibility is a fixture, not an afterthought.** `new AxeBuilder({ page })
  .withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze()`, attached via
  `testInfo.attach()` so the reviewer sees the violation list, not just a boolean.
- **A Healer "skip" is a finding, not a pass.** `/crew:webtest`'s generator loop may hand a
  failing test to `playwright-test-healer`; if it marks the test skipped rather than fixing the
  locator/wait, report that to the reviewer - it is exactly as reportable as a failing test.

## MCP wiring

Project-scoped `.mcp.json` (not a verify.json rule - shown unlabelled so the skill test's
JSON-rule scan does not treat it as one):
```
{
  "mcpServers": {
    "playwright": { "command": "npx", "args": ["@playwright/mcp@latest", "--isolated", "--headless", "--caps", "testing"] },
    "chrome-devtools": { "command": "npx", "args": ["chrome-devtools-mcp@latest"] }
  }
}
```
On Windows, `npx` is not directly executable by the MCP host - wrap both entries as
`"command": "cmd", "args": ["/c", "npx", ...]` (documented in chrome-devtools-mcp's own
troubleshooting for the "Connection closed" failure). Mirror both servers in `.codex/config.toml`
under `[mcp_servers.<name>]` for a trusted project.

## verify.json rules

The canonical rule set lives in `plugin/crew/hooks/scripts/webtest_rules.py` (written in
parallel by another lane; if the final path differs, treat this reference as the one to fix on
integration, not the rule itself). It wires: `npx playwright test --reporter=blob` for exit
code, `npx playwright merge-reports --reporter html ./blob-report` to produce the reviewer
artifact, an axe project asserting zero `violations`, `git ls-files playwright/.auth` asserting
empty, and `toHaveScreenshot` diffs bounded by `maxDiffPixelRatio` - run only inside the pinned
Docker image, skipped (not failed) on a bare host. `/crew:webtest` drives the planner ->
generator -> healer loop against a ticket's acceptance criteria; see that command for the phase
sequence.

## Verification

Run what the repo runs - `npx playwright test`, reporting the exit code and the trace/blob
report path, never a summary line. A rule proposed for `verify.json`:

```json
{
  "paths": ["playwright.config.*", "**/*.spec.ts", "tests/**/*.ts", "e2e/**/*.ts"],
  "run": [
    "sh -c 'P=node_modules/.bin/playwright; [ -x \"$P\" ] || P=$(command -v playwright 2>/dev/null); if [ -z \"$P\" ]; then echo \"TOOL MISSING: playwright is not installed locally (checked node_modules/.bin and PATH) - npx would try to download it rather than reporting UNVERIFIED. Run npm install to check locally.\" >&2; exit 77; fi; \"$P\" test --reporter=blob'"
  ],
  "reach": "local",
  "why": "a rerunnable trace and blob report a reviewer can open, not a summary line"
}
```

The probe checks for an already-installed `playwright` binary (local `node_modules/.bin` first,
then `PATH`) rather than a bare `command -v npx`, matching this repo's other stack-* rules -
`npx <missing-pkg>` on a modern npm reaches the registry rather than failing closed.

Nothing in this repo writes rules into `verify.json` on a skill's behalf (see the
`crew-verification` skill) - add this by hand.
