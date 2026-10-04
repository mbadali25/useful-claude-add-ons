# L-0680: the session hooks inherit the main checkout's repo config in a linked worktree          status: spec   risk: med
Split from T-0096 on 2026-10-04 (slice 1 of 2 further slices). Written against origin/main `155fe6d8` (crew 1.0.322). Needs T-0096 merged first: it uses the resolver T-0096 adds.

## Intent
In a linked git worktree with no crew config of its own, `notify`, `handoff-read`, `handoff-write` and `context-watch`, in both flavours, read the main checkout's `.crew/config.json` (and `crew.json` where they already look for it) through T-0096's resolver. A lane then gets the owner's notifications, handoff path, transcript retention and context thresholds where it got nothing before. The worktree's own files still win whole, nothing is merged, and `unknown` inherits nothing.

## Exclusions
- No harness path: not `verify-gate.*`, `scope-guard.*`, `completion-audit.*`, `review_gate.py`, nor `plugin/crew/tests/sabotage*.py`. Those are L-0681.
- No change to the resolver itself beyond copying the PowerShell function. If the resolver needs a fix, that is its own change to T-0096's files.
- Nothing these hooks write moves: `.crew/transcripts/`, the context-watch marker, the PreCompact record, the event claims and the handoff note stay in the worktree (or under `<git-common-dir>/crew/`, as today).
- The `.crew/` directory gates stay: `context-watch.sh:160`, `context-watch.ps1:34`.
- An inherited relative `context.handoffPath` is resolved against the worktree, not the main checkout.
- No change to what `crew_context.inject_enabled` decides (`handoff-read.sh:41`, already Python and routed), to `auto-clear.*`, or to any Python file.
- The messages that name `.crew/config.json` as the place to set a value (`context-watch.sh:544-557`, `context-watch.ps1:353-370`) are reworded only to name the file in force when it is inherited; no new message.

## Evidence
All read at origin/main `155fe6d8` on 2026-10-04. Paths are under plugin/crew/hooks/scripts/.
- notify.sh:6 `cd "${CLAUDE_PROJECT_DIR:-.}"`, :8 `[ -f .crew/config.json ] || exit 0`, :21 the python heredoc opens `.crew/config.json`. notify.ps1:290-292 the same gate, :302 the read.
- handoff-read.sh:44 the gate, :48 `context.handoffPath`. handoff-read.ps1:227-228.
- handoff-write.sh:12 `[ -f .crew/config.json ] || [ -f .crew/crew.json ] || exit 0`, :61 the crew.json-only early exit, :81 `context.keepTranscripts`, :87 `context.handoffPath`. handoff-write.ps1:297, :356, :378, :386.
- context-watch.sh:160 the directory gate, :174 the config gate, :232-250 the awk pass over `.crew/config.json` for `context.enabled` when python is absent, :313 the python read. context-watch.ps1:34 the directory gate, :140 the config gate, :150 the read.
- crew_common.py:96-126 `repo_config_dir`, the reference behaviour.
- Tests to extend or copy from: plugin/crew/tests/test_context_watch.py, plugin/crew/tests/test_handoff_staleness.py, plugin/crew/tests/test_worktree_config.py:39-46 (`_lane`).
- .crew/verify.json:338-339 maps `handoff-write.*` to the auto-resume rule.
- Docs that state the gap: plugin/crew/README.md:1027-1029, plugin/crew/CONFIG.md:147-148, docs/guides/crew/src/troubleshooting.md:234-236 (their wording after T-0096 lands is what this slice edits).
- None of the eight scripts is in `HARNESS` (scripts/check-tooling-pr.py:58-87).

## Unknowns
- T-0096's function names and output contract (`crew_repo_config_dir` setting `CREW_CFG_DIR` / `CREW_CFG_SOURCE`; `Get-CrewRepoConfigDir`). Resolved by reading T-0096's merged `_common.sh` and `cloud-guard.ps1` before planning; this spec follows whatever landed.
- Several lanes notifying one channel (direction question 1). Accepted as risk; documented.
- `notify.ps1` is also called in-process by `context-watch.ps1` (notify.ps1:299-300). Resolved at plan time: confirm the copied function is defined once per process or is safe to redefine.
- Line numbers move; re-read each site on the build base before planning.

