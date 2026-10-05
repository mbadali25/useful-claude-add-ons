# T-0011 plan            spec: .work/tickets/T-0011/spec.md

Owner approves (risk: high). Precondition: T-0004 merged. Crew version for this ticket: 1.0.34.

### Step 1: the ship decision, pure
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_ship.py
Where: family source `review_ledger.py:273` (round rows), risk from T-0004's `crew_ticket.parse_risk`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py -q -k decision
Risk: high - this function is what merges unattended
- [ ] read `gh pr checks --help` and `gh --version` on this machine; record the chosen adapter (JSON fields or text) in the step's commit message
- [ ] `ship_decision(policy, risk, checks, families, known_failures)`: `checks` is a list of `{"name", "state"}` with state in {pass, fail, pending, skipping, unknown}; `pr` -> `open-pr`; `merge`: any `unknown` -> stop; any `pending` -> wait; any `fail` whose name is not EXACTLY in `known_failures` -> stop; risk `high` (or unknown) and every family in {"claude", None} -> stop "same-family review only on a high-risk ticket"; else `merge`
- [ ] tests: `test_pr_policy_never_merges`, `test_merge_all_green`, `test_merge_waits_on_pending`, `test_merge_stops_on_unknown_state`, `test_merge_allows_listed_known_failure`, `test_known_failure_needs_exact_name`, `test_high_risk_same_family_stops`, `test_missing_family_counts_as_same_family`, `test_high_risk_cross_family_merges`, `test_low_risk_same_family_merges`

### Step 2: the `ship` phase and the gh adapter
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_ship.py
Where: T-0004's `next_phase` terminal branches (`done` -> `closed`); the adapter is the only code that runs `gh`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py -q -k "phase or adapter"
Risk: high - a wrong PR state closes a ticket that never shipped, or merges twice
- [ ] `_gh(args)` adapter: returns parsed JSON or `None` on any failure (not installed, not authenticated, non-zero exit); tests stub it
- [ ] `next_phase`: spec `status: done` and no merged PR -> `ship`; `gh pr view <branch> --json number,state` None -> stop "could not read PR state"; MERGED -> `closed`; OPEN under `pr` -> `closed`, "PR #n open, merge by hand"
- [ ] `crew_autopilot.py ship --ticket <id>`: push the branch (`git push -u origin <branch>`, no force), `gh pr create` if none, then poll required checks every 30 s up to `ciTimeoutMinutes`, feeding `ship_decision`; `merge` -> `gh pr merge <n> --merge`; print PR, checks and families used
- [ ] tests: `test_ship_phase_after_done`, `test_merged_pr_closes`, `test_open_pr_under_pr_policy_closes_with_note`, `test_gh_failure_stops`, `test_merge_argv_is_merge_commit_without_admin`, `test_timeout_pending_stops`

### Step 3: config and the command
Files: plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/config.template.json, plugin/crew/commands/autopilot.md, plugin/crew/tests/test_crew_config.py, plugin/crew/tests/test_crew_autopilot_ship.py
Where: T-0004's `AUTOPILOT_DEFAULTS` near `crew_state.py:1062`; leaf count `test_crew_config.py:271`
Test: python3 -m pytest plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_autopilot_ship.py plugin/crew/tests/test_lifecycle_commands.py -q; python3 plugin/crew/hooks/scripts/_test/validate-prompts.py
Risk: med
- [ ] defaults `ship: "merge"`, `knownFailures: []`, `ciTimeoutMinutes: 60`; `ship` not in {pr, merge} -> `pr` with a warning (the non-merging direction); `knownFailures` not a list of strings -> `[]` with a warning
- [ ] `autopilot.md`: `ship` phase runs `crew_autopilot.py ship --ticket <id>` and reports its line; still under 120 lines
- [ ] tests: `test_ship_default_merge`, `test_ship_bad_value_reads_pr`, `test_known_failures_bad_type_is_empty`; leaf count re-measured

### Step 4: sabotage, verify rule, docs, version
Files: plugin/crew/tests/sabotage_autopilot.py, plugin/crew/tests/sabotage.py, .crew/verify.json, plugin/crew/CONFIG.md, plugin/crew/README.md, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md, TODO.md
Where: registry `sabotage.py:2927`
Test: python3 plugin/crew/tests/sabotage.py restricted to the new mutations; python3 -m pytest plugin/crew/tests/ -q serially; python3 scripts/check-marketplace.py
Risk: low
- [ ] mutations: merge on pending -> `test_merge_waits_on_pending`; drop the same-family refusal -> `test_high_risk_same_family_stops`; `None` family counts as cross-family -> `test_missing_family_counts_as_same_family`; substring match on known failures -> `test_known_failure_needs_exact_name`
- [ ] `.crew/verify.json` rule for `test_crew_autopilot_ship.py`; CONFIG.md and README document the keys and that until 2026-10-01 high-risk tickets stop at merge (Codex out)
- [ ] bump crew to 1.0.34 (assigned; lanes must not collide) in plugin.json, marketplace.json, PLUGINS.md; CHANGELOG; BUDGETS.md if flagged

