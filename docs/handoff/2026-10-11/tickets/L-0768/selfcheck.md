# L-0768 self-check
<!-- stamp: bundle=b0013ae53ff90db86ac7d78995f72dbea672fa5c8c8f7bbe4b1caee1aaae5f05 standards=a031dfc6196243a94f86382e89635b333eeae94fe8eb6724c9908ea9028cf6ae base=e77532e01775ac61e7cd6c3cf276ad4453b67ac3 -->

standards: 25 in sets GEN, PWSH, PYTHON, REPO; overlay: present (.crew/standards.md); digest a031dfc6

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | addressed | A failed ls-tree/cat-file is could-not-tell in all three readers (test_promote_gate_tree_policy.py::test_a_failed_listing_of_the_deployed_map_blocks, mutations 'reads a failed listing ... as no map'); an undeclared environment blocks (test_an_environment_the_deployed_map_does_not_declare_blocks); a non-UTF-8 or unparseable map blocks (test_a_deployed_map_that_does_not_parse_blocks) |
| GEN-02 | n/a | no shared file is written; the gate only reads the map and git objects |
| GEN-03 | addressed | the in-flight marker is written only after every check on the sha's own map passed; the sha read is the tree's HEAD (T-0505), the same sha whose map is read |
| GEN-04 | addressed | must-block and must-allow pairs in test_promote_gate_tree_policy.py, both flavours; every new branch has a promote_tree_mutations.py entry that goes RED (sabotage run 2026-10-10) |
| GEN-05 | addressed | ls-tree entry accepted only as `<mode> blob <40-hex> <path>`; anything else blocks as 'not a file' (promote-gate.sh TREE_MAP parse, ps1 $entry check, _sha_map_blob) |
| GEN-06 | addressed | git argv lists in python; tree from rev-parse --show-toplevel and sha from rev-parse HEAD, oid checked as 40 hex before cat-file; --no-replace-objects on every policy read (test_a_replace_ref_cannot_waive_review / _drop_requires) |
| GEN-07 | addressed | one policy rule: _promote_review.policy_map_text, mirrored by the sh VERDICT (same blob) and ps1 (same two git calls); _promote_github reads the same blob the gate listed (--policy-blob) |
| GEN-08 | addressed | ps1 decodes the blob as UTF-8 explicitly (OutputEncoding pinned), both flavours tested; Windows-native not exercised locally (CI crew-windows jobs) |
| GEN-09 | addressed | promote.md, README, CONFIG.md, SKILL, guide and troubleshooting updated to the new rule; gate header comments rewritten |
| GEN-10 | addressed | git replace behaviour measured in the fixture (_replace_map asserts status clean and the gate still blocks) |
| GEN-11 | addressed | requires, rollback, requireHuman, github shaInput and requireReview all read the same map; one case per requirement in both flavours |
| GEN-12 | addressed | review bundle is built from the committed HEAD; tests re-run on HEAD before review |
| PWSH-16 | addressed | Invoke-PolicyGit resolves git with Get-Command -CommandType Application and treats no Application as could-not-tell (promote-gate.ps1 Invoke-PolicyGit) |
| PYTHON-01 | addressed | blob decoded utf-8-sig strict, UnicodeDecodeError is could-not-tell (_promote_review.policy_map_text, promote-gate.sh VERDICT) |
| PYTHON-03 | addressed | ls-tree output split on whitespace into 4 fields, path field must be present; one entry only |
| PYTHON-04 | n/a | no file is rewritten |
| PYTHON-06 | addressed | argv lists via crew_common.require_tool('git') in _promote_review; VERDICT uses shutil.which('git') |
| PYTHON-07 | addressed | every new git read is bounded by what is left of the gate deadline: sh `timeout "$left"` (list_policy_map), VERDICT and _promote_github timeout=deadline-left, ps1 WaitForExit(left); test_a_stalled_map_read_blocks_inside_the_hook_timeout (both flavours, ls-tree and cat-file) + mutations RED |
| PYTHON-08 | n/a | children inherit the hook environment as before; no new environment dependency |
| PYTHON-10 | addressed | a non-object map or environments refuses (ps1 explicit; python raises -> non-zero -> block) |
| PYTHON-11 | addressed | try bodies wrap only the git call / decode being classified |
| PYTHON-13 | n/a | no path containment; tree equality is by git toplevel strings as before |
| REPO-01 | n/a | no identity handling |
| REPO-02 | n/a | no change detector |
| REPO-03 | addressed | crew 1.2.22 in plugin.json, marketplace.json, PLUGINS.md; CHANGELOG + README synced; BUDGETS count; version re-set last at merge |
