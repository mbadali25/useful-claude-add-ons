# Cloud handoff: T-0502

**crew-setup ships a diagram check that renders as root, and its runners show why a check failed**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children). One of several siblings from the same report (T-0500, T-0501, T-0503, T-0106); all independent.
- **INDEX status:** direction (first handed to cloud on 2026-09-30; spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `T-0502-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0502/direction.md`, `docs/tickets/T-0502/spec.md`
- **Size:** about 110 added production lines under `plugin/` (the new case about 60, the two template runners about 20 together, skill and command Markdown about 30).
- **Harness:** no harness path. One feature PR. `.crew/verify.json` is in `ALONGSIDE` and no harness file is edited, so the tooling-PR rule is not engaged.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0088 | merged | Item 17 of the same report. Context only, not a blocker. |

Nothing must land first. Nothing blocks this ticket and it blocks nothing. It can be worked at any time.

Related, no forced order (siblings from the same report, all independent):

- T-0500 (approved): also edits crew-setup phase text. Whichever lands second merges main first.
- T-0501 (done), T-0503 (merged).
- T-0106 (direction, also handed to cloud on branch `T-0106-build`).

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- `docs/handoff/cloud/T-0502.md` and its row in `docs/handoff/cloud/README.md` are on main from the first hand-off (2026-09-30). The spec is newer and wins where they differ. This ticket's PR deletes that file and its row.
- The file named in the report, `_verify/cases/diagrams-parse.sh`, is not a crew template. It was written by hand in the reporting repository, and crew cannot patch it. The fix is on crew's side: a ready case, and runners that stop hiding output.
- The new case goes in `templates/cases/`, not under `templates/_verify/`. That tree is copied whole by setup, and a repo with no diagrams must not receive a case that fails.
- The case must not call into the plugin: `CLAUDE_PLUGIN_ROOT` is not set in a repo's CI or under the gate.
- No EUID branch: the `--no-sandbox` config is passed always, as `render.sh` does.
- Only the templates change. This repo's own `_verify/smoke.sh` and `_verify/run-all.sh`, `render.sh`, and the verify-gate scripts are not edited.
- Keep every line `plugin/crew/hooks/scripts/_test/setup-walkthrough.sh` greps byte-compatible (`PASS <name>`, `SKIP <name> (...)`, the `SMOKE:` and `REGRESSION:` prefixes, exit codes). The spec says not to run that walkthrough on a shared host: it writes under the system temp directory.
- `plugin/crew/commands/verify.md` is over its line budget and growth there is a hard fail. If the one added sentence cannot be offset inside the file, leave `verify.md` unchanged and put the pointer in `phases.md` and the template README.
- The three template scripts must be LF. See the repo CLAUDE.md landmine on `write_text` and CRLF.
- The tests use a fake `mmdc`. Real `mmdc` as root is not covered; the spec asks for one manual root run quoted in the PR body where a host has mermaid-cli, or a statement that no such host was available.
- The spec's last section says to run `/crew:plan T-0502` against it.
- The two "Owner decision 2026-09-30" sections in direction.md were written for local lanes. Merge, never rebase, still applies. The heavy-run wrapper is a local tool and is not in the repo; whether a cloud session needs an equivalent could not be told.
- No tests or gates were run when the spec was written.

## Open questions for the owner (recommended option taken)

1. `--no-sandbox` always (matches `render.sh`). Alternative: only when EUID is 0, the report's wording.
2. The runners print the last 5 lines of a failing check's combined output. A check that echoes a secret would show it in the gate log. Taken: accept. Alternative: print stderr only.
3. Exit 77 in the template runners is reported as SKIP and not counted as a failure (matches the gate). Alternative: `smoke.sh` keeps 77 as FAIL so a smoke run cannot be green on skips alone.
4. `plugin/crew/commands/verify.md` is over the command line budget where growth is a hard fail, so its one-sentence pointer is optional. Confirm that leaving `verify.md` unchanged is acceptable if the sentence cannot be offset.
5. Real `mmdc` as root is covered only by one manual run quoted in the PR body. Is that enough?

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0502/` in the final PR unless the owner wants it kept.
