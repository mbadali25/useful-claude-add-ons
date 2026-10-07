# Cloud handoff: L-0657

**CI fails when a built crew guide is stale**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

**BLOCKED: needs T-0048 merged first (it is still at spec), and T-0055 merged first.** Do not start until both are on main.

- **Role:** child ticket, split from T-0055, slice 1 of 1.
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Branch:** `L-0657-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0657/direction.md`, `docs/tickets/L-0657/spec.md`
- **Size:** about 15 production lines (`marketplace.yml` about 10, `scripts/gate-runner.py` about 5). No harness path. Nothing under `plugin/crew/` changes. Risk is marked low in the spec.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0048 | spec (not merged) | Provides `build.py --check` and `config_reference.py --check`, the two commands this ticket runs in CI. Neither exists on main. Must be merged first. |
| T-0055 | ready, not built (handed off 2026-10-04) | The parent slice. Adds the CI steps and the `CLAUDE.md` doc-rule paragraph this child extends. direction.md says it "should land first so the two CI edits do not conflict"; spec.md lists it under "must land first". The spec wins: it must land first. |
| T-0087 | merged | A dependency of the parent (the model checker and the tooling-PR rule). |

This ticket blocks nothing.

Family order:

1. T-0055: the docs-touched-or-declared check. Not blocked.
2. L-0657 (this ticket): after both T-0048 and T-0055 have merged.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published. The implementing session writes the plan.
- The names and exit codes of T-0048's two `--check` commands are taken from T-0048's spec, which is not on main. Re-read `build.py --check` and `config_reference.py --check` on main once T-0048 merges, before planning.
- If a `--check` command is wrong, that is a T-0048 fix. Do not change `build.py`, `config_reference.py` or any guide source or output here.
- Only HTML is compared; DOCX and PDF are not byte-reproducible.
- Whether the HTML is byte-stable across `markdown` versions and between the CI runner and the machine that built the committed guides: could not tell. Run the step on the ticket's PR; if it differs with nothing stale, pin the version; if it still differs, stop and report. Do not loosen the comparison.
- Keep `markdown` out of the pylint job; `.pylintrc` leaves it out on purpose.
- With `markdown` missing, the check must exit 2, not 0, and `gate-runner.py` must report SKIP, not PASS.
- The must-fail proof is shown once in the PR description with the CI run link, then reverted.

## Open questions for the owner (recommended option taken)

1. Pin the `markdown` version in CI? Default taken: yes, to the version the committed HTML was built with, because a different version can change the HTML and fail every PR. Which version that is: could not tell from the files; the implementer reads it from the environment that built the committed guides.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0657/` in the final PR unless the owner wants it kept. Per the spec this ticket changes nothing under `plugin/crew/`, so no crew version is needed unless that changes.
