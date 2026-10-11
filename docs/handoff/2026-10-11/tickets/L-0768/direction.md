# L-0768: from a git worktree, promote-gate's review check reads the project dir's .crew/verify.json, not the deploying tree's

Type: bug
Status: in progress.
**OWNER DECISION 2026-10-10 (Matthew, given directly in the lane's session):** fix now, as an explicit
exception to the 2026-10 crew feature freeze (no new crew features until review Phase 1 lands). This
supersedes the triage note below.
**OWNER TRIAGE NEEDED:** bug fix vs feature under the 2026-10 crew feature freeze. Note that
promote-gate.sh:33-40 states this as a deliberate design ("Policy and state stay in the project dir,
deliberately: .crew/verify.json, ..."), so changing it is a policy change, not only a cwd fix.
Reported by: TSS-win session (crew 1.2.17, Windows), relayed by the coordinator 2026-10-10.
Related: L-0765 (promote-gate can never pass a main-tip release), L-0703 (review evidence in promote-gate),
T-0505 (which tree the gate judges).

## Report (substance)

- promote-gate.ps1:40-42 runs `Set-Location` to `$env:CLAUDE_PROJECT_DIR` (or `.`) at startup.
- `$tree` is resolved correctly from the tool call's cwd for the sha==HEAD and clean-tree checks.
- `Invoke-PromoteReview` (promote-gate.ps1:1096-1102 on origin/main e77532e0) starts `_promote_review.py`
  with `WorkingDirectory = (Get-Location).Path`, which is the project dir, not `$tree`. (`$tree` is passed
  as the first argument.)
- `committed_map_text()` (_promote_review.py:319-331) reads `.crew/verify.json` relative to the cwd and
  never uses the tree argument; its HEAD comparison (`git ls-tree HEAD`) is also the cwd's HEAD.
- Result: from a git worktree, the review check reads the MAIN checkout's verify.json. A `requireReview`
  waiver committed in the worktree or release branch is never seen.
- Reproduced by the reporter: `_promote_review.py` run by hand inside the worktree exits 0, while the
  hook's call with the same arguments blocks.
- Reporter's suggested fix: `WorkingDirectory = $tree`, and committed_map_text reads
  `git -C <tree> show HEAD:.crew/verify.json`.

## Does the bash flavour have it too? Yes (read only, origin/main e77532e0)

promote-gate.sh:60 runs `cd "${CLAUDE_PROJECT_DIR:-.}"`, the review call at promote-gate.sh:927-928 runs
`_promote_review.py "$TREE" "$FULL" ...` with no `cd "$TREE"`, so it inherits the project dir as cwd and
reads the same project-dir map. _promote_review.py's own docstring (lines 9-10) says it is "Run by BOTH
promote-gate.sh and promote-gate.ps1 from the project dir (the map is `.crew/verify.json` there)", and
promote-gate.sh:33-40 says the map, PROMOTIONS.md, approval markers and incident files stay in the project
dir on purpose (a throwaway worktree could hold a forged copy and launder a sha). Both flavours therefore
behave the same, and the behaviour is the documented design. The reported symptom is real, though: the
review requirement is judged against a map that is not the one committed in the tree being deployed.

## Unknowns

- Whether only the review-policy read (`ENVIRONMENTS.*.requireReview`) should follow the deploying tree's
  committed map (read with `git -C <tree> show <sha>:.crew/verify.json`, so it cannot be forged by an
  uncommitted edit) while the state files stay in the project dir.
- How this interacts with L-0765 (main-tip releases).

## Acceptance (draft, for spec)

- From a worktree whose committed `.crew/verify.json` sets `requireReview: false` with a `reviewReason` for
  an environment, both flavours honour it for a deploy run from that worktree; an uncommitted edit there
  still does not.
- From the main checkout, behaviour is unchanged.
- Must-block and must-allow regression cases for both flavours, sabotage-tested.
