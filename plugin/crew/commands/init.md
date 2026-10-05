---
description: Guided phased setup for this repo — resumable, one phase at a time
argument-hint: "[--status | --phase N | --audit [--all-repos DIR]]"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent, Skill
---

Run the guided setup for this repository.

Follow `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/phases.md` exactly. It defines all
nine phases, the status file format, and the rules about stopping between phases.

Arguments: $ARGUMENTS
- `--status` — print the phase table from `.crew/STATUS.md` and stop
- `--phase N` — run that phase only, warning about incomplete prerequisites
- `--audit` — the QA audit only (`crew-qa-standards`): run
  `qa_audit.py --root .`, show the table verbatim with UNKNOWN as unknown, then `qa_doc.py --root .`
  (dry run) and offer `--write` once. Fix nothing unasked; offer `--stamp` after the report
- `--audit --all-repos DIR` — `qa_audit.py --all-repos DIR`: one line per crew checkout
- no argument — resume at the first phase not marked `done`

Phase 1 also runs `crew_gitignore.py apply --root .` (phases.md): language ignore patterns, added
without asking, only inside its managed block of `.gitignore`.

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
