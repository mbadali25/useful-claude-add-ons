---
description: Guided phased setup for this repo — resumable, one phase at a time
argument-hint: [--status | --phase N]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill
---

Run the guided setup for this repository.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/phases.md` exactly. It defines all
nine phases, the status file format, and the rules about stopping between phases.

Arguments: $ARGUMENTS
- `--status` — print the phase table from `.crew/STATUS.md` and stop
- `--phase N` — run that phase only, warning about incomplete prerequisites
- no argument — resume at the first phase not marked `done`

After each phase, if `notify.provider` is configured, send one line:
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/notify.sh phase "Phase N <state>"`

## Web phase (inside Phase 6, Browser tests)

When the repo has a `playwright.config.*`, an `angular.json`, or a
`package.json` naming Playwright, offer ONE confirmed step. First the dry run,
which writes nothing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_scaffold.py" --root .
```

Show its output verbatim and ask once. Only on yes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_scaffold.py" --root . --apply
```

A root that is not a web project itself prints `n/a` and one `module` line
per web project below it (three levels, `node_modules` and dot-directories
skipped). For each module, the same two steps with `--module <dir>` added:
dry run, show it verbatim, ask once, apply on yes. The test files, config and
`.gitignore` lines land in the module, under its config's `testDir`; the
Test Agents, `.mcp.json` and `.codex/config.toml` land at the root, where a
session loads them.

It creates only what is missing and never overwrites: a Playwright config
(role/testid locators, web-first `expect`, `trace: 'on-first-retry'`, blob
reporter in CI, `snapshotPathTemplate` with `{platform}`, a `visual` project
that exists only inside the pinned image), an auth `setup` project (only when
`.crew/secrets.md` or a declared `storageState` records credentials), an axe
fixture, `playwright/.auth/` in `.gitignore`, the Test Agents (skipped when
`.claude/agents/playwright-test-planner.md` exists), `.mcp.json` entries for
`@playwright/mcp` and `chrome-devtools-mcp` (a `cmd /c` wrapper on Windows),
and the same two servers in `.codex/config.toml`. `.gitignore`, `.mcp.json`
and the Codex file are only ever added to. An existing config is never
edited: each project it lacks is a `gap` line with a snippet to paste.

Exit 0 is done, including advisory `gap` and `skip` lines - quote them. Exit
1 means something was refused (a `--module`, a `testDir` it could not read, an
unparseable `.mcp.json`) or an `init-agents` run failed - quote the line.
Exit 2 is usage. Then run its `next:` line, and propose the rules
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/webtest_rules.py" --root .`
prints (add `--module <dir>` for a module) for Phase 5's verify map; quote
each `omitted` line it prints on stderr as a rule waiting on that gap.
