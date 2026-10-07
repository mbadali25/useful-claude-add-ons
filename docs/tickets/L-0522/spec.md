# L-0522: Delta gate: a catch-up merge that adds none of the ticket's own code keeps the review receipt; version bump and refresh run BEFORE the gate so L-0512's tree cache can hit          status: spec   risk: high
Reconstructed 2026-10-05 (the original spec and plan were lost with a removed lane worktree). Written against
origin/main `a555ff37` and `L-0522-tooling` `ddd9b2a7` (marked TB, branch-only). PR 1 (#377, landing order) is
merged; this spec covers **PR 2** (the delta gate, tooling-only) and **PR 3** (a later slice, feature/docs).
`L-0522-tooling` forks from `f691c54c` and is about 1594 commits behind main: re-find every anchor by content
after merging origin/main.

## Intent
**PR 2.** When `review_ledger.check_receipt` finds the rebuilt bundle's hash differs from the receipt's, it asks
`review_delta.judge` before answering stale. The gate keeps the receipt only when it proves the ticket's own
delta is byte-identical to the reviewed one: the reviewed head is a commit whose tree rebuilds the reviewed
bundle, it is an ancestor of HEAD, the integration base is one commit bound to the ticket's merge-train entry
(or a pinned `base_sha`), there is one merge base, the checkout is clean, the bundle-excluded paths are unchanged
(check E, which also guards the fast path), and every path outside a fixed allowlist has equal status, modes and
blob ids in both deltas. The allowlist: code maps, rules and diagrams may move only their anchor sha; CHANGELOG,
TODO, PLUGINS.md and BUDGETS.md are exempt; manifests may move only the bumped plugin's version tokens. Anything
unproven reads stale, with "could not tell" as its own reason. Owner decision 2026-10-03: it ships
**fail-closed**; in a clone whose merge train is not armed it keeps nothing (`no train entry binds the
integration ref`). A kept receipt prints `receipt kept by delta gate: ...`. `review_run.preflight` short-circuits
on a delta-kept CLEAN only with a VERIFIED or NO_GATE gate. `crew_autopilot` routes a refresh that moved more than
an anchor to a human stop.

After merging main, PR 2 also: (1) rebuilds the reviewed bundle in judge step 2 through `review_patch`'s own
T-0100 tree logic (synthetic merged-main base), not a plain `git diff`, so a receipt written after a catch-up can
be reproduced; (2) stops claiming that `check_land` passes its fetched sha (PR 3 wires it).

**PR 3 (later slice, branch `L-0522-docs`).** `/crew:done` check 1 says a receipt may be kept by the delta gate,
what that line means and that it needs an armed train; the README's receipt paragraph says the same and drops
"a delta gate - until one exists"; `check_land` passes the base sha it fetched into `check_receipt`.

The title's second half (bump and refresh before the gate) shipped in PR 1. Its rationale (L-0512's tree cache)
is gone: L-0512 was dropped 2026-10-02, and the tree-pass cache that landed keys on HEAD.

## Exclusions
- PR 2 carries no feature code: no edit to `crew_train.py`, `done.md` or any production file outside `HARNESS`,
  except the declared `SEAM` path `crew_autopilot.py` (trailer `Tooling-seam:` already on `44641776`).
- No arming of the merge train, no fallback to `scope_base._default_ref` or any guessed ref.
- No widening of the allowlist beyond the classes above. No exemption for any `plugin/*/` code, command, skill
  or prompt file.
- Not L-0620: a catch-up that edits a ticket file main also edited, resolved back to the reviewed bytes, stays
  stale here (the follow-up keeps it).
- No change to the bundle hash, `review_patch.EXCLUDED` or the T-0100 merged-main rule.
- No change to review budget, refund, auto-accept (L-0510) or the reviewer prompt beyond `review.md`'s receipt
  sentence.
- No rebase or force-push of `L-0522-tooling`: catch up by merge.

## Evidence
origin/main `a555ff37` unless marked TB (`L-0522-tooling` `ddd9b2a7`):
- `check_receipt(root, ticket)` `plugin/crew/hooks/scripts/review_ledger.py:856`; CLI `--check-receipt` `:1028`.
  TB: `check_receipt(root, ticket, base_sha=None)` `:834`, check E before both success returns, `review_delta.judge`
  on a hash mismatch, kept line `receipt kept by delta gate:`.
