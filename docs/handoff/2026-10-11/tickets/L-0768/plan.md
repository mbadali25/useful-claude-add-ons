# L-0768 plan

## Step 1 - one reader of the deployed sha's map (_promote_review.py)
- Files: plugin/crew/hooks/scripts/_promote_review.py
- Change: `policy_map_text(tree, sha, deadline)` returns `(text, source)`: `git -C <tree> ls-tree
  --full-tree <sha> -- .crew/verify.json` (bounded by the gate deadline); a failed listing, a non-blob
  entry or a failed `cat-file` is CouldNotTell; an entry is read as the blob (utf-8-sig); no entry
  falls back to the existing project-dir read (`project_map_text`, the old `committed_map_text`, cwd
  = project dir, held to the project dir's HEAD). `main` uses it. A `--policy <tree> <sha> <deadline>`
  mode prints the source on line 1 and the text after, for the ps1 flavour. Docstring rewritten.
- Test: unit cases in test_promote_gate_tree_policy.py for each branch (blob, absent, failed listing).
- Risk: a sha whose map is a directory or a submodule entry - refused as could-not-tell.

## Step 2 - bash flavour
- Files: plugin/crew/hooks/scripts/promote-gate.sh
- Change: the MAP_DIRTY block moves below tree resolution and fires when the deploy tree is the project
  dir, or when the deployed sha has no committed map (the project-dir fallback). The VERDICT python
  imports `_promote_review` and reads the policy with `policy_map_text(TREE, FULL, deadline)`; a
  CouldNotTell or a matched environment missing from that map blocks. Header comment updated.
- Test: sh cases in test_promote_gate_tree_policy.py; existing promote-gate suites.
- Risk: VERDICT gains a git call inside the 16s deadline - bounded by `_left(deadline)`.

## Step 3 - ps1 flavour
- Files: plugin/crew/hooks/scripts/promote-gate.ps1
- Change: same move of the `$mapDirty` block; after the tree is known, `git -C $tree ls-tree
  --full-tree $full -- .crew/verify.json`, then `cat-file blob`, parsed with ConvertFrom-Json and
  Find-DuplicateJsonKey into `$policy` (fallback `$vm` when no entry); `$cfg = $policy.environments.$e`;
  a missing environment blocks. `Invoke-PromoteReview` keeps the project dir as WorkingDirectory
  (the fallback reads the project dir's map, never a worktree's untracked copy) - stated in a comment.
- Test: ps1 cases (wallclock where the deadline is timed).
- Risk: PowerShell splits git output into lines; joined with LF as the existing committed-map read does.

## Step 3b - the github sha rule reads the same map
- Files: plugin/crew/hooks/scripts/_promote_github.py, plugin/crew/hooks/scripts/promote-gate.sh, plugin/crew/hooks/scripts/promote-gate.ps1
- Change: `--tree <dir> --policy-blob <oid>` reads the blob the gate listed (cat-file --no-replace-objects), the project dir map without it; both gates pass it; ps1's `$ghMatched` uses `$policy`.
- Test: test_the_github_sha_rule_comes_from_the_deployed_map, both flavours; test_promote_gate_github.py unchanged and green.
- Risk: a crash on an unreadable map blocks (could-not-tell), as before.

## Step 4 - regression suite and sabotage
- Files: plugin/crew/tests/test_promote_gate_tree_policy.py, plugin/crew/tests/promote_tree_mutations.py,
  plugin/crew/tests/test_promote_gate_effective_tree.py, plugin/crew/tests/test_promote_gate_review.py,
  plugin/crew/tests/test_promote_gate_dispatch.py, plugin/crew/tests/test_promote_gate_literal_match.py
- Change: the acceptance cases in the spec, both flavours; mutations: VERDICT reads the cwd map again,
  ps1 `$cfg` from `$vm` again, the review helper reads the cwd map again, the dirty guard back at the
  project dir unconditionally, the missing-environment block removed. test_uncommitted_edits_to_the_
  deploy_map_block is retargeted (the project dir's dirty edit is not policy: the worktree's committed
  requires still blocks), and its mutation follows it.
- Test: the new file both ways; each mutation run alone goes red.
- Risk: existing cases asserting the old message from a worktree.

## Step 5 - docs and version
- Files: plugin/crew/commands/promote.md, plugin/crew/README.md, plugin/crew/CONFIG.md,
  plugin/crew/skills/crew-verification/SKILL.md, docs/guides/crew/src/**, docs/guides/crew/**,
  INSTALLATION.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json,
  plugin/PLUGINS.md, CHANGELOG.md, README.md, .crew/codemap/**, graphify-out/**, docs/diagrams/**
- Change: state the rule (policy = the deployed sha's committed map; matching and state stay in the
  project dir); troubleshooting entry for the moved guard; guide rebuilt; next free crew version.
- Test: check-marketplace.py, check-crew-docs.py, build.py --check, config_reference.py --check.
- Risk: version collides with #584 / other lanes - re-checked at merge.
