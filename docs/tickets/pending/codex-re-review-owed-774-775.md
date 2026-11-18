# Codex re-review owed on #774 (round 11) and #775

Priority: unassigned (owner to set).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's open-item list.
Siblings: `follow-up-775-own-failures-after-remerge.md`.

## Problem

The PR reviewer order is Codex, then Kimi, then Opus 5.5. #774 and #775 have so far been reviewed by Kimi k3 and by Sonnet 5.5 (the author's own pass), not by Codex. Codex `gpt-6-sol` was out of usage until Nov 20, 16:20 (owner's statement, not checked). So the preferred reviewer's verdict is still owed on both PRs.

## Evidence

VERIFIED by `gh pr view` on 2026-11-17: #774 head `4475eb86f`, draft, `mergeStateStatus` DIRTY, 4 failing checks (`check (3.12)`, `test (3.12)`, `crew-windows-default (6/6)`, `crew-shell-matrix (windows-latest)`). #775 head `bdebf07c2`, draft, UNSTABLE, 4 failing checks. The #775 body records Codex rounds 3 to 8 as earlier work, so Codex did review earlier heads; the owed item is a re-review of the current heads.

NOT verified: the round number "11" for #774 (owner's figure; #774's body was not read), the exact reviewer history of each PR.

## Recommended next step

After Nov 20, 16:20, run the Codex re-review on #774's head, then on #775's head once #775's own failures are fixed (re-review a head that is red only if the owner wants it). If Codex is still unavailable, follow the fallback order: Kimi, then Opus 5.5 (see the owner's reviewer-fallback note).

## Acceptance criteria

- A Codex verdict (BLOCK / FIX / NIT counts) is recorded on each PR for the head it reviewed, with that head's sha.
- Every BLOCK and FIX is fixed or answered; NITs are listed.
- The review is on a head that includes the final fixes (a later push means a re-review of the delta).

## Owner questions

1. Review #775 before or after its test failures are fixed?
2. Is a Kimi or Opus verdict acceptable to merge if Codex is still unavailable at merge time?

## Out of scope

Doing the fixes; merging (owner decision; approved order is #777, then #774 and #775 together, then #769, then #776).

## Related

#774, #775; the review harness `review_run.py` (not opened here).
