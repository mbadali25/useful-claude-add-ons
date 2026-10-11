# L-0791 - redraw the config and brief diagrams whose drawn labels are wrong on main

Source: L-0789 (PR #604), lane measurements at origin/main 987ea4fb, 2026-10-11. Owner decision 2026-10-11
(Matthew, relayed by coordinator ac5b48330c1347c0d): #604 lands as the two-diagram PR; the corrections go here.
Not started. Under the 2026-10 crew feature freeze this is a docs refresh, not a feature.

How each was measured: the diagram's `%% Anchors:` paths diffed against its header sha
(`git diff --name-only <anchor>..987ea4fb -- <paths>`), then each cited line and count re-taken with `grep -n` and
by importing crew_config / crew_guards in a worktree at 987ea4fb. "flow" means boxes and arrows read against the
code. Old value -> measured value.

## A. The nine on #600's check-4 list (lane D)

1. `docs/diagrams/data-flow-crew-config-autoclear.mmd` @452b30cc - boxes hold; one note claim wrong. The notes name
   `write_autoclear_method()` / `write_autoclear_enabled()` as the writers; a third exists,
   `apply_onlyRepos_narrowing` (crew_autoclear_setup.py:596; calls `_require_global_readable`, then
   `write_global_config` at :610). Cites: crew_autocycle `settings` :139-184 -> :174 (signature now
   `settings(root, global_path=None)`); writers :239-269 -> :241-271; `_require_global_readable` :107-114 -> :109;
   `_global_file_problem` :69-104 -> :71; `write_global_config` :2820 -> :3736. Not re-taken: :175, :177-178,
   crew_config.py:1623-1624 (AUTOCLEAR_MACHINE_ONLY paths are at :1913-1914 now).
2. `docs/diagrams/data-flow-crew-config-menu.mmd` @452b30cc - flow holds; every box's line number is wrong.
   crew_config_files.py: Lock :104 -> :133; update_json :364 -> :430; move_no_clobber :466 -> :532;
   read_restorable :199 -> :265. crew_config_menu.py: menu_spec :317 -> :328; choices :215 -> :226; save :480 ->
   :491; plan_delete :800 -> :829; apply_delete :852 -> :944; restore_repo_config :962 -> :1068.
   Notes: machine_lock :273 -> :339; read_strict :181 -> :247; state_digest :243 -> :309; replace_text :352 -> :418;
   _unlink_source :418 -> :484; move_aside :508 -> :574; create_bytes :517 -> :583; restorable :171 -> :237;
   _probe_for :168 -> :179; _plan_both :446 -> :457; delete_preview :637 -> :666; _redetected :629 -> :658;
   _unbound :836 -> :865; restore_lines :773 -> :802; _valid_backup :946 -> :1052. Still right: Busy :63,
   LOCK_WAIT_SECONDS :43, ABSENT :50, Conflict :67, Displaced :71. Not re-taken: Lock's ":134-141".
3. `docs/diagrams/data-flow-crew-config-read.mmd` @1d10d8f6 - wrong labels and one missing step.
   Box DEF "crew_config.py:245, 141 leaves" -> :246, 153 leaves. Box TMPL ":432, 81 leaves across 20 blocks" ->
   :448, 89 leaves across 21 blocks. Merge title "resolve_config() ... :820" -> :923. Box M2 "call :854" -> :958.
   Box SCHEMA ":855-858" -> :959-962. Missing step: `resolve_config` runs `_without_machine_only(repo_cfg)` (:956)
   between `without_null_shadows` (:955) and the second merge; not drawn.
   Notes: read_global_config :767 -> :867; _prune :699 -> :799; filter_global :725 -> :825; without_null_shadows
   :676 -> :776; M1 call :853 -> :957; merge_defaults crew_state.py:1385 -> :1295; load_config crew_state.py:267 ->
   :278; crew_common.repo_config_dir :96 -> :149; _common.sh crew_repo_config_dir :328 -> :365;
   promote-gate.ps1 Get-CrewRepoConfigDir :142 -> :545 (cloud-guard.ps1:192, auto-clear.ps1:132,
   handoff-read.ps1:186, handoff-write.ps1:286, context-watch.ps1:29 still right). crew_state: PM_DEFAULTS :1145 ->
   :1055, QA_DEFAULTS :1197 -> :1107, DEV_DEFAULTS :1207 -> :1117, WORKTREE_DEFAULTS :1235 -> :1145,
   CONTEXT_DEFAULTS :770 -> :680, RESUME_DEFAULTS :733 -> :638, AUTOPILOT_DEFAULTS :1133 -> :1042. crew_guards:
   GUARD_DEFAULTS :198 -> :216, PRODUCTION_DEFAULTS :222 -> :241, CLOUD_DEFAULTS :239 -> :258,
   ENVIRONMENTS_DEFAULTS :251 -> :278 (INSTALL_DEFAULTS :48 still right). crew_upgrade: GRAPH_BLOCK :48 -> :51,
   DOCS_BLOCK :107 -> :110, BITBUCKET_BLOCK :150 -> :153, GITHUB_BLOCK :173 -> :176, CHANGE_BLOCK :203 -> :206.
   Note TMPL says "guards (all TEN names)"; ALL_GUARD_NAMES is twelve, and the global template has a 21st block,
   unattendedCloud.
4. `docs/diagrams/data-flow-crew-config-shell-route.mmd` @452b30cc - holds. Notes only: crew_config.py :340 / :579
   -> :346 / :646; crew_shell decide :560 -> :563; status_line :923 -> :926. No box carries a number.
5. `docs/diagrams/data-flow-crew-config-split.mmd` @1d10d8f6 - wrong measured counts in the boxes.
   S1 "81 global-settable leaves across twenty blocks" -> 89 across 21. S2 "60 repo-only leaves" -> 68.
   S3 "141 / 81 / 60" -> 153 repo-template / 89 global / 68 repo-only, and 4 leaves are global-only
   (unattendedCloud), a category the diagram does not have. Note S1 "guards (all TEN)" -> twelve.
   AUTOCLEAR_CONSENT_KEYS crew_state.py:746 -> :656.
6. `docs/diagrams/data-flow-crew-config-two-files.mmd` @452b30cc - holds. Notes only:
   crew_context.load_crew_config :122-133 (and ":121-132" in the numbered block) -> :124-135;
   crew_tracker.resolve :212 -> :267.
7. `docs/diagrams/data-flow-crew-config-unattended.mmd` @1d10d8f6 - wrong labels and a missing step.
   Box UCREAD "resolve_target :345" -> :432. Box CHAIN "run_checks :767" -> :994, and it lists "settings, export,
   identity, sandbox probe"; the code runs settings, version, export, identity, sandbox (the version step is
   missing). Notes: _read_machine :670 -> :893; resolve_config's drop crew_config.py:845 -> :956
   (`_without_machine_only`, def :1917); explain_config's repoIgnored :1730-1785 -> about :1964-2056.
   Its 2026-10-08 re-anchor note says no cited line moved; crew_unattended.py is unchanged since 1d10d8f6, so these
   were already off at that anchor.
