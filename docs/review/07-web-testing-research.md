---
title: Web testing tooling for crew 1.1
date: 2026-09-23
source: Claude Fable 5.1 researcher, vendor docs and registries fetched 2026-09-23
status: input to crew 1.1 (stack-web, /crew:webtest)
---

**Sourcing note:** Context7 is not exposed in this session (its tool surface never surfaced), so everything below comes from vendor docs, registries and GitHub source, fetched today (2026-09-23). Nothing in this repo was read.

## 1. Recommended toolset (versions as of 2026-09-23)

| Package | Version | Role |
|---|---|---|
| `@playwright/test` | 1.63.0 (released 2026-09-04) | test runner; bundles `npx playwright mcp` since 1.62 and Test Agents since 1.56 |
| `@playwright/mcp` | 0.0.82 | agent-driven browser; snapshot (a11y tree) mode default, `--caps vision` for x/y clicks, `--caps testing` for `browser_verify_*` assertions, `--isolated` + `--storage-state`, `--headless` (headed is default), `--save-session` |
| `chrome-devtools-mcp` | 1.10.1 (2026-09-23) | Puppeteer-based; `performance_start/stop_trace`, `performance_analyze_insight` (LCPBreakdown, DocumentLatency, CWV), `lighthouse_audit`, `list_network_requests`, `list_console_messages`, `emulate`; Node ^20.19 / ^22.12 / >=23 |
| `@axe-core/playwright` | 4.13.0 (axe-core ~4.13.0, peer `playwright-core >=1.0.0`) | `new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze()` as a fixture, attach results via `testInfo.attach()` |
| Docker image | `mcr.microsoft.com/playwright:v1.63.0-noble` | the only sane way to make Windows-authored and Linux-CI screenshots agree |

**Test Agents.** `npx playwright init-agents --loop=claude|codex|vscode|opencode` (Codex loop is in current docs). Per `generateAgents.ts`: the claude loop writes `.claude/agents/playwright-test-{planner,generator,healer}.md` plus `.mcp.json`; codex writes `.codex/agents/*.toml`; both point the MCP entry at `npx playwright run-test-mcp-server` (not `@playwright/mcp`). It also scaffolds `specs/` (Markdown plans) and `tests/seed.spec.ts`. Docs say regenerate the definitions on every Playwright upgrade. Planner needs a running app plus the seed test; Healer re-runs until green or "guardrails intervene" and may mark a test skipped if it decides the feature is broken.

## 2. Design

**`stack-web` skill** (activated when `playwright.config.*` exists):
- Encodes the rules: `getByRole`/`getByTestId` only, web-first `expect`, `trace: 'on-first-retry'`, `reporter: CI ? 'blob' : 'html'`, auth via a `setup` project writing `playwright/.auth/*.json` (gitignored; one account per `parallelIndex` if tests mutate state), screenshots with `snapshotPathTemplate` containing `{projectName}`/`{platform}`, `animations:'disabled'` (default), `mask`/`stylePath` for volatile regions, and a stated policy that baselines are generated only inside the pinned Docker image.
- MCP wiring: project-scope `.mcp.json` with `playwright` (`--isolated --headless --caps testing`) and `chrome-devtools` entries; Windows entries use `"command":"cmd","args":["/c","npx",...]` (Chrome DevTools MCP troubleshooting documents this for the "Connection closed" failure). Codex mirror in `.codex/config.toml` (`[mcp_servers.x]`, trusted-project only).

**`/crew:webtest`** is the execute step, not a planner. Crew's spec → plan already exists, so: (1) `spec` phase hands the acceptance criteria to `playwright-test-planner`, which writes `specs/<ticket>.md`; (2) `plan` phase is crew's own; (3) `implement` calls `playwright-test-generator` on that spec; (4) failures go to `playwright-test-healer`, but only for locator/wait repairs; a Healer "skip" is reported as a finding, not accepted; (5) reviewer gets the trace zip and axe attachment. The Playwright agents are subagents that crew *invokes*; do not re-author their prompts.

**`verify.json` rules:** `npx playwright test --reporter=blob` (exit code), `npx playwright merge-reports --reporter html ./blob-report`, an axe project with zero `violations`, `git ls-files playwright/.auth` must be empty, and `toHaveScreenshot` diffs ≤ configured `maxDiffPixelRatio` inside the Docker image only (skip visual on host).