- TB `plugin/crew/hooks/scripts/review_delta.py` (711 lines): module docstring lists check E and steps 1-9;
  `tree_bundle_sha256` `:187` (plain `git diff` + `split_parts`, pre-T-0100); `excluded_check` `:234`;
  `valid_base_sha` `:255`; `integration_ref` `:269` (imports `crew_train`, stale when `crew_train.load` gives no
  entry); `judge` `:644`, `_judge` `:656` (calls `integration_ref` unconditionally `:666`, so a pinned `base_sha`
  does not bypass the train). Allowlist constants `EXEMPT_ANCHORED`, `EXEMPT_PROSE`, `EXEMPT_MANIFEST` at the top.
- T-0100 on main: `review_patch._ticket_base_tree` `plugin/crew/hooks/scripts/review_patch.py:271`
  (`merged_main.resolve` `:281`), `bundle_sha256(parts)` `:366` (patch parts only), manifest `merged_main` and
  `bundle_base_tree` `:463`; `merged_main.resolve` `plugin/crew/hooks/scripts/merged_main.py:67`. Not on TB.
- `crew_train.LANDING_ORDER` `plugin/crew/hooks/scripts/crew_train.py:1235` (PR 1); `check_land` `:1240` calls
  `review_ledger.check_receipt(top, ticket)` with no base `:1279`.
- Other callers: `crew_autopilot.py:452`, `:528`, `:1271` (main); TB keeps one at `:528`, so main's two new call
  sites must be judged after the merge.
- Tree-pass cache `plugin/crew/hooks/scripts/verify-gate.sh:1372` (`verify_record.passes_load` `verify_record.py:667`):
  keyed on HEAD and every ref, Stop only. L-0512 dropped (INDEX row, 2026-10-02).
- `HARNESS` `scripts/check-tooling-pr.py:58` (`review_*.py`, `sabotage*.py`, `commands/review.md`), `SEAM` `:89`
  (`crew_autopilot.py`), `ALONGSIDE` `:99` (tests, README, docs, codemap, verify.json, version files).
- Main README "a delta gate - until one exists" `plugin/crew/README.md:791`; receipt paragraph `:772`.
- `/crew:done` check 1 `plugin/crew/commands/done.md:10-17` ("Rebuilds the bundle and fails if anything changed").
- Verify rules on main: `.crew/verify.json` rule 39 (`test_review_*.py`), 43 (`test_crew_train.py`), 44 (harness:
  check-tooling-pr, tooling-pr suite, golden, contracts, canary).
- Ledger: L-0522 `ACCEPTED`, rounds_left 0, receipt round 2 CLEAN, head `f691c54c`, base `8123fe74`; both rounds
  are PR 1's bytes (`f691c54c` and round 1's `5dd0511c` are ancestors of #377's head `3a1d0e75`).
- Train: `crew_train.py status` -> `armed: no` in the main clone, 2026-10-05.

## Unknowns
- How hard the main merge is: `crew_autopilot.py` +1720 lines on main since the fork, README +979, code maps
  rewritten. Measured as line counts only; conflicts not attempted.
- Whether T-0100's synthetic base can be rebuilt for the reviewed head without the integration ref's position at
  review time. The manifest records `merged_main.commit`; the receipt does not. If the reviewed head's merged
  commit cannot be recovered (`merge-base <H_r> <ref>`), step 2 reads could-not-tell, which is fail-closed.
- Whether `crew_ticket.py approve` registers a successor budget on an `ACCEPTED` ledger (seen only after a reject).
- Whether any of the 33 sabotage entries' anchors moved with main (each must match exactly once; rule 9 checks).

## Size and split
PR 1 merged. PR 2: about 2120 lines over 14 files as built (711 production, about 1300 tests and sabotage), plus
the merge, the step-2 re-derivation (estimate under 80 lines plus tests) and version/refresh files. PR 3: under
60 lines (two prose paragraphs, a one-argument wiring change, one test). Two PRs because `HARNESS` paths land
alone (T-0087); PR 3 merges after PR 2.

## Touch
PR 2 (tooling-only, `L-0522-tooling`):
- `plugin/crew/hooks/scripts/review_delta.py`, `plugin/crew/hooks/scripts/review_ledger.py`,
  `plugin/crew/hooks/scripts/review_run.py`, `plugin/crew/commands/review.md`
