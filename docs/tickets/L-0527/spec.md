# L-0527: Kimi review launch in the review harness (tooling half of T-0028)          status: spec   risk: high
Written against origin/main `a555ff37` (2026-10-05). The source is `d4f1e5bc` (local branch `L-0527-source`,
an ancestor of origin/main), and the patch is the split commit reversed: `git diff 524da6a4 524da6a4^ -- <path>`.

## Intent
`/crew:review` can launch Kimi Code as the QA reviewer. `review_run.py --provider kimi` runs the probe
(`kimi_probe.probe`) before preflight and before any round is reserved, and only `ok` launches. The launch
uses the read-only agent file and flags. The review prompt is passed through `prompt_argument(..., exe)`, so a
`.cmd`/`.bat` shim never gets a multi-line inline prompt. The working tree is fingerprinted before and after
(REPO-02). A reviewer write is refused as `EXIT_PROBE_CHANGED` (8), naming the paths, with no round spent
when the probe changed the tree. A write under `graph.out` is set aside, and `graph.out` is resolved through
`crew_common.repo_config_dir`, never set to `.crew`. A surviving reviewer process is stopped. `review_verdict.py`
reads Kimi's stream with `kimi_probe.final_message`, the one parser. Adding `kimi` to `review_run.LAUNCHED` is
what makes the launch gate admit it, and `commands/review.md` stops filtering it out. Every probe and launch
fix has a sabotage entry, including the seven owed from T-0028 rounds 6-7.

## Exclusions
- No feature code and no doc outside `HARNESS`/`ALONGSIDE` (`scripts/check-tooling-pr.py:58-120`). These
  are a follow-up feature PR right after this one: crew-providers `SKILL.md`, `alternative-providers.md`,
  the `kimi_probe.py` docstrings, and `crew_config.py`'s `review_launchable` docstring.
