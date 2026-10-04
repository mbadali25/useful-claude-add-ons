# L-0688 - direction: refresh admission refuses an artifact removed from the index

Split from L-0540 on 2026-10-04. Status: seed (not yet approved). Feature PR, no harness path. **Lands before L-0540.**

## Problem

`crew_refresh_check.artifact_verdicts` returns `True` for an artifact that was removed from the git index but left in the working tree with a forward re-anchor. The commit then records the deletion of a file the verdict called a re-anchor. T-0094 review round 8 reported it as a BLOCK; the owner accepted the round on 2026-09-30 and required the fix before the completion audit calls `artifact_verdicts` (L-0540 direction.md, "MUST-FIX").

Repro from the review: on an anchored map run `git rm --cached .crew/codemap/app.md`, leave the file on disk with a reachable forward anchor, call `artifact_verdicts`. It returns True although `git ls-files -s` prints nothing for the path.

Checked at origin/main `155fe6d8`: `_on_disk` skips every raw diff record with `000000` on either side (plugin/crew/hooks/scripts/crew_refresh_check.py:829-833) and treats an empty `ls-files -s` like a new file (:834-842). Nothing reaches the hole today, because no hook calls `artifact_verdicts`.

## Why it is its own ticket

crew_refresh_check.py is outside `HARNESS` and `ALONGSIDE` in scripts/check-tooling-pr.py, so the fix cannot ride in L-0540's tooling-only PR. For the same reason the module docstring's interim sentence about L-0540 (:122-127) can only be changed here.

## Options

1. **Recommended, taken.** In `_on_disk`, refuse when the `--cached` diff against the base shows the path going to mode `000000`: the base holds it and the index does not. A path with no base copy and no index entry (a new, untracked rendered file) stays as today.
2. Refuse every artifact with an empty `ls-files -s`. Rejected: it refuses a new rendered diagram before `git add`, which the Stop hook sees in the middle of a refresh.
3. Compare the index blob with the bytes read. Wider than the finding; not needed to close it.

## Open questions for the owner

- A staged-but-different index copy (index bytes differ from disk bytes) is still judged from disk. Out of scope here; say if it should be a follow-up.
