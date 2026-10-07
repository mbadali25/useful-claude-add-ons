# Cloud handoff: L-0527

**Kimi review launch in the review harness, tooling half of T-0028 (tooling-only PR)**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** child, the second of two PRs the owner split T-0028 into ("Split into 2 PRs", 2026-09-30). The feature half is T-0028, PR #288, merged.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; the implementing session writes the plan)
- **Branch:** `L-0527-build`, new from origin/main `a555ff37`. Docs only so far, no implementation yet.
- **Files here:** `docs/tickets/L-0527/direction.md`, `docs/tickets/L-0527/spec.md`
- **Size:** about 700 production lines (`review_run.py`, `review_verdict.py`, review.md), about 1500 test lines, and about 780 sabotage lines. Already reviewed through T-0028 rounds 1-5 on the source.
- **Harness:** yes. `review_*.py`, `commands/review.md`, `review_fixtures.py` and `sabotage*.py` are review/gate harness paths, so this lands alone as a tooling-only PR.

## Where the code is

The source is reachable from origin/main, so no local branch is needed:

- `git show d4f1e5bc:<path>` gives each file as reviewed (`d4f1e5bc` = local `L-0527-source`, an ancestor of main).
- `git diff 524da6a4 524da6a4^ -- plugin/crew/hooks/scripts/review_run.py plugin/crew/hooks/scripts/review_verdict.py plugin/crew/commands/review.md plugin/crew/tests/review_fixtures.py plugin/crew/tests/sabotage.py plugin/crew/tests/sabotage_kimi.py plugin/crew/tests/test_review_run_kimi.py plugin/crew/tests/test_review_verdict.py plugin/crew/tests/test_worktree_config.py plugin/crew/tests/test_kimi_docs.py` is the harness patch the split removed.
- It does not apply clean. Main has 24 commits on `review_run.py` and 33 on review.md since. Re-apply it hunk by hunk.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0028 | merged (PR #288) | Probe, `final_message` parser, `kimi_fixtures`, the launch gate. |
| T-0087 | merged | The rule that tooling PRs land alone. |
| L-0528 | spec (PR open) | Moves `EXIT_UNVERIFIED` to 9 and leaves 8 for `EXIT_PROBE_CHANGED`. Either order works. |
| follow-up (id to be minted) | not filed | Feature PR for the docs outside `ALONGSIDE`: crew-providers `SKILL.md`, `alternative-providers.md`, the `kimi_probe.py` and `crew_config.py` docstrings. Lands right after this one. |

## Read before writing code

- Re-find every `path:line` by content. They were checked at `a555ff37`.
- Do **not** carry over SRC `review_verdict.py`'s own stream parser. Import `kimi_probe.final_message`, which is the only parser.
- Keep the probe before preflight and before reserve, and re-read `run`'s order on main first (L-0574's `prereview_gate` and the standards gate landed since).
- `test_provider_table.py:2540`'s must-block test assumes kimi is not launched. Rewrite it so that a provider not in `LAUNCHED` is ineligible, using a stand-in name.
- `sabotage.py` is at 3381 of 3400 lines: only the import and the `+ KIMI_MUTATIONS` term go there.
- Register the 7 sabotage entries owed from T-0028 rounds 6-7 (listed in direction.md), each aimed at the tests under `test_kimi_probe.py:497`.
- A harness change runs the harness rule's suites: the tooling checker, its suite, the golden replay, the seam contracts, and the canary review. `check-tooling-pr.py` must exit 0.
- Own ledger and review budget, and the merge-train protocol with `--match-head-commit` (the owner's split rules).

## Open questions for the owner (recommended option taken)

- Docs outside `ALONGSIDE` go in a follow-up feature PR after this one, not before it, so no doc claims a launch that does not exist yet. The coordinator mints its id.
- `EXIT_PROBE_CHANGED` is 8.
- The three T-0028 follow-ups (codex/copilot fingerprint, the unredacted codex stream error, `.git` writes beyond HEAD and the index) stay separate tickets.

## Before landing

Merge origin/main (never rebase) and take a crew version one past main's from the coordinator. Follow the repo's CLAUDE.md: scope discipline, doc updates for `plugin/crew` changes, and the tooling-PR rule. Run the full suites, the verify gate, the re-anchor and the self-check stamp under heavy-run before each review. Remove `docs/tickets/L-0527/` in the final PR unless the owner wants it kept.