8. `docs/diagrams/data-flow-crew-config-write.mmd` @452b30cc - flow holds; box line numbers wrong.
   plan_global_write crew_config.py:2936 -> :3717; GlobalWriteRefused class :2286 -> :2894; plan_repo_write :3136 ->
   :3947; RepoWriteRefused class :2988 -> :3774; repo_widens :3068 -> :3859; write_repo_config :3162 -> :3973.
   Notes: global_snapshot :2887 -> :3626; leaf_updates :2674 -> :3390; value_allowed :2790 -> :3506; MACHINE_REFUSED
   :2710 -> :3426; is_global_path :748 -> :848; null_means :2747 -> :3463; enum_values :2656 -> :3369;
   merged_problems :2849 -> :3587; _content_problem :2822 -> :3560; validate_providers :179 -> :180; _plan_on :2903
   -> :3642; assignments :2693 -> :3409; _widens :2357 -> :2965; write_global_config :2955 -> :3736;
   GlobalWriteConflict :2290 -> :2898; repo_snapshot :3124 -> :3935; machine_view :3155 -> :3966; REPO_REFUSED :3003
   -> :3795; REPO_VETO_ONLY :3024 -> :3816; is_repo_veto :3027 -> :3820; _REPO_WIDENING :3037 -> :3831; is_repo_path
   :3060 -> :3851; RepoWriteConflict :2992 -> :3778. Not re-taken: :2798-2807, :2835-2838, :208-241, :2979, :3194.
9. `docs/diagrams/process-crew-brief-crew-context.mmd` @1d10d8f6 - flow reads right; line numbers wrong in nearly
   every box. Only crew_state.py moved under its Anchors since 1d10d8f6 (+1 line), but the crew_context.py cites
   were already off at that anchor. ".crew/ directory? :993" -> :1156; "read crew.json else config.json :121-132"
   -> :124-135; "memory.inject? :1000-1003" -> :1166; "resume_line :687" -> :831; "additionalContext JSON :1090" ->
   :1261; "crew_state.py:774, :980" -> HANDOFF_ARCHIVE_DIR :722 (the archive code is near :877); the startup
   branch ":908-910" -> about :1069. Notes: _handoff_verdict :638 -> :682; resume_decision :661 -> :705; the stale
   rule crew_state.py:646 -> STALE_HANDOFF_DEFAULTS :584, handoff_staleness :791. Not re-taken: :881-892, :893, :900,
   :911-923, :924, :1086-1089, crew_state :859-914, :954-958.

## B. The other eleven that read stale by the same measure

- `docs/diagrams/data-flow-crew-config-no-python.mmd` @452b30cc - measured: holds. Re-drawn for L-0772 on
  2026-10-11 but its header sha was not moved. One note cite: `_role_write_fallback_decision` :326-346 -> :358-378.
  cloud-guard.sh :40 / :55-78 and env-guard.sh :38 / :53-76 are right.