**Install steps** (both scripts, same order): Node ≥ 20.19 check → `npm i -D @playwright/test@1.63.0 @axe-core/playwright@4.13.0` → `npx playwright install --with-deps chromium` → `npx playwright init-agents --loop=claude` and `--loop=codex` (idempotent: detect `.claude/agents/playwright-test-planner.md`) → write `.mcp.json`/`.codex/config.toml` with the `cmd /c` wrapper on Windows → Docker presence check for visual baselines.

## 3. Alternatives and why Playwright wins for validation

- **Claude in Chrome** (`claude --chrome`): shares your logged-in browser, pauses on CAPTCHA/login, not supported in WSL, needs `/login` on a direct Anthropic plan, tools always loaded increase context. Good for exploratory checks; produces no repeatable artifact, no CI path.
- **Stagehand** (v4, act/extract/observe, CDP-native, TS/Py/Go) and **browser-use** (CDP since 2025-08-20) both state they target agents, not testing; nondeterministic LLM steps make them poor verify-gate inputs.
- **webcmd** 0.8.4 (Node ≥ 20.6): compiles learned site navigation into deterministic CLI commands; agent-oriented, closed benchmarks, young.
- Playwright wins because the artifact is a deterministic test, a trace and a blob report a CI gate can rerun and a reviewer can read. Chrome DevTools MCP is complementary (perf/CWV), not a replacement.

**Visual regression alternatives:** Lost Pixel was archived 2026-04-22 (team joined Figma); Argos is MIT and has `@argos-ci/playwright` but self-hosting is undocumented; BackstopJS/reg-suit are older. Stay on `toHaveScreenshot` in Docker.

## 4. Risks

- The Generator has a documented failure to write files in one loop (issue #38068, closed not-planned, 2025-10-30); expect to re-check after each Playwright upgrade, since agent files must be regenerated.
- Healer can silently `skip` a test that is actually catching a bug.
- `@playwright/mcp` is still 0.0.x; flags move between releases.
- `--caps vision` and Claude in Chrome both expose prompt-injection surfaces on live sites.
- Cross-OS `merge-reports` needs an explicit `--config` to disambiguate tests root.

## Sources (verified, fetched today)

- https://playwright.dev/docs/test-agents — loops, seed test, regenerate-on-upgrade, Healer guardrails
- https://raw.githubusercontent.com/microsoft/playwright/main/packages/playwright/src/agents/generateAgents.ts — per-loop output paths, `run-test-mcp-server`
- https://playwright.dev/docs/release-notes — 1.56 agents, 1.62 bundled MCP, 1.63 aria trace; https://github.com/microsoft/playwright/releases — 1.63.0 on 2026-09-04
- https://raw.githubusercontent.com/microsoft/playwright-mcp/main/README.md — flags, `--caps testing`, Claude/Codex snippets, Windows profile path; https://registry.npmjs.org/@playwright%2Fmcp/latest — 0.0.82
- https://github.com/ChromeDevTools/chrome-devtools-mcp/releases (1.10.1, 2026-09-23); .../docs/tool-reference.md; .../docs/troubleshooting.md (`cmd /c`, WSL)
- https://playwright.dev/docs/test-snapshots, /docs/api/class-pageassertions, /docs/auth, /docs/best-practices, /docs/test-sharding, /docs/docker, /docs/accessibility-testing
- https://registry.npmjs.org/@axe-core%2Fplaywright/latest (4.13.0); .../@agentrhq%2Fwebcmd/latest (0.8.4)
- https://code.claude.com/docs/en/chrome; https://code.claude.com/docs/en/mcp; https://learn.chatgpt.com/docs/extend/mcp?surface=cli
- https://github.com/browserbase/stagehand; https://browser-use.com/posts/playwright-to-cdp (2025-08-20); https://github.com/agentrhq/webcmd; https://github.com/lost-pixel/lost-pixel; https://github.com/argos-ci/argos; https://github.com/microsoft/playwright/issues/38068

**Unverified / secondary:** Playwright MCP v0.0.82 release *year* (the releases page rendered "2024", which contradicts its WebMCP content; treat as 2026-09-18). webcmd BU Bench claims are vendor-reported. Argos self-hosting: docs page 404.

**Not checked:** Playwright Python agents (issue #38610 open), `@playwright/mcp` Windows-specific bugs beyond the profile path, Codex CLI Windows `cmd /c` behaviour, Chrome DevTools MCP headless flags.