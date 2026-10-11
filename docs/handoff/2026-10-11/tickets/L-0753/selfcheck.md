# L-0753 self-check
<!-- stamp: bundle=e77a43952df4140c3eb154698e3e71143aa1fa2067a62cafc89a055901b1180a standards=2a02982acc8605a42efda8d9aeddcccbcc18a81e18d78b19dfbd5cade8a11c2f base=a7fb104b04233315abe5b9b4d1a55fe6554841aa -->

standards: 24 in sets GEN, PYTHON, REPO; overlay: present (.crew/standards.md); digest 2a02982a

Answer every row before `/crew:review`. Status is `addressed` (Evidence: the test that
covers it, a `mutation -> failing test` pair, or the file:line that does it) or `n/a`
(the reason it does not apply to this change). Then run `crew_standards.py stamp`;
any later edit to the change needs a new stamp.

| ID | Status | Evidence or reason |
|---|---|---|
| GEN-01 | addressed | own_changes: merged_main could-not-tell, unreadable HEAD, missing/garbled/foreign receipt, a receipt naming another ticket or base, no landing, non-merge landing, unlistable parents -> full since-base set with the reason on the top line (test_could_not_tell_judges_the_full_set x7); ci_receipt: parent run lookup or parent tree read failing -> UNKNOWN (test_check_could_not_tell_when_*) |
| GEN-02 | n/a | no shared file written; both checks stay read-only |
| GEN-03 | n/a | no irreversible action added |
| GEN-04 | addressed | must-allow and must-block for a-d in test_done_own_changes.py (pre-land, landed, later) and test_ci_receipt.py; 11 hand mutations each red (.work/tickets/L-0753/sabotage-by-hand.py); entries filed for the tooling PR |
| GEN-05 | addressed | a parent vouches only when its tree equals HEAD's (ci_receipt._same_tree_parents) and only when HEAD has no run; the landing is accepted only as a merge whose first parent lacks the receipt head; everything else is the full set or UNVERIFIED |
| GEN-06 | addressed | git argv lists only; shas from git or a 40-hex regex-checked receipt field; no shell |
| GEN-07 | addressed | own_changes returns one dict consumed by crew_docs_check and ticket_freshness; test_own_changes_names_the_landing_merge pins its keys and values |
| GEN-08 | addressed | pure git plumbing via crew_common.require_tool / completion_audit._git_fields; no path separators built; the CI Windows shards run the same pytest files |
| GEN-09 | addressed | done.md, docs.md, crew README, troubleshooting and daily-workflow guides (rebuilt), the done diagram and crew codemap describe this commit; CHANGELOG entry |
| GEN-10 | addressed | L-0739 live evidence measured: main a7fb104b tree == PR head 221ffe9b9 tree; verify-gate.yml:28-31 has no main trigger; merged_main docstring corner reproduced by test (landed stage red on main) |
| GEN-11 | addressed | checks 4 and 5 share own_changes; tested at all three moments; check 2 parent path binds the same receipt fields as the HEAD path |
| GEN-12 | addressed | local verify-gate --all at the review HEAD (this branch changes ci_receipt.py, so a CI receipt cannot vouch for it) |
| PYTHON-01 | addressed | _receipt_head opens review.json with encoding utf-8, errors strict; UnicodeDecodeError is could-not-tell |
| PYTHON-03 | addressed | diff-tree -z NUL split; rev-list output is sha tokens |
| PYTHON-04 | n/a | no file rewritten |
| PYTHON-06 | addressed | git launched via crew_common.require_tool as argv lists |
| PYTHON-07 | addressed | _contains subprocess timeout=GIT_TIMEOUT; git_out and _git_fields carry their own timeouts; binary search bounds the git calls |
| PYTHON-08 | n/a | same inherited environment as every existing git call in these modules; nothing home-dependent added |
| PYTHON-10 | addressed | receipt JSON checked to be a dict with a 40-hex head string naming a commit; marketplace.json at the landing goes through _entries' shape checks |
| PYTHON-11 | addressed | _receipt_head: the file read and json.loads are separate try blocks; _contains try body is the subprocess.run only |
| PYTHON-13 | n/a | no filesystem path containment; repository-relative git paths only |
| REPO-01 | n/a | no identity checks changed |
| REPO-02 | addressed | post-land set also unions working-state changes vs HEAD (changed_paths(top, HEAD)), so an uncommitted edit at close is judged |
| REPO-03 | addressed | placeholder version commit last (plugin.json, marketplace.json, PLUGINS.md, CHANGELOG, README sync); check-marketplace passes |