### Step 5: amendment - merge commits, and the two pins on the old autopilot block
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_ship.py, plugin/crew/tests/sabotage_autopilot.py, plugin/crew/tests/test_crew_autopilot.py, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/README.md, plugin/crew/CONFIG.md, CHANGELOG.md, TODO.md
Where: the built branch T-0011-build in /repos/personal/uca-t-0011 (HEAD c0881f38); `plugin/crew/tests/test_crew_autopilot.py:1076`; `plugin/crew/skills/crew-setup/SKILL.md:169`
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py plugin/crew/tests/test_crew_autopilot.py plugin/crew/tests/test_crew_config.py -q -p no:cacheprovider; python3 plugin/crew/tests/sabotage.py (non-RED set equal to main's); full suite serially
Risk: med - a squash merge made by autopilot rewrites the commits every refresh anchor names
- [ ] The merge argv is `["gh", "pr", "merge", str(n), "--merge"]`. Rename the test to `test_merge_argv_is_merge_commit_without_admin`; it asserts the exact argv and that `--squash`, `--rebase` and `--admin` are absent. Add a sabotage mutation that restores `--squash` and turns that test red.
- [ ] `plugin/crew/skills/crew-setup/SKILL.md`: the inline default-config block's `autopilot` object gains `ship`, `knownFailures` and `ciTimeoutMinutes` with the defaults, so `test_default_config_matches_crew_setup_skill_md_inline_copy` passes.
- [ ] `plugin/crew/tests/test_crew_autopilot.py:1076`: `test_autopilot_defaults_are_the_config_block` asserts the five-key block.
- [ ] README and CONFIG.md say merge commits and why (refresh anchors, D-028). Remove the squash-vs-D-028 item from TODO.md. The CHANGELOG entry says merge commit.
- [ ] Refresh until `fresh` (the build left 6 codemaps, 2 diagrams and graphify-out stale), keep the version set last, and run the suites serially. Then review round 1.

### Step 6: successor - review round 2 (4 BLOCK, 2 FIX, 0 NIT; .work/review/T-0011-build--1mwEli/out.txt in uca-t-0011)
Files: plugin/crew/hooks/scripts/crew_autopilot.py, plugin/crew/tests/test_crew_autopilot_ship.py, plugin/crew/tests/sabotage_autopilot.py, plugin/crew/README.md, plugin/crew/CONFIG.md, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json
Test: python3 -m pytest plugin/crew/tests/test_crew_autopilot_ship.py plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider; each new test watched red first on b5bffe4e; python3 plugin/crew/tests/sabotage.py (non-RED set equal to main's, every SHIP mutation RED); full suite serially
Risk: high - every finding is a way ship merges unattended on checks, a tree or reviews other than the ones it read
- [ ] BLOCK (crew_autopilot.py:344, `read_checks` at `:324-360`), per the spec's Owner decision (recommendation taken; re-plan if the owner picks GraphQL): measure the field count of `gh pr checks <n> --required` on a real PR with this machine's gh 2.46 (`| od -c`), record it in the commit and in a comment beside `_BUCKETS`, and make a row with any other count (after dropping one trailing empty field only if the measurement shows gh prints one) return None. Must-block: `test_read_checks_tab_in_name_is_unreadable` - the stub `(1, "check\tfail\tfail\t1m\turl\t\n", "")` reads None, and `ship` with `knownFailures: ["check"]` stops with no merge argv recorded; the same for a tab inside the description field. Must-allow: a row in the measured shape reads its exact name and bucket, and an all-pass set still merges.
- [ ] BLOCK (:535, the `head = git_out(...)` at `:536` taken after the CI loop): capture `head` once, right after the push (`:493`) and before the first `read_checks`; the PR's `headRefOid` must equal it when the PR is first read and on every poll, read both before and after that poll's `read_checks`; local HEAD must still equal it after the loop; the merge argv carries this `head`. Any mismatch stops with both shas named and never merges. Must-block: `test_ship_stops_when_a_commit_lands_after_passing_checks` - the checks stub passes for A, then makes an empty commit B in the fixture repo and reports `headRefOid` B; ship stops and records no `pr merge` argv. Must-allow: with no new commit the merge argv is exactly `merge_argv(n, A)`.
- [ ] BLOCK (:539, the `check_receipt` after CI): the families reported and the receipt checked must come from one ledger. `_ship_gate` also returns the sha256 of `review_ledger.ledger_path(top, ticket)`'s bytes (None when unreadable, which stops); after `check_receipt` returns True, and again immediately before the merge call, the hash is re-read and must equal the one from the gate that produced `families`. Must-block: `test_ship_stops_when_the_ledger_is_replaced_after_the_last_poll` - a `check_receipt` stub that swaps the ledger file for a Claude-only successor-plan ledger before returning True; ship stops naming the ledger change, no merge argv. Must-allow: an unchanged ledger merges and the result's `families` are the gate's.
- [ ] BLOCK (:557, the merge at `:555` after `read_merge_queue` at `:548`): re-read local HEAD immediately before the merge call and stop when it is not the captured `head`, or unreadable. Must-block: `test_ship_stops_when_head_moves_during_the_queue_read` - a `read_merge_queue` stub that commits B locally and returns False, the PR left at A; no merge argv. Must-allow: the same stub without the commit merges with `--match-head-commit A`.
- [ ] FIX (:493, the push): a CLEAN receipt can cover uncommitted edits that `git push` does not carry. `git status --porcelain --untracked-files=all` (ignored files excluded) must be empty and readable in `_ship_phase` before it names `ship` (`:457`), in `ship` before the push, and again before the merge; otherwise stop, "the working tree differs from HEAD - commit or discard first", and a git failure is could-not-tell, also a stop. Must-block: `test_ship_refuses_a_dirty_tracked_file_before_pushing` and `test_ship_refuses_an_untracked_file_before_pushing` - no push argv, no merge argv. Must-allow: a clean tree pushes and merges as today (the existing all-green test stays green).
- [ ] FIX (:557, gh queues after the preflight), per the spec's Owner decision (recommendation taken): `read_pr` also reads the PR's node `id`; when the merge call leaves the PR not MERGED, read the queue again, and when it is true or unreadable run `gh api graphql` with `dequeuePullRequest` for that id once, then stop naming the queue and the dequeue outcome. Must-block: `test_ship_dequeues_a_pr_gh_queued` - merge exits 0, `read_pr` reads OPEN, the queue reads True; one dequeue argv is recorded and the result is a stop naming the queue; `test_ship_unreadable_queue_after_merge_dequeues_and_stops` for a None queue read. Must-allow: a merge that reads MERGED records no dequeue argv, and across every ship test the only `api graphql` mutation ever recorded is `dequeuePullRequest`.
- [ ] README and CONFIG.md: ship stops on a dirty tree, on a check row it cannot parse (a tab in a required check's name), on a moved head or a changed ledger, and dequeues a PR gh queued. CHANGELOG: the six fixes under the branch's entry.
- [ ] Sabotage in `SHIP_MUTATIONS` (`sabotage_autopilot.py`), one per new branch: the field-count check removed -> `test_read_checks_tab_in_name_is_unreadable`; `head` re-sampled after the loop -> `test_ship_stops_when_a_commit_lands_after_passing_checks`; the ledger-hash comparison removed -> `test_ship_stops_when_the_ledger_is_replaced_after_the_last_poll`; the pre-merge HEAD re-read removed -> `test_ship_stops_when_head_moves_during_the_queue_read`; the porcelain check removed -> `test_ship_refuses_a_dirty_tracked_file_before_pushing`; the dequeue call removed -> `test_ship_dequeues_a_pr_gh_queued`. Each turns its named test red.
- [ ] Keep crew at the branch's version, set last (step back and re-set if needed). Refresh until `fresh`. Continue the ledger via `--successor-plan <sha256 of this plan.md>` against the owner's `/crew:approve T-0011` receipt, then review round 3. The reviewer's output is copied byte-for-byte.

## Self-review
- Spec coverage: decision -> 1; same-family -> 1; ship phase and PR state -> 2; merge-commit-without-admin argv -> 2 and 5; config keys -> 3; sabotage, verify, docs, version -> 4.
- Touch coverage: every Files: entry is in the spec's Touch.
- Interfaces: `ship_decision` (1) is what `ship` (2) calls; `_gh` (2) is the only caller of `gh`.
- Not verified while planning: this machine's `gh pr checks` flags (step 1 reads them).
