# Triage of five stale open draft PRs: #770, #750, #753, #755, #647

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list. One combined ticket because none has a single concrete open question beyond "land, rework or close"; #757 is in `obsidian-basemode-nine-pr-plan-recall-harness-first.md`.

## State (VERIFIED by `gh pr view` on 2026-11-17)

| PR | Title (short) | Head | Base | Merge state | CI (failing checks) | Last update |
|---|---|---|---|---|---|---|
| #770 | `/crew:config --set --repo` from a linked worktree writes the main checkout's config (L-0946, 1.3.68) | `0a803bad6` | main | DIRTY | 30 of 30 pass | 2026-11-13 |
| #750 | AutoClear works in a pmux (psmux) pane on native Windows (1.3.41) | `579182a94` | main | DIRTY | 4 fail: `test (3.12)`, `crew-windows-default (1/6)`, `(3/6)`, `crew-shell-matrix (windows-latest)` | 2026-11-11 |
| #753 | `.crew/verify.json` production `requireHuman` true to false | `89efa36d4` | main | BEHIND | 19 pass, 3 skipped | 2026-11-11 |
| #755 | Windows trust-store seam venv is the interpreter the gate runs (tests only) | `d1da7570f` | `L-0888-trust-store` | DIRTY | 3 fail: `crew-windows-default (2/6)`, `crew-windows-wallclock`, `crew-shell-matrix (windows-latest)` | 2026-11-11 |
| #647 | L-0813 WIP: ship, install and check the Codex host wrapper | `931d2f2dc` | main | DIRTY | 5 fail: `test (3.12)`, `crew-windows-default (1/6)`, `(2/6)`, `(6/6)`, `crew-shell-matrix (windows-latest)` | 2026-10-18 |

All five are draft and open.

## Per-PR notes

- #770: green but conflicts with main (and, per its own history, with the version files). It names a root cause verified on main d7bd8b2e8 (crew 1.3.57). Needs a re-merge and a version re-bump (the repo's rule: content change needs a bump, above every open PR head). Open question: still wanted, or fixed elsewhere?
- #750: red on four checks, conflicts with main. Cause of the failures not read. Open question: still wanted given AutoClear changes since 1.3.41?
- #753: a one-line data change to `.crew/verify.json`. Body: owner decision 2026-11-10 to remove the human step from the production rung. Note: #730 (pre-production environments) has since merged, so the file may have moved: INFERRED, not checked. Open question: does the owner still want production `requireHuman` false, given that the three priority-D tickets keep approval for production commands?
- #755: stacked on `L-0888-trust-store` (#679, which MERGED on 2026-11-15; VERIFIED). Its base branch may no longer matter; it must be retargeted to main. Ownership unclear (owner's note); its session id matches #753/#757's, but who is driving it is not stated.
- #647: oldest (2026-10-18), "WIP", Phase 2 (version, CHANGELOG, docs cascade, gate, Codex/Kimi review) pending per its body. Open question: still wanted, and does it need the freeze exception again?

## Recommended next step

The owner marks each of the five: land (then re-merge, re-bump, re-gate), rework, or close. For anything kept, read the failing jobs first; do not assume they are inherited from main.

## Acceptance criteria

- Each PR has a recorded owner decision and, if kept, a named driver and a next step; closed PRs say why.
- No PR is left draft, red and unowned.

## Owner questions

1. Land, rework or close for each of #770, #750, #753, #755, #647?
2. Who owns #755?
3. #753: is production `requireHuman: false` still the intent?

## Out of scope

Doing the rework; merging.
