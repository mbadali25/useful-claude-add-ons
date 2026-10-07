# L-0647: crew_ghdeploy.py record and the /crew:promote github sequence          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
L-0644 to L-0646 can prepare, find and judge a run, but nothing writes the result where crew's gates read it, and `/crew:promote` does not yet tell a session to use them. `.work/PROMOTIONS.md` is what `requires` and the Stop gate read, so a failed job's log pasted into it must never be readable as a pass row.

## Decision (kept from the owner's 2026-09-26 direction: "records pass or fail, with a failed job's log excerpt, in .work/PROMOTIONS.md")
`crew_ghdeploy.py record` appends a detail line for the dispatch and, on anything but pass, a `not-run` table row, the previous good sha for that environment and a sanitized excerpt of `gh run view --log-failed`. `/crew:promote` gate 2, for an environment with a `github` entry, runs prepare, the dispatch as its own Bash call, identify, watch and record, in that order. Rollback stays a person's choice: the record names the previous good sha and promote states the two options, as today.

## Options considered
1. **Detail lines and the excerpt in PROMOTIONS.md, every pipe character replaced (recommended, kept).** One file to audit; a line with no pipe cannot be read as a row.
2. Excerpt in a separate log file. Safer by construction, but the owner asked for it in PROMOTIONS.md.
3. No excerpt, only the run URL. Loses the reason once the run's logs expire.

## Depends on
L-0644 to L-0646.

## Open questions for the owner
- `promote.md` is at its 380-line allowance. Default: the sequence goes in a new sibling file of the crew-verification skill and promote.md points to it with no net growth. Alternative: raise the allowance.
- The attended evidence run needs the owner present and a consumer repository with a nonProd workflow. Default: it is evidence recorded after merge and install, not a merge gate.
