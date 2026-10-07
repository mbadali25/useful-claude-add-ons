# Cloud handoff: T-0093

**CLAUDE.md truncation paragraph: build_gallery.py:206 re-run can raise OverlayInvalid if a theme file changes mid-render (T-0091 round-2 NIT)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04). The intended path is `/crew:fix`, so the spec says no plan.md is needed.
- **Branch:** `T-0093-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0093/direction.md`, `docs/tickets/T-0093/spec.md`
- **Size:** 0 production lines. One documentation file, `docs/claude-md-evidence.md`, changes by roughly 10 lines.
- **Harness:** no. `docs/**` is not a harness path; the tooling-PR rule does not apply.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0091 | done (merged 2026-09-28, PR #252) | Wrote the paragraph and the sentence this ticket corrects. This ticket is its round-2 NIT. |

The spec also names commit `199defe8` (on main, no ticket id), which moved the paragraph from `CLAUDE.md` to `docs/claude-md-evidence.md`. The ticket facts and the spec agree.

Nothing blocks this ticket and it blocks nothing. It can be worked at any time.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor. The acceptance checks compare line numbers against the branch head, not against the spec.
- A stale plan.md is not published. No plan.md existed.
- The title still says CLAUDE.md, but the file to edit is `docs/claude-md-evidence.md`. `CLAUDE.md` must not change.
- The condition is narrower than the original review note said. Most theme-file changes do not raise. The spec's "Required content" section fixes the facts the new text must state; the wording is the implementer's.
- Reproduce the condition at the branch head before writing the text, in a throwaway copy made with `git archive`. Never run it in the checkout: it truncates a tracked `index.html`.
- Change only the truncation bullet. Do not rewrap lines the rewording does not change. Also correct the count sentence ("Six more were read one by one and none has ...").
- No code change, no version bump, no CHANGELOG entry, no new test or checker. The PR body carries `Docs: none - not a plugin/crew change`.
- The "take a crew version" step under "Before landing" does not apply here: the file belongs to no plugin.
- The direction file's older owner decision still applies: catch up with main by merge, never rebase.

## Open questions for the owner (recommended option taken)

1. Should direction option 2 (make `build_gallery.py` compute the HTML before opening `index.html`) be filed as its own doc-builder ticket? Taken: no; the document states the measured condition instead.
2. Should the INDEX title be corrected to name `docs/claude-md-evidence.md` instead of CLAUDE.md? Taken: left alone; the spec title carries the right path.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0093/` in the final PR unless the owner wants it kept.
