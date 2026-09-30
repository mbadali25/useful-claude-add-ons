---
description: Guided phased setup for this repo — resumable, one phase at a time
argument-hint: [--status | --phase N]
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill
---

Run the guided setup for this repository.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/phases.md` exactly. It defines all
nine phases, the status file format, and the rules about stopping between phases.

Arguments: $ARGUMENTS
- `--status` — print the phase table from `.crew/STATUS.md`, then the checker's lines, and stop
- `--phase N` — run that phase only, warning about incomplete prerequisites
- no argument — run the checker, offer what it flags, then resume at the first phase not marked `done`

## Before resuming

For no argument and for `--status`, when `.crew/STATUS.md` exists, run the
checker before choosing where to resume and show its lines verbatim. It writes
nothing.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_setup_status.py" --root .
```

- exit 0 — nothing to re-verify.
- exit 1 — each `phase N ... - re-verify` line is a `done` row whose definition
  changed since it was marked, whose file does not say which crew it was marked
  against, or whose note may record a breakage. Offer them one at a time, in the
  order listed, before the first phase not marked `done`.
- exit 3 — could not tell. Quote the line and stop; do not resume past a status
  file the checker cannot read.

Every rewrite of `.crew/STATUS.md` - after any phase, under every argument form -
copies the version from the checker's `current crew:` line in as
`crew: <version>` after `updated:`.

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

It creates only what is missing and never overwrites: a Playwright config
(role/testid locators, web-first `expect`, `trace: 'on-first-retry'`, blob
reporter in CI, `snapshotPathTemplate` with `{platform}`, a `visual` project
that exists only inside the pinned image), an auth `setup` project, an axe
fixture, `playwright/.auth/` in `.gitignore`, the Test Agents (skipped when
`.claude/agents/playwright-test-planner.md` exists), `.mcp.json` entries for
`@playwright/mcp` and `chrome-devtools-mcp` (a `cmd /c` wrapper on Windows),
and the same two servers in `.codex/config.toml`. `.gitignore`, `.mcp.json`
and the Codex file are only ever added to.

Exit 1 means something was refused (an unparseable `.mcp.json`) or an
`init-agents` run failed - quote the line. Then run its `next:` line, and
propose the rules `webtest_rules.py` prints for Phase 5's verify map.