## Touch
- `plugin/crew/hooks/scripts/notify.sh`
- `plugin/crew/hooks/scripts/notify.ps1`
- `plugin/crew/hooks/scripts/handoff-read.sh`
- `plugin/crew/hooks/scripts/handoff-read.ps1`
- `plugin/crew/hooks/scripts/handoff-write.sh`
- `plugin/crew/hooks/scripts/handoff-write.ps1`
- `plugin/crew/hooks/scripts/context-watch.sh`
- `plugin/crew/hooks/scripts/context-watch.ps1`
- `plugin/crew/tests/test_worktree_config_shell.py` - extends T-0096's file
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/skills/crew-context/SKILL.md` - only if it states where these hooks read the config
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/crew-1.0-troubleshooting.html`
- `docs/guides/crew/crew-1.0-troubleshooting.docx`
- `docs/guides/crew/crew-1.0-troubleshooting.pdf`
- `.crew/verify.json` - add the eight scripts to the rule T-0096 created for the shell test
- `.crew/codemap/crew.md`
- `.crew/codemap/INDEX.md`
- `.claude/rules/**` - regenerated
- `docs/diagrams/data-flow-crew-config-read.mmd`
- `docs/diagrams/process-crew-brief-handoff-read.mmd`
- `docs/diagrams/index.html`
- `graphify-out/**` - by graphify update only

Estimated production lines added: about 150 (four PowerShell copies at about 28 each, reader edits about 40). One PR.

## Acceptance checks
Each test builds a throwaway repository and a `git worktree add` lane under `tmp_path`, with `HOME`/`USERPROFILE` pointed at a fixture; no test sends a real notification (the provider is a stub command on a fixture PATH).
Command for all new tests: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_worktree_config_shell.py -q`.
- [ ] `test_notify_in_a_lane_uses_the_main_checkouts_provider[sh|ps1]`: main checkout sets a `notify` block, lane has no config: the stub provider is called once. Red before this change (the hook exits at the gate).
- [ ] `test_notify_in_a_lane_with_its_own_config_ignores_the_main_checkouts[sh|ps1]`: the lane's own config has no `notify` block: nothing is sent.
- [ ] `test_handoff_read_in_a_lane_prints_the_note_at_the_inherited_path[sh|ps1]`: main sets `context.handoffPath: notes/H.md` and `memory.inject: false`; the lane has `notes/H.md`: its text is printed. The main checkout's own `notes/H.md` is never printed.
- [ ] `test_handoff_write_in_a_lane_keeps_the_inherited_transcript_count[sh|ps1]`: main sets `context.keepTranscripts: 2`; three PreCompact runs in the lane leave two files under the **lane's** `.crew/transcripts/`, and the main checkout's `.crew/` gains no file.
- [ ] `test_context_watch_in_a_lane_follows_the_inherited_enabled_false[sh|ps1|sh-no-python]`: main sets `context.enabled: false`: no warning and no marker. The `sh-no-python` case covers the awk path.
- [ ] `test_context_watch_in_a_lane_warns_at_the_inherited_threshold[sh|ps1]`: main sets `context.warnAt` below the fixture transcript's size: the warning is printed once.
- [ ] `test_session_hooks_read_only_their_own_file_when_git_cannot_tell[sh|ps1]`: `.git` a file naming a missing directory: each of the four hooks behaves as with no config.
- [ ] `test_powershell_resolver_copies_are_identical` now covers seven scripts (T-0096's three plus these four).
- [ ] `test_no_session_hook_names_the_own_config_path`: in the eight scripts, no executable line (comments and user-facing message strings excluded by an explicit allowlist with counts) contains `.crew/config.json` or `.crew/crew.json` outside the resolver.
- [ ] Unchanged outside a lane: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_context_watch.py plugin/crew/tests/test_handoff_staleness.py plugin/crew/tests/test_crew_context_wrappers.py -q` (heavy: through heavy-run) and `bash scripts/_test/check-powershell.sh` pass.
- [ ] Hand sabotage, recorded in the PR body: revert one routed gate per hook to the literal `.crew/config.json`; the matching lane test goes red.
- [ ] Feature PR: `python3 scripts/check-tooling-pr.py` exits 0.
- [ ] Docs, in this PR: the "not yet covered" list in README.md, CONFIG.md and troubleshooting.md drops the session hooks (and is removed entirely if L-0681 has already landed); README gains one sentence that a lane notifies with the main checkout's settings and that handoff paths stay relative to the lane; guide html, docx and pdf rebuilt with `python3 docs/guides/crew/src/build.py`; code map, rules and diagrams refreshed.
- [ ] Version: crew bumped once past origin/main in both version files, PLUGINS.md and CHANGELOG; commit, then `python3 scripts/check-marketplace.py` exits 0.

## Dependencies
- T-0096 (direction on 2026-10-04; spec written today): must be merged first.
- T-0088 (merged): the Python reference.
- Blocks nothing. Independent of L-0681; either order.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