- No change to `kimi_probe.py` behaviour (it is feature code, and the reviewed fixes from rounds 6-7 are on main).
- No working-tree fingerprint for codex or copilot, no redaction of the codex stream error
  (`review_run.py`'s `extra.append(f"codex: {error}")`), and no `.git`-internal write detection beyond HEAD and
  the index. Each is a follow-up carried from T-0028.
- No change to the EXIT_UNVERIFIED/EXIT_PROBE_LIMITED collision (L-0528).
- No edit to `plugin/crew/tests/sabotage.py` beyond registering `KIMI_MUTATIONS`: an import and a `+`
  term. The file has 19 lines of room under `.pylintrc:140` `max-module-lines=3400`.

## Evidence
origin/main `a555ff37` unless marked SRC (`d4f1e5bc`, reachable from main):
- The launch is absent. `plugin/crew/hooks/scripts/review_run.py:181` `LAUNCHED = ("codex", "copilot")`; `:938-941`
  (comment, then `PROVIDERS = ("codex", "copilot", "claude")`); `:952` `--provider ... choices=PROVIDERS`; `:976-978`
  `--probe` is codex only. `review_run.py` is 1006 lines. SRC is 1354 lines, with `LAUNCHED` including `kimi` at `:188`,
  `EXIT_PROBE_CHANGED = 8` at `:175`, `prompt_argument(prompt_path, exe=None)` at `:289`, `tree_fingerprint` at `:437`,
  `graph_out` at `:505` (calling `crew_common.repo_config_dir` at `:525`), and the probe-changed check at `:1020-1034`.
- `plugin/crew/commands/review.md:298-303` hard-codes `("codex", "copilot", "claude")` in the `$ELIGIBLE` filter, and
  `:300` carries the comment "kimi has no review_run.py runner (T-0028)". The probe table row is at `:238`.
- Launch gate: `plugin/crew/hooks/scripts/crew_config.py:2096-2116` `review_launchable()` is `review_run.LAUNCHED | {"claude"}`.
  Its pinned tests are `plugin/crew/tests/test_provider_table.py:2540-2551` (must-block: kimi not eligible) and
  `:2552-2560` (must-allow, via monkeypatch).
- Feature half on main (T-0028, PR #288): `plugin/crew/hooks/scripts/kimi_probe.py` `final_message` `:151`, `launchable` `:194`,
  `redact` `:200`, `kimi_env` `:205`, `write_agent_file` `:214`, `read_only_flags` `:236`, `kimi_home` `:244`, `probe` `:506`;
  `STATES` `:81`. SRC review_run calls `kimi_probe.probe`, `launchable`, `kimi_env`, `redact` and `read_only_flags`, all present.
  `crew_common.repo_config_dir(root)` is at `plugin/crew/hooks/scripts/crew_common.py:137` and returns `(crew_dir, source, detail)`, as SRC expects.
- Parser move: the split commit `524da6a4` took the stream parser out of `review_verdict.py` (-84 lines) and into
  `kimi_probe.final_message`. SRC `review_verdict.py` has its own copy, so it must not be carried over.
- Drift since `524da6a4` (`git rev-list --count 524da6a4..origin/main -- <path>`): `review_run.py` 24 commits
  (+353/-66), `commands/review.md` 33, `tests/sabotage.py` 18, `review_verdict.py` 3, `test_review_verdict.py` 3,
  `test_worktree_config.py` 1, and `review_fixtures.py` 0.
- Files the split removed (`git show --stat 524da6a4`): `plugin/crew/tests/sabotage_kimi.py` (735 lines, `KIMI_MUTATIONS` at SRC `:93`),
  `plugin/crew/tests/test_review_run_kimi.py` (1457), the hunks in `review_fixtures.py` (+197) and `test_review_verdict.py` (+154),
  `test_worktree_config.py` (+28), and the review.md hunks in `test_kimi_docs.py`.
- Round 6/7 probe fixes landed after the split: `66c0ba0e` (round 6 and the launch gate) and `233701d5` (round 7).
  Their tests are marked "their mutations are L-0527's" at `plugin/crew/tests/test_kimi_probe.py:497`, with
  `test_probe_a_non_string_default_model_is_unknown` `:502`, `..._another_providers_credential_is_not_a_login` `:520`,
  `..._an_oauth_credential_it_cannot_locate_is_unknown` `:538`, `..._output_past_the_cap_is_unknown_and_not_kept` `:548`,
  and `..._a_fifo_swapped_in_after_the_check_does_not_block` `:574`.
- Sabotage registration: `plugin/crew/tests/sabotage.py:66-87` (imports) and `:3064-3071` (`MUTATIONS +=`). The file is 3381 lines.
- `.crew/verify.json:527-540` is the Kimi rule, mapping the feature files only.
- Docs that say "lands as L-0527" and are outside `ALONGSIDE`, for the follow-up: `plugin/crew/skills/crew-providers/SKILL.md:368-373`,
  `plugin/crew/skills/crew-providers/alternative-providers.md:10-13`, `plugin/crew/hooks/scripts/kimi_probe.py:14`, `:42`, `:109`,
  and `plugin/crew/hooks/scripts/crew_config.py:2104`. Inside `ALONGSIDE`: `plugin/crew/README.md:1659` (Kimi paragraph),
  `CHANGELOG.md:3691-3697`, `TODO.md:66-69`, `.crew/codemap/crew.md:1896-1928`, `.crew/codemap/verification-harness.md:776`,
  `plugin/crew/tests/kimi_fixtures.py:7`, `:11`, and `plugin/crew/tests/test_kimi_stream.py:4`.
- Harness: `scripts/check-tooling-pr.py:58-87` (`review_*.py`, `sabotage*.py`, `review_fixtures.py`, `commands/review.md`).

## Unknowns
- How much of SRC `review_run.py`'s kimi path conflicts with the 24 commits since the split, among them L-0574's
  `prereview_gate` and the standards gate order. The probe must still run before preflight and reserve. Re-read
  `run`'s order on main before carrying a hunk over.
- Whether main's `tests/kimi_fixtures.py` (the fake kimi) replaces SRC `review_fixtures.py`'s fake-kimi wiring
  completely, or `review_fixtures.py` still needs a thin hook. The default is to reuse `kimi_fixtures`, with no second fake.
- Whether the SRC `graph.out` exemption still matches main's `crew_common.repo_config_dir` semantics after its 4
  commits since the split. The `test_worktree_config.py` graph_out cases decide it.
- The follow-up docs PR's ticket id is minted by the coordinator (not here).
- The next free crew patch version is set at implement time.

## Size and split
About 650 production lines in `review_run.py`, about 30 in `review_verdict.py` (the parser now imported), and
about 25 in review.md. About 1500 test lines (`test_review_run_kimi.py`, plus parts of `test_review_verdict.py`,
`test_worktree_config.py`, `test_kimi_docs.py` and `test_provider_table.py`) and about 780 sabotage lines (SRC's
735 plus 7 owed entries). It is large, but the owner fixed it as one PR ("Split into 2 PRs", 2026-09-30), and
direction Option 2 rejects a further split. Harness: **yes, tooling-only PR**. A small follow-up feature PR
carries the docs outside `ALONGSIDE`.

## Touch
- `plugin/crew/hooks/scripts/review_run.py`
- `plugin/crew/hooks/scripts/review_verdict.py`
- `plugin/crew/commands/review.md`
- `plugin/crew/tests/review_fixtures.py` (only if `kimi_fixtures` cannot be reused as is)
- `plugin/crew/tests/sabotage_kimi.py` (new)
- `plugin/crew/tests/sabotage.py` (registration only)
- `plugin/crew/tests/test_review_run_kimi.py` (new)
- `plugin/crew/tests/test_review_verdict.py`
- `plugin/crew/tests/test_worktree_config.py`
- `plugin/crew/tests/test_kimi_docs.py`
- `plugin/crew/tests/test_provider_table.py`
- `plugin/crew/tests/kimi_fixtures.py` (comment lines only, unless the fake needs a launch mode)
- `plugin/crew/tests/test_kimi_stream.py` (docstring only)
- `.crew/verify.json` (the Kimi rule widened to the harness files and `test_review_run_kimi.py`)
- `plugin/crew/README.md`
- `plugin/crew/docs/external-tool-formats.md` (the review_run/review_verdict citations SRC re-mapped)
- `docs/guides/crew/src/*.md` that describe review providers (re-check `working-with-codex.md` and the provider pages) and the rebuilt HTML, DOCX and PDF (`docs/guides/crew/src/build.py`)
- `.crew/codemap/crew.md`, `.crew/codemap/verification-harness.md`
- `docs/diagrams/` (only if the review lifecycle diagram names the providers launched; say so in the PR if unchanged)
- `CHANGELOG.md`, `TODO.md` (move the carried follow-ups)
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `docs/tickets/L-0527/` (removed in the final PR)

Not in Touch (follow-up feature PR): `plugin/crew/skills/crew-providers/SKILL.md`,
`plugin/crew/skills/crew-providers/alternative-providers.md`, `plugin/crew/hooks/scripts/kimi_probe.py`, and
`plugin/crew/hooks/scripts/crew_config.py`. `plugin/crew/CONFIG.md` has no new key.

## Acceptance checks
Commands from the repo root. Run pytest and the sabotage run through the heavy-run wrapper on a memory-bound host.
`K` is `plugin/crew/tests/test_review_run_kimi.py`.
- [ ] `--provider kimi` probes before preflight and before reserve: a probe state other than `ok` reserves
  nothing and exits with the probe's code; `ok` launches with the read-only agent file and flags.
  `python3 plugin/crew/tests/pytest_rule.py K -q -k "probe"`
- [ ] A reviewer write to the working tree is refused, naming the paths. A tree the probe changed is
  `EXIT_PROBE_CHANGED` (8) with no round spent. A write under `graph.out` is set aside. A `graph.out` that resolves to `.crew`
  is not an exemption. `python3 plugin/crew/tests/pytest_rule.py K plugin/crew/tests/test_worktree_config.py -q -k "fingerprint or graph_out"`
- [ ] A `.cmd`/`.bat` kimi shim gets the prompt by file, never inline and multi-line. A reviewer process that survives is stopped.
  `python3 plugin/crew/tests/pytest_rule.py K -q -k "shim or survivor"`
- [ ] `review_verdict` parses Kimi's stream through `kimi_probe.final_message`, and there is only one parser:
  `grep -n "def .*kimi.*message\|def _kimi_text" plugin/crew/hooks/scripts/review_verdict.py` is empty.
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_verdict.py plugin/crew/tests/test_kimi_stream.py -q`
- [ ] `kimi` is in `review_run.LAUNCHED` and `PROVIDERS`, the launch gate admits it, and review.md's `$ELIGIBLE` filter
  no longer drops it. `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_provider_table.py plugin/crew/tests/test_kimi_docs.py -q`
- [ ] `sabotage_kimi.py`'s `KIMI_MUTATIONS` are registered in `sabotage.py`. They include the 7 owed entries:
  wrong-shaped api_key/oauth reads not-authenticated again; a temp dir inside a repository is allowed again;
  a non-string default_model reads not-authenticated again; any `credentials/` file counts again; the output cap
  is removed; config.toml is stat'ed and then reopened by path again; and `crew_config.review_launchable` admits every QA
  provider again. Each is `RED (good)` in a full `python3 plugin/crew/tests/sabotage.py` run, and the log is
  attached. `wc -l plugin/crew/tests/sabotage.py` is at most 3400.
- [ ] Existing review suites pass:
  `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_review_run_launch.py plugin/crew/tests/test_review_gate.py plugin/crew/tests/test_review_limit.py plugin/crew/tests/test_review_run_prereview.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_kimi_probe.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`, and the harness rule's suites pass
  (`python3 scripts/_test/tooling-pr.py`, the golden replay, seam contracts, and canary review, per `.crew/verify.json`).
- [ ] Docs: README, the guides (rebuilt), `external-tool-formats.md` and the code maps describe the launch and the
  fingerprint. crew is bumped to the next free patch with a CHANGELOG entry, `python3 scripts/check-marketplace.py`
  passes after the commit, and the follow-up docs PR is opened (or its ticket named) in the PR body.

## Dependencies
- T-0028 (feature half, PR #288): merged. It provides the probe, the parser, the fixtures and the launch gate.
- T-0087 (tooling PRs land alone): merged.
- L-0528 (exit-code collision): independent, either order. L-0528 moves `EXIT_UNVERIFIED` to 9 and leaves 8 to this ticket.
- Blocks: the follow-up feature PR for the docs outside `ALONGSIDE`.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
