# Cloud handoff: L-0684

**gizmoduck tool lookup: one tool home, and an explicit override beats PATH (item 10 of a report from another repository's session)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** child ticket, split from T-0108, slice 1 of 2 (the other is L-0685).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0684-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0684/direction.md`, `docs/tickets/L-0684/spec.md`
- **Size:** about 110 production lines (`base.py` 35, `zap.py` 25, `nikto.py` 20, `testssl.py` 15, `gizmoduck.py` 15). The parent's direction says about 100; the spec's figure is used. No harness path, and `plugin/crew` is untouched: this is a gizmoduck-only feature PR. Risk is marked med in the spec.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0107 | done (merged as PR #273, gizmoduck 0.5.5) | The routine CLI and the sanitised-environment tests this ticket edits. |
| L-0599 | done (merged as PR #315, gizmoduck 0.5.6) | The version this family bumps from. |

Nothing open blocks this ticket. It blocks L-0685, which installs into the tool home defined here.

No hard dependency on T-0108 (the parent; safe Nuclei defaults). Both edit `gizmoduck.py`, the README and the version files: land one, merge origin/main into the other (merge, never rebase), bump again.

Family order:

1. T-0108 first, as the parent's direction recommends (a recommendation, not a code dependency).
2. L-0684 (this ticket).
3. L-0685: needs L-0684 merged first.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- The report's wording is not what the code does: neither adapter looks at `LOCALAPPDATA` first. The real defect is that PATH beats the explicit override, a broken override falls through silently, and Linux has no tool home. The spec is built on that.
- Nothing was run when the spec was written.
- First implementation step: the autouse fixture in `conftest.py` that points `GIZMODUCK_HOME` at an empty temp directory and clears the override variables and `XDG_DATA_HOME`, so no test reads the real home. Then run the whole gizmoduck suite.
- The override state is three-valued (`unset` / `ok` / `broken`) and read at call time, never at import. A broken override never falls through.
- The ZAP archive layout (whether `zap.sh` sits one level down) is resolved at implement time by reading what the archive extracts.
- Two behaviour changes to flag in the CHANGELOG: a set override now beats PATH; a set but stale override now disables the tool.
- The version to bump is gizmoduck's, in `plugin/gizmoduck/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` and `plugin/PLUGINS.md`. The crew version is not bumped. The PR body says `Docs: none for crew - gizmoduck only`.
- Sabotage is by hand, quoted in the PR.

## Open questions for the owner (recommended option taken)

1. A set-but-broken override disables the tool instead of falling through to PATH. Alternative: warn and fall through.
2. Default tool home is `~/.local/share/gizmoduck` (XDG). Alternative: `~/.gizmoduck`.
3. testssl is included although the report names only ZAP and nikto, because it has the identical defect. Alternative: a follow-up.
4. The tool home's `bin` is searched ahead of PATH. Alternative: PATH first.
5. Accepted as risk in the spec: whether anyone relies on PATH beating a set override could not be told from the repo.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0684/` in the final PR unless the owner wants it kept. For this ticket the version taken from the coordinator is gizmoduck's, not crew's.
