# L-0768 - promote-gate reads deploy policy from the deployed tree, not the session's checkout

Owner decision 2026-10-10 (Matthew, direct): fix now, as an explicit exception to the 2026-10 crew
feature freeze. This is PR A of the TSS-win report (bugs 2 and 3); L-0765 (release mode) is PR B.

## Intent

From a linked git worktree, both promote-gate flavours read `.crew/verify.json` from the session's
project dir. The review helper (`_promote_review.py`) runs with the project dir as cwd and
`committed_map_text()` reads `.crew/verify.json` there, ignoring its `tree` argument; the bash VERDICT
step and the ps1 `$vm` read requires / rollback / requireHuman from the same file; and the
uncommitted-map guard judges the project dir's copy. So a `requireReview: false` waiver committed on
the branch being deployed is never seen, and the main checkout's unrelated dirt or waiver decides a
worktree deploy.

The rule after this ticket, both flavours: **the policy that governs a deploy is the map committed in
the sha being deployed** - `git -C <tree> ls-tree --full-tree <sha> -- .crew/verify.json`, then that
blob. Since the sha must be the tree's HEAD (T-0505), this is exactly what a deploy from a main
checkout at that sha reads today, so a worktree can do nothing a checkout of the same sha could not.

- requireReview / reviewReason, requires, rollback / rollbackReason and requireHuman for every
  matched environment come from that committed map.
- A matched environment the deployed sha's map does not declare blocks (could not tell), naming it.
- The deployed sha carries no committed map at all (an old sha, a repo whose map is ignored): the
  project dir's map is the policy, read exactly as today (working file held to the project dir's
  HEAD), and then the project dir's map must be clean.
- A committed map at the sha that cannot be read or parsed, or holds case twins or a duplicate key,
  blocks (could not tell). A failed `ls-tree` is could-not-tell, never "no map".
- The uncommitted-map guard judges the deployed tree's own working copy: when the deploy tree IS the
  project dir its dirty map blocks as today (same message); a linked worktree's tree dirt, its map
  included, is refused by the existing clean-tree check (T-0505). A dirty map in an unrelated project
  dir no longer blocks a worktree deploy, because it is no longer read as policy - it is still matched
  (working and committed, as today), which can only add environments.

The `github` entry's sha rule (`_promote_github.py`, L-0648) is per-environment policy too, so it
reads the same blob (`--tree`/`--policy-blob`, listed by the gate); without that, an uncommitted project-dir edit dropping a
`shaInput` would have become policy once the project-dir guard stopped judging worktree deploys.

Unchanged and deliberate: WHICH command is a deploy and to which environment (the matcher,
`_promote_dispatch.py`) is read from the project dir's map, working and
committed, before the tree is known; state stays in the project dir (`.work/PROMOTIONS.md`,
`.crew/.approved-*`, the rollback runbook file, incident files, `.crew/.deploy-in-flight`). The
no-python jq fallback blocks every possible deploy and is untouched.

## Exclusions

- L-0765 (release mode, merged-main tip receipts, scope_base fallback): PR B.
- Moving matching to the deployed tree's map (it runs before the tree is resolved; a branch that adds
  a new deploy command is not matched until its map is in the project dir - unchanged from today).
- review_patch.py, review_ledger.py, scope_base.py and every other HARNESS path: not touched.
- Rollback runbook paths are still resolved in the project dir.

## Evidence

- promote-gate.sh:60 `cd "${CLAUDE_PROJECT_DIR:-.}"`; VERDICT step opens `.crew/verify.json` (cwd);
  review call at the end runs `_promote_review.py "$TREE" "$FULL" ...` from the project dir.
- promote-gate.ps1:42 `Set-Location $root`; `$cfg = $vm.environments.$e` from the working map;
  `Invoke-PromoteReview` sets `WorkingDirectory = (Get-Location).Path`.
- `_promote_review.py` `committed_map_text(deadline)` opens `.crew/verify.json` relative to cwd and
  compares with `git ls-tree HEAD` of the cwd.
- The dirty-map guard (`if [ -n "$MAP_DIRTY" ]` / `if ($mapDirty)`) names "the project dir".
- TSS-win repro: `_promote_review.py` run by hand in the worktree exits 0; the hook's call blocks.

## Unknowns

None open. Decided: policy from the deployed sha's committed map; project-dir fallback only when the
sha carries no map; matching and state unchanged.

## Touch

- `plugin/crew/hooks/scripts/promote-gate.sh`
- `plugin/crew/hooks/scripts/promote-gate.ps1`
- `plugin/crew/hooks/scripts/_promote_review.py`
- `plugin/crew/hooks/scripts/_promote_github.py`
- `plugin/crew/tests/test_promote_gate_github.py`
- `plugin/crew/tests/test_promote_gate_tree_policy.py`
- `plugin/crew/tests/test_promote_gate_effective_tree.py`
- `plugin/crew/tests/promote_tree_mutations.py`
- `plugin/crew/tests/test_promote_gate_review.py`
- `plugin/crew/tests/test_promote_gate_dispatch.py`
- `plugin/crew/tests/test_promote_gate_literal_match.py`
- `plugin/crew/commands/promote.md`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/skills/crew-verification/SKILL.md`
- `docs/guides/crew/src/**`
- `docs/guides/crew/**`
- `INSTALLATION.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `README.md`
- `.crew/codemap/**`
- `.crew/verify.json`
- `graphify-out/**`
- `docs/diagrams/**`
- `.claude/rules/**`

## Acceptance checks

Both flavours (sh and ps1), committed regression cases, every ps1 case that times a deadline marked
`wallclock` (L-0759):
- MUST ALLOW: a deploy from a linked worktree whose committed map sets `requireReview: false` +
  `reviewReason`, while the main checkout's map requires review, is admitted.
- MUST BLOCK: a waiver only in the main checkout's committed map does not admit a worktree deploy
  whose committed map requires review.
- MUST BLOCK: an uncommitted waiver in the worktree (map edited, not committed) does not admit
  (clean-tree check), and an uncommitted waiver in the main checkout does not either.
- MUST ALLOW: a dirty (uncommitted) map in the main checkout does not block a clean worktree deploy
  whose committed map admits it.
- MUST BLOCK: the main checkout's dirty map still blocks a deploy from the main checkout.
- MUST BLOCK: `requires` comes from the worktree's committed map (dropping it only in the main
  checkout's map does not skip it; dropping it only on the branch does).
- MUST BLOCK: a matched environment absent from the deployed sha's map blocks, naming it.
- MUST BLOCK: a deployed sha whose committed map does not parse blocks as could-not-tell.
- MUST BLOCK: the `github` shaInput rule comes from the deployed sha's map.
- MUST BLOCK: a failed listing of the deployed sha's map is could-not-tell.
- Fallback: a worktree at a sha with no committed map uses the project dir's map (as today).
- Sabotage: each new guard has a promote_tree_mutations.py entry; reintroducing the bug (read the
  project dir's map; review helper ignores the tree) turns its case red.
- The existing promote-gate suites pass (cases whose assertion named the old project-dir guard are
  retargeted, never deleted).
- check-marketplace.py, check-crew-docs.py, build.py --check, config_reference.py --check pass.
