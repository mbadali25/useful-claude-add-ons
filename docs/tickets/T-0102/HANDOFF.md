# Cloud handoff: T-0102

**One marketplace reference skill: Linux tools on a Windows system, and SSM's limits (`skills/windows-ssm/`)**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** standalone ticket (no split children).
- **INDEX status:** direction (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session)
- **Priority:** med
- **Branch:** `T-0102-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0102/direction.md`, `docs/tickets/T-0102/spec.md`
- **Size:** about 125 added production lines: `skills/windows-ssm/scripts/ssm_output.py` about 110, the marketplace entry 6, the two install scripts 2 lines each, `scripts/gate-runner.py` 1, the workflow and `.crew/verify.json` a few. The three markdown files (about 400 lines together) are documentation.
- **Harness:** no harness path. One feature PR. Nothing under `plugin/crew/` changes, so there is no crew version bump and no crew document set.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0040 | merged (PR #290) | Crew's Windows shell routes. Context only: the new skill points to `shellRoute` and must not restate or contradict it. |
| L-0561 | merged | Registered `mailgun` and set the marketplace count to 35, the number this ticket moves to 36. |

Nothing open blocks this ticket and it blocks nothing: no INDEX row names T-0102. It can be worked at any time.

Related, no ordering: L-0632 (direction; diagram standard for other skills), L-0597 (done; Skill-Pipeline merge wording). Any other ticket that registers a skill moves the same count; whichever lands second merges main and re-counts.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor, and re-check that the marketplace still holds 35 skills before writing 36.
- No plan.md is published. The implementing session writes the plan.
- The direction first drafted on another machine on 2026-09-28 was never copied over. direction.md was rebuilt from the INDEX row, and spec.md is a first spec. If the earlier draft held decisions beyond the INDEX row, they are not reflected here.
- Registration must be whole, in one commit: the marketplace entry, both install scripts at the same position with the same text, both README table rows, `skills/UPDATE.md`, the four `skills-count` claims and the CHANGELOG. This is the repo's scope-discipline rule; a partial registration fails the checker.
- This is a public repository. No hostnames, account or profile names, instance ids, bucket names or customer data in any file. Examples use AWS's documentation placeholders only.
- Every number in `ssm-limits.md` carries an AWS or Microsoft documentation URL on the same row. A number with no URL is not written. No uncited truncation-marker string goes into the code or the reference.
- The helper is offline: no AWS call, no credentials, no file written, and it never prints the content it inspects. An output exactly at the limit counts as truncated; a non-terminal status is "could not tell". Only "complete" exits 0.
- The new test file needs a module name no other suite uses (two test directories with the same module name collide in the combined pytest run).
- The suite must be wired in three places that agree: `.crew/verify.json`, `scripts/gate-runner.py` and `.github/workflows/pytest-crew.yml`.
- `python3 scripts/check-marketplace.py` is run after the commit (its version-drift check compares commits).
- Re-pinning the README's install URLs is a separate step after the merge, not part of this PR.

## Open questions for the owner (recommended option taken)

1. Skill name: `windows-ssm`. Alternatives: `windows-linux-tools`, `ssm-limits`.
2. The truncation helper is in scope (the INDEX row calls it optional): an offline checker of about 110 lines with tests and CI wiring. If the owner says out, drop the helper, its tests and the three test-wiring files from Touch; the rest stands.
3. Output exactly at the limit (24,000 stdout / 8,000 stderr characters) cannot be told apart from cut output. Taken: treat as truncated, exit non-zero.
4. Default-on in the install menu, like every other skill. It registers no hook.
5. The earlier direction drafted on another machine was never copied over. If it holds decisions beyond the INDEX row, they are not reflected.

## Before landing

Merge origin/main, follow the repo's CLAUDE.md (scope discipline: every registration place in the same commit; no crew version is needed because `plugin/crew` is not touched; the new skill's own version is 1.0.0), and remove `docs/tickets/T-0102/` in the final PR unless the owner wants it kept.