- `docs/diagrams/process-crew-brief.mmd` @a54ca704 - not yet measured (moved: hooks/hooks.json, crew-context.sh,
  handoff-read.sh).
- `docs/diagrams/process-crew-brief-handoff-read.mmd` @a54ca704 - not yet measured (moved: handoff-read.sh).
- `docs/diagrams/process-crew-brief-platform-sync.mmd` @a54ca704 - not yet measured (moved: crew_platform.py).
- `docs/diagrams/process-crew-brief-status.mmd` @f9ed7ddd - not yet measured (moved: crew_status.py).
- `docs/diagrams/process-crew-lifecycle.mmd` @adb3c2a7 - not yet measured (moved: hooks/hooks.json).
- `docs/diagrams/process-crew-lifecycle-approve.mmd` @f808e5f0 - not yet measured (moved: commands/plan.md,
  hooks/hooks.json, crew_ticket.py, crew_tracker.py).
- `docs/diagrams/process-crew-lifecycle-brainstorm.mmd` @f808e5f0 - not yet measured (moved: commands/brainstorm.md,
  commands/fix.md, crew_tracker.py).
- `docs/diagrams/process-crew-lifecycle-implement.mmd` @adb3c2a7 - not yet measured (moved: hooks/hooks.json). Measured
  defect: reads FAIL in `diagram_check.py` (the file is byte-identical at origin/main 987ea4fb and at b129d3030,
  where it was rendered by `render.sh` and checked). Output line, verbatim, columns Diagram | Verdict | Nodes |
  Crossings | Through a node | Label overlaps | Wordy boxes (warning) | Note:
  `| process-crew-lifecycle-implement.svg | FAIL | 15 | 0 | 0 | 1 | 1 |  |`
  So: 15 nodes, 0 crossings, 0 through a node, 1 label overlap, 1 wordy box. (An earlier line here said "1 crossing,
  1 line through a box"; that was wrong, corrected 2026-10-11.)
- `docs/diagrams/process-crew-lifecycle-review.mmd` @f808e5f0 - not yet measured (moved: commands/review.md,
  crew_autopilot.py, crew_standards.py, review_run.py).
- `docs/diagrams/process-crew-lifecycle-spec-plan.mmd` @f808e5f0 - not yet measured (moved: commands/plan.md,
  commands/spec.md, crew_tracker.py).

Not in this ticket: `process-crew-kimi-agent` (lane D re-anchors it in #600); `data-flow-crew-config.mmd` and
`data-flow-crew-config-ratchet.mmd` (L-0789, #604).

## C. Check 4 cannot be cleared from main for a PR that edits a cited file

`/crew:done` check 4 is per ticket. `plugin/crew/hooks/scripts/crew_refresh_check.py`, `_diagrams`:

```
declared = _declared(body)
reached = code if declared is None else _reached(declared, changed)
if not reached:
    continue
...
status, reason, refreshable = _judge(root, anchor.group(1), reached, untracked)
```

`_judge`:

```
moved = _moved_in_tree(root, sha, reached)
...
if not moved and not new:
    return FRESH, f"nothing it cites moved since {sha[:12]}", False
...
return STALE, f"{_few(sorted(moved))} changed since its anchor {sha[:12]}", True
```

and `_moved_in_tree` is "Which of `paths` differ between `sha` and the WORKING TREE". So a diagram is judged only
when the ticket's own changed paths intersect its Anchors, and a PR that edits a cited file differs from every sha
on main in that file. Re-anchoring on main clears check 4 only for the cited paths the PR did not change itself.
That is also why lane D saw nine and a whole-tree measure sees twenty: there is no check-4 set for main.

**Open consequence, a question for the owner:** this ticket alone does not end the waiver below. Either each PR
re-anchors the diagrams its own diff reaches, in the PR, after merging main; or the check gets its own ticket
(for example: judge only the hunks the PR adds beyond main). Not decided.

## D. A label change is plugin content

`crew_diagrams.py embed` writes each diagram into the README nearest its Anchors, here `plugin/crew/README.md`.
Any box-label correction therefore changes plugin content and needs a crew version bump, a CHANGELOG entry and the
regenerated `docs/diagrams/README.md` and `index.html` (L-0789 did exactly this for one label: crew 1.2.31).

## E. The waiver that names this ticket

Owner, 2026-10-11 (relayed by coordinator ac5b48330c1347c0d): `/crew:done` check 4 is waived for a diagram that was
already stale on main before the PR and was not created by it, for #600, #584, #597 and #603.

## Acceptance Criteria
- Every diagram in A carries the measured values above (or newer ones, re-measured at its new anchor), the two
  missing steps are drawn, and each header names a commit at which nothing it cites has moved.
- Every diagram in B is measured, then re-anchored or corrected the same way; `process-crew-lifecycle-implement`
  passes `diagram_check.py` or its FAIL is filed.
- `render.sh`, `diagram_check.py`, `diagram_doc.py --write`, `crew_diagrams.py embed` run; `crew_diagrams.py check`
  reads fresh; crew version bumped with a CHANGELOG entry.
- Section C's question has an owner answer recorded here.