- `plugin/crew/hooks/scripts/crew_autopilot.py` (SEAM, declared by `Tooling-seam:` trailer)
- `plugin/crew/tests/test_review_delta.py`, `plugin/crew/tests/sabotage_review.py`,
  `plugin/crew/tests/test_crew_autopilot.py`, `plugin/crew/tests/test_crew_train.py`
- `plugin/crew/README.md`, `docs/guides/crew/src/troubleshooting.md` plus the rebuilt HTML, DOCX and PDF
  (`docs/guides/crew/src/build.py`), `.crew/verify.json`, `.crew/codemap/**`, `docs/diagrams/**`,
  `.claude/rules/**`, `graphify-out/**`
- Version files: `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `plugin/PLUGINS.md`, `CHANGELOG.md`, `README.md` (generated "What's new"), `plugin/crew/BUDGETS.md`
- `docs/tickets/L-0522/**` (removed before landing unless the owner keeps it)

PR 3 (feature/docs, `L-0522-docs`, after PR 2):
- `plugin/crew/commands/done.md`, `plugin/crew/README.md`, `plugin/crew/hooks/scripts/crew_train.py`,
  `plugin/crew/tests/test_crew_train.py`, `plugin/crew/tests/test_done*.py` if a pinned sentence moves
- docs set per root CLAUDE.md: `plugin/crew/CONFIG.md` (check, likely none), `plugin/PLUGINS.md` row,
  `docs/guides/crew/src/*.md` plus rebuilt outputs, `.crew/codemap/**`, `docs/diagrams/**`, `.claude/rules/**`,
  `graphify-out/**`, version files as above, `plugin/crew/BUDGETS.md`

## Acceptance checks
PR 2:
- `python3 scripts/check-tooling-pr.py` exits 0 (tooling only; the `crew_autopilot.py` seam declared).
- `python3 scripts/_test/tooling-pr.py`
- `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_delta.py -q`, including a new case: a
  receipt written on a T-0100 bundle after a catch-up (paths dropped as identical to merged main) is kept across
  a later version bump and anchor-only refresh, and reads stale when one ticket byte moves.
- `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_*.py -q` (rule 39)
- `python3 -m pytest plugin/crew/tests/test_crew_train.py plugin/crew/tests/test_crew_autopilot.py -q`
- `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_golden.py plugin/crew/tests/test_review_contracts.py plugin/crew/tests/test_review_canary.py -q` (rule 44)
- Fail-closed: in a fixture clone with no `state.json`, `review_ledger.py --ticket <id> --check-receipt` after a
  bump-only commit prints `delta gate: could not tell: no train entry binds the integration ref` and exits non-zero.
- Sabotage: `python3 plugin/crew/tests/sabotage.py` reports `RED (good)` for every `sabotage_review.py` L-0522
  entry, plus one new entry that reverts step 2 to the plain-diff rebuild.
- Dogfood: on `L-0522-tooling` itself, `review_ledger.py --ticket L-0522 --check-receipt` reads stale (PR 2 adds
  ticket code over PR 1's receipt).
- `git grep -n "check_land. passes" -- plugin/crew` finds nothing (today: `review_delta.py:30`, `review_ledger.py:840` on TB).
- `python3 scripts/check-marketplace.py` (after commit), `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests -q`.

PR 3:
- `python3 -m pytest plugin/crew/tests/test_crew_train.py -q` with a case that `check_land` passes its fetched sha
  (a judge fixture whose train ref moved after the fetch still judges the fetched commit).
- `git grep -n "until one exists" -- plugin/crew/README.md` finds nothing; `done.md` check 1 names
  `receipt kept by delta gate` and the armed-train condition.
- `python3 scripts/check-tooling-pr.py` exits 0 (no harness path touched), `python3 scripts/check-marketplace.py`.

## Dependencies
- Depends on: PR 1 (#377, merged), T-0100 (#371, merged on main; PR 2 must adapt to it), T-0087 (tooling-alone
  rule), the merge train (L-0520; must be armed for the gate to keep anything).
- Blocks: T-0033 (#527, to close as superseded by PR 2's manifest allowlist), L-0511 PR 2 (#528; bump and refresh
  once at land need the version and anchor exemptions).
- Follow-up: L-0620 (fast path vs a catch-up resolved back to the reviewed bytes over main's edit to a ticket file).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
