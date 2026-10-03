# T-0050 plan            spec: .work/tickets/T-0050/spec.md

Anchors are origin/main 1e0706ac unless labelled. Each is re-checked with `git grep -n` of the named symbol before its step starts, because T-0010 (branch T-0010-policies abd4f29b, inside T-0029-wave 1f54089e) moves `crew_autopilot.py`, `crew_state.py` and `crew_ticket.py` lines when it lands. If T-0010 is on main when this is built, its `approval` and `questions` get rows in Step 1. If it is not, they are left to T-0010 and the forcing test makes its merge add them (spec, Unknowns). Codex is unavailable until 2026-10-01, so the optional second opinion was skipped and the review is same-family.

## Design (settled; the steps implement it)

The personal table. `crew_guards.PERSONAL_KEYS` maps a dotted path to `(kind, order)`:
- `kind` is `tiers`, `int-min` or `value`;
- `order` is a tuple, strictest first, for `tiers`, and None otherwise;
- `crew_guards.REPO_ONLY_AUTOPILOT` is a frozenset of autopilot keys that are never global. It is empty until T-0011 adds `autopilot.knownFailures`;
- rows at landing: `autopilot.mode` `("off", "plan")`, `autopilot.maxPhases` int-min, `scope.allowCliApproval` `(False, True)`, plus `autopilot.approval` and `autopilot.questions` `("human", "risk", "self")` when T-0010 is on main;
- `crew_state` re-exports both names beside `RATCHETED_KEYS`.

`effective_personal(dotted, repo, global_, default)` returns `(value, held_down_by)`:
- A layer SETS the key when its value is neither `crew_config._MISSING` nor `None`. Callers pass `_MISSING` through as `None`.
- Neither sets it -> `(default, None)`. One sets it -> `(that value, None)`.
- `tiers`, both set: the rank is the index in `order` by exact match (`True is True`, `"self" == "self"`), and -1 for anything else. The lower rank wins, with the repo's value on a tie. `held_down_by` is the layer whose higher-ranked value lost.
- `int-min`: a valid value is an int, not a bool, and >= 1. Two valid -> the smaller. One valid -> that one (the invalid layer is ignored). None valid -> the repo's raw value if set, else the global's, so the reader warns and uses its default.
- `value`: the repo if set, else the global.
- An unknown `dotted` raises KeyError, never falls back.

Layers:
- `default_global_config()` gains `"scope": {"allowCliApproval": False}` and `"autopilot": {<each personal autopilot key>: AUTOPILOT_DEFAULTS[key]}`.
- `PERSONAL_PATHS` = the rows whose path exists in `default_config()`.
- `template_config()` = `default_config()` minus `PERSONAL_PATHS`, dropping a block left empty. `global_template_config()` = `default_global_config()` minus the same paths.
- `resolve_config` runs its merge unchanged. Then, for each personal path, it sets the merged value to `effective_personal(<repo raw>, <filtered global raw>, <default>)[0]`, where the repo raw value is read after `without_null_shadows`, so a repo `null` is silent.
- `resolve_personal(root, dotted, path=None)` returns `{"path", "effective", "repo", "global", "heldDownBy"}`, the same shape as `resolve_ratcheted`.

`cli_approval_allowed(top, global_path=None)`:
- Read the repo file as today (`plugin/crew/hooks/scripts/crew_ticket.py:634-639`). A repo value of exactly `False`, or a repo file that exists and does not parse, returns False before anything else is read.
- Otherwise import `crew_guards` (light) and read the global file at `global_path` or `crew_state.GLOBAL_CONFIG_PATH`. `crew_state` is imported lazily inside this branch only.
- A global file that does not parse is silent.
- Return `effective_personal("scope.allowCliApproval", repo, global, False)[0] is True`.

`crew_backup.py`, standard library plus a lazy `crew_state`:
- `backup_root()` is `$CREW_BACKUP_DIR`, else `dirname(crew_state.GLOBAL_CONFIG_PATH)/backups`.
- `target_dir(path)` is `global` when `realpath(path) == realpath(crew_state.GLOBAL_CONFIG_PATH)`. Otherwise it is `repo/<name>-<sha256(realpath(path))[:10]>`, where `<name>` is the directory that holds `.crew`.
- `backup(path)` returns the stamp, or `None` when `path` does not exist. It raises `BackupError` on any failure. Steps:
  - make the directories 0700;
  - copy the raw bytes to `<stamp>.json` 0600 through a temp file and `os.replace`;
  - write `source` (the absolute path) once;
  - rotate to the newest `KEEP = 20` by stamp.
- `list_backups(path)` returns the stamps, newest first. `read_backup(path, stamp)` returns the bytes, or raises `BackupError`. A stamp outside `^\d{8}T\d{6}Z(-\d+)?$` is refused.
- Rule for every writer: `crew_backup.backup(path)` runs immediately before `os.replace(tmp, path)`. If it raises, the temp file is removed and the write is refused with the reason.

The profile, `dirname(GLOBAL_CONFIG_PATH)/profile.json`:
- `{"schema": 1, "saved_at", "global": {"saved_at", "values": {dotted: value}}, "repos": {<key>: {"saved_at", "path", "values": {...}}}}`.
- `values` holds the leaves of the file that differ from `template_config()` (repo) or `global_template_config()` (global), or that are absent from it. `schema` and `platform.*` are excluded, and unknown keys are kept.
- `profile_key(top)` follows the spec's rule.
- The vault copy is `<memory.vaultPath>/crew/profile.json`, where `memory.vaultPath` comes from `filter_global(read_global_config())` and must be an existing directory.
- `read_profile()` returns `(profile, source_note)`, or raises `ProfileUnreadable` or `ProfileAbsent`, following the spec's both-copies rules.
- Writes go through a temp file and `os.replace`, with the text computed first, and the previous profile is backed up with `crew_backup` under `backups/profile/`.

CLI (`crew_config.py`). The layer flags `--repo` and `--global` are mutually exclusive. `--root` defaults to the cwd.
- `--set PATH=JSON` (existing; global by default) and new `--unset PATH`, both taking `--repo`. A repo path must be a leaf of `default_config()` and never `schema`.
- `--rebuild` (needs `--repo` or `--global`), with `--no-profile`.
- `--restore STAMP` (needs a layer) and `--backups` (needs a layer).
- `--save-profile` (with an optional layer; both layers when none is given).
- `--explain --all`.
- Every write is a dry run until `--apply`.
- Exit codes: 0 ok or dry run; 2 usage or a refused key; 3 could not tell (an unreadable profile); 4 the backup failed, nothing written.

### Step 1: `PERSONAL_KEYS`, the global layer, and templates that do not spell personal keys
Files: plugin/crew/hooks/scripts/crew_guards.py, plugin/crew/hooks/scripts/crew_state.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/hooks/scripts/crew_platform.py, plugin/crew/templates/config.template.json, plugin/crew/templates/global.template.json, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/tests/test_crew_config.py, plugin/crew/tests/test_crew_config_personal.py, plugin/crew/tests/test_platform_sync.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config_personal.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_platform_sync.py plugin/crew/tests/test_change_command.py plugin/crew/tests/test_crew_autopilot.py -q
Risk: high - a wrong rank or a silent layer read as the floor either widens a permission or makes the whole feature inert
- [ ] Tests first, in `test_crew_config_personal.py`. The global file is a scratch file set with `monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", ...)` and the same on `crew_state`, as `conftest.py:25-44` does.
- [ ] Pure `effective_personal` table: every row of the spec's must-block and must-allow lists, plus int-min with one invalid layer, a tie, and an unknown path raising KeyError.
- [ ] Through `resolve_config(root)["autopilot"]` and `crew_autopilot.settings(root)`:
  - `test_global_self_repo_human_resolves_human`
  - `test_global_self_repo_risk_resolves_risk`
  - `test_repo_self_global_human_is_held_down`
  - `test_global_plan_repo_off_resolves_off`
  - `test_global_typo_reads_human_with_warning`
  - `test_global_maxphases_smaller_wins`
  - `test_global_self_repo_silent_resolves_self`
  - `test_global_self_repo_null_resolves_self`
  - `test_non_personal_keys_resolve_as_before`: a snapshot of `resolve_config` over the existing fixture configs, taken before this step
  - The approval and questions cases run only when T-0010's keys are in `AUTOPILOT_DEFAULTS`, and are skipped with that reason otherwise.
- [ ] `test_every_autopilot_key_has_a_personal_row_or_is_repo_only`, `test_no_template_spells_a_personal_key`, `test_global_knownfailures_and_scope_mode_refused` (`plan_global_write` raises `GlobalWriteRefused`, and `filter_global` drops both).
- [ ] Implement per the Design:
  - `PERSONAL_KEYS`, `REPO_ONLY_AUTOPILOT` and `effective_personal` go in `crew_guards.py` after `effective_ratcheted` (`plugin/crew/hooks/scripts/crew_guards.py:524-550`), and are re-exported in `crew_state.py` beside `RATCHETED_KEYS` (`plugin/crew/hooks/scripts/crew_state.py:89`).
  - In `crew_config.py`, `default_global_config()` (`:378-540`) gains the two blocks, with a docstring bullet saying why. `template_config`, `global_template_config`, `PERSONAL_PATHS` and `resolve_personal` are new. The REPO ONLY comments at `:362-374` are rewritten to say which keys are personal.
  - `resolve_config` (`:748-787`) gets the post-merge personal pass.
  - `explain_config` (`:1538-1656`) emits personal rows with `personal`, `heldDownBy`, `repo` and `global`, like its ratchet rows.
  - `_RATCHETED` (`:2357`) gains widening notes for each tiers and int-min personal key, so `_widens` (`:2173-2193`) prints a `!` line for `approval -> self` and for `allowCliApproval -> true`.
- [ ] Regenerate `config.template.json` from `json.dumps(template_config(), indent=2) + "\n"` and `global.template.json` from `global_template_config()`, and rewrite crew-setup's inline copy (`plugin/crew/skills/crew-setup/SKILL.md:168-169`) to match.
- [ ] Point these tests at the template functions: `test_default_config_matches_the_committed_template` (`plugin/crew/tests/test_crew_config.py:47-58`), `test_default_global_config_matches_the_committed_template` (`:61-72`) and the inline-copy test (`:121`). Re-measure the declared-leaf assertion (`:275`), writing the number and its reason in the comment above it.
- [ ] `heal_config` writes `crew_config.template_config()` in place of `default_config()` (`plugin/crew/hooks/scripts/crew_platform.py:295`). Update `test_platform_sync.py`'s expected healed file to match.

### Step 2: `scope.allowCliApproval` from the global layer, through the approval path
Files: plugin/crew/hooks/scripts/crew_ticket.py, plugin/crew/tests/test_crew_ticket.py, plugin/crew/tests/test_scope_guard.py
Test: python3 -m pytest plugin/crew/tests/test_crew_ticket.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_crew_config_personal.py -q
Risk: high - this function decides whether a receipt Claude could write counts; a wrong answer is an unapproved edit let through by the scope guard
- [ ] Tests first:
  - Must-block: `test_cli_approval_global_true_repo_false_is_false`, `test_cli_approval_global_true_repo_corrupt_is_false` and `test_cli_approval_global_corrupt_repo_absent_is_false`.
  - In `test_scope_guard.py`, `test_guard_refuses_cli_receipt_when_repo_false_over_global_true`: a Write inside Touch under a `cli` receipt is refused.
  - Must-allow: `test_cli_approval_global_true_repo_silent_is_true`, and in `test_scope_guard.py` `test_guard_allows_cli_receipt_with_global_true_repo_silent`.
  - `test_cli_approval_matches_resolve_config_matrix`: repo and global each in {absent, `null`, `false`, `true`, `"true"`, corrupt}, 36 cases. `cli_approval_allowed` must equal `resolve_config(root)["scope"]["allowCliApproval"] is True`, with a corrupt repo file as False on both sides.
- [ ] Implement `cli_approval_allowed(top, global_path=None)` per the Design (`plugin/crew/hooks/scripts/crew_ticket.py:634-639`). Its docstring and the module docstring's approval paragraph (`:39-50`) name the global layer and the repo-false rule.
- [ ] Measure the added cost: `python3 -X importtime -c "import crew_ticket; crew_ticket.cli_approval_allowed('.')"`, before and after, from `plugin/crew/hooks/scripts`. Record both numbers in the commit message. More than 20 ms added is a stop to report, not a number to tune around.

### Step 3: `crew_backup.py` and a backup before every crew config write
Files: plugin/crew/hooks/scripts/crew_backup.py, plugin/crew/hooks/scripts/crew_config.py, plugin/crew/hooks/scripts/crew_platform.py, plugin/crew/hooks/scripts/crew_autoclear_setup.py, plugin/crew/skills/crew-graph/scripts/crew_upgrade.py, plugin/crew/tests/conftest.py, plugin/crew/tests/test_crew_backup.py, plugin/crew/tests/test_autoclear_setup.py, plugin/crew/tests/test_upgrade.py, plugin/crew/tests/test_platform_sync.py
Test: python3 -m pytest plugin/crew/tests/test_crew_backup.py plugin/crew/tests/test_autoclear_setup.py plugin/crew/tests/test_upgrade.py plugin/crew/tests/test_platform_sync.py plugin/crew/tests/test_crew_config.py -q
Risk: high - a writer that skips its backup loses the owner's values silently, which is this ticket's whole problem; a writer that writes after a failed backup is the same failure
- [ ] `conftest.py`: the autouse fixture (`plugin/crew/tests/conftest.py:25-44`) also runs `monkeypatch.setenv("CREW_BACKUP_DIR", str(tmp_path / "crew-backups"))`, so pytest subprocesses inherit it.
- [ ] Tests first, in `test_crew_backup.py`:
  - Unit: `test_backup_copies_raw_bytes_including_corrupt`, `test_backup_absent_file_returns_none`, `test_backup_rotation_keeps_newest_20`, `test_backup_same_second_collision_suffix`, `test_backup_dirs_private` (0700 and 0600; skipped on Windows, and named), `test_read_backup_refuses_bad_stamp` (`../x`, `latest`), and `test_target_dir_global_vs_repo`.
  - Per writer: a backup appears before the replace, and with an unwritable backup root (a file where the directory should be) the write is refused and the target stays byte-identical:
    - `test_write_global_config_backs_up_first` and `test_write_global_config_refuses_without_backup`
    - `test_heal_config_backs_up_first` and `test_heal_config_refuses_without_backup`
    - `test_apply_changes_backs_up_first` and `test_apply_changes_refuses_without_backup`
    - `test_autoclear_repo_write_backs_up_first` and `test_autoclear_repo_write_refuses_without_backup`
    - `test_upgrade_backs_up_first` and `test_upgrade_refuses_without_backup`
- [ ] Create `crew_backup.py` per the Design. Its module docstring lists every writer that calls it, by function.
- [ ] Wire `crew_backup.backup` immediately before each `os.replace`:
  - `write_global_config` (`plugin/crew/hooks/scripts/crew_config.py:2536-2580`);
  - `heal_config` (`plugin/crew/hooks/scripts/crew_platform.py:295-301`), after its existing `.broken` slot logic, which stays;
  - `apply_changes` (`:420-447`);
  - `crew_autoclear_setup._atomic_write_json` (`plugin/crew/hooks/scripts/crew_autoclear_setup.py:451-463`), and the batch in `apply_migrate_to_repo`, for the `config.json` entry only (`:636-653`). A failed backup refuses the whole batch before its first replace;
  - `crew_upgrade` (`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1328-1346`), after the existing one-time `backup_config`, which stays.
  - A refusal surfaces through each writer's existing error path: `heal_config` returns `(None, message)`, `apply_changes` reports and leaves the file, `write_global_config` raises `BackupError`, which `main` maps to exit 4, and the upgrade reports and stops.
- [ ] Run the full suite once with `ls -laR ~/.claude/crew/backups` before and after. The two listings must be identical, and a missing directory counts as identical to a missing directory. Record the result in the commit message.

### Step 4: repo writes, `--set` and `--unset` with `--repo`, and the profile
Files: plugin/crew/hooks/scripts/crew_config.py, plugin/crew/tests/test_crew_config_rebuild.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config_rebuild.py -q -k "set or unset or profile"
Risk: med - a repo writer that replaces rather than merges drops keys; a profile refreshed from a defaults write erases the owner's values
- [ ] Tests first:
  - `test_set_repo_dry_run_writes_nothing`, `test_set_repo_apply_merges_and_backs_up`, `test_set_repo_refuses_schema`, `test_set_repo_refuses_unknown_path`
  - `test_unset_repo_removes_one_leaf_and_keeps_siblings`, `test_unset_global_personal_key`
  - `test_profile_refreshed_after_set_apply`: only that layer's section changes
  - `test_profile_values_exclude_schema_and_platform`
  - `test_profile_keeps_unknown_keys`
  - `test_profile_key_normalises_origin`: `git@github.com:O/R.git`, `https://user:tok@GitHub.com/O/R/` and `ssh://git@github.com/O/R` all give `github.com/O/R`, and a repo with no origin gives `path:<realpath>`
  - `test_save_profile_dry_run_then_apply`
  - `test_vault_copy_written_when_vault_path_set`, `test_no_vault_copy_when_vault_path_missing_dir`
  - `test_defaults_writers_never_touch_profile`: `heal_config`, `apply_changes`, an upgrade and `crew_autoclear_setup`'s repo write each leave `profile.json` byte-identical
- [ ] Implement:
  - `plan_repo_write(root, sets, unsets)` and `write_repo_config(...)`: merge onto the current parsed file and never replace. A corrupt current file is refused here ("use --rebuild --repo").
  - `plan_global_write` gains `unsets`.
  - `profile_key`, `profile_section(cfg, template)`, `read_profile`, `write_profile` (it backs up the old profile first) and `refresh_profile(layer, root)`, called after each successful `write_global_config` or `write_repo_config` from `main`.
  - The CLI flags `--repo`, `--global`, `--unset` and `--save-profile`.

### Step 5: `--rebuild`, `--restore` and `--backups`
Files: plugin/crew/hooks/scripts/crew_config.py, plugin/crew/tests/test_crew_config_rebuild.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config_rebuild.py -q
Risk: high - a rebuild that writes on a dry run, or from a profile it could not read, replaces the owner's file with defaults
- [ ] Tests first:
  - Must-block, each writing nothing, taking no backup and leaving the profile unchanged:
    - `test_rebuild_never_writes_without_apply`: file bytes and mtime unchanged
    - `test_rebuild_profile_unreadable_exit_3`
    - `test_rebuild_profile_absent_refused_without_no_profile`
    - `test_rebuild_needs_a_layer`
    - `test_restore_unknown_stamp_exit_2`
    - `test_restore_dry_run_writes_nothing`
    - `test_rebuild_refuses_when_backup_fails_exit_4`
  - Must-allow:
    - `test_corrupt_repo_rebuilt_from_profile`: the dry run lists each leaf to be written with `!` on widenings; `--apply` writes `template_config()` plus the profile's values; the corrupt bytes are the newest backup
    - `test_missing_repo_config_rebuilt_from_profile`
    - `test_rebuild_global_from_profile`
    - `test_rebuild_no_profile_writes_template`
    - `test_vault_copy_newer_wins_and_is_named`
    - `test_vault_copy_unreadable_uses_home_copy_and_says_so`
    - `test_restore_roundtrip`: the current file is backed up first, then the stamped bytes land
    - `test_backups_lists_newest_first`
- [ ] Implement:
  - `plan_rebuild(root, layer, use_profile=True)` returns `(target_text, changes, notes)`, where `changes` is a list of `{"path", "before", "after", "widens"}` and `notes` names the current file's state (ok, absent, or corrupt with N bytes) and the profile source. A readable current file's `platform` block is carried into a repo target.
  - `apply_rebuild(...)` backs up, then writes through a temp file and `os.replace`.
  - `plan_restore` and `apply_restore`, and `--backups`. `main` wires these flags with the exit codes from the Design.

### Step 6: `--show` - every value's layer, shadows and profile drift
Files: plugin/crew/hooks/scripts/crew_config.py, plugin/crew/tests/test_crew_config_personal.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config_personal.py -q -k "show or explain"
Risk: med - a layer column that disagrees with the run is the failure `explain_config`'s own docstring records; it reads as "you have it"
- [ ] Tests first:
  - `test_explain_all_lists_every_default_config_leaf` (count equal to `len(leaf_paths(default_config()))`)
  - `test_explain_all_marks_repo_only`
  - `test_explain_personal_row_matches_resolve_config`: for every personal key and fixture, the row's value is `resolve_config`'s
  - `test_explain_names_held_down_layer`
  - `test_shadow_finding_names_key_and_unset_command`
  - `test_no_shadow_when_global_silent`
  - `test_profile_drift_finding`
  - `test_explain_all_writes_nothing`
- [ ] `explain_config(root, path=None, all_keys=False)`:
  - With `all_keys`, it covers `leaf_paths(default_config())` as well. A repo-only row carries `"repoOnly": True` and a source of `repo` or `default`.
  - `_print_explain` (`plugin/crew/hooks/scripts/crew_config.py:2583`) prints `repo-only`, `held down by <layer>` and the findings block:
    - `shadow: <path> = <value> in .crew/config.json equals the built-in default and hides your global <value>; remove it with /crew:config --unset <path> --repo --apply`
    - `profile drift: <path> file=<v> profile=<v>`
- [ ] `--explain` without `--all` keeps its current rows, so `/crew:upgrade`'s reading is unchanged.

### Step 7: the walkthrough, the command and the docs
Files: plugin/crew/commands/config.md, plugin/crew/skills/crew-setup/global-config.md, plugin/crew/hooks/scripts/crew_platform.py, plugin/crew/CONFIG.md, plugin/crew/README.md
Test: python3 -m pytest plugin/crew/tests/test_crew_config_personal.py -q -k "docs"; (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)
Risk: low - prose, but the command file is what the session follows
- [ ] Tests first:
  - `test_config_md_names_every_new_flag`: `--rebuild`, `--restore`, `--backups`, `--unset`, `--repo`, `--save-profile` and `--apply`
  - `test_config_md_no_longer_says_it_never_writes_repo_file`
  - `test_heal_message_names_rebuild`
- [ ] `config.md`:
  - `--show` runs `--explain --all`, then `--check-global`.
  - New sections for `--rebuild`, `--restore`, `--backups`, `--set`/`--unset --repo` and `--save-profile`, each a dry run, then the owner's yes, then `--apply`.
  - Replace the "does not write `.crew/config.json`" sentence (`plugin/crew/commands/config.md:35-37`) with the four routes that do.
- [ ] `global-config.md`:
  - A rule for personal keys: the stricter layer wins, and a silent layer imposes nothing.
  - Step 2 asks about `autopilot.mode`, `autopilot.approval`, `autopilot.questions`, `autopilot.maxPhases` and `scope.allowCliApproval`, and reads each `!` line back.
  - Step 4 says what was backed up and where.
  - The stop list at `:97-99` is untouched here (T-0049 owns it).
- [ ] The `heal_config` message (`plugin/crew/hooks/scripts/crew_platform.py`, the message beside `:295`) adds: "your saved values: /crew:config --rebuild --repo".
- [ ] CONFIG.md:
  - a new section "Personal keys and the per-key ratchet", with the table and the rule;
  - section 10 ("Global-settable keys", `plugin/crew/CONFIG.md:636`) and section 11 ("Repo-only keys", `:740`) re-counted by running `leaf_paths` and `is_global_path`, not by hand;
  - a "Backups, profile and rebuild" section.
- [ ] README (`plugin/crew/README.md:851`, `:884`): global defaults, the profile, rebuild, restore and backups.

### Step 8: sabotage, one mutation per refusing branch
Files: plugin/crew/tests/sabotage_config_layers.py, plugin/crew/tests/sabotage.py
Test: python3 plugin/crew/tests/sabotage.py - every new entry red with a real failure and no ANCHOR LOST; each run alone by hand first (copy aside, mutate, run, restore, `cmp`)
Risk: low for the code, high if skipped
- [ ] `sabotage_config_layers.py` defines `CONFIG_LAYER_MUTATIONS` in the `(label, target, find, replace, test)` shape of `plugin/crew/tests/sabotage_autopilot.py`. `sabotage.py` imports it beside its siblings and appends it to `MUTATIONS`; both anchors are re-read with `git grep -n "MUTATIONS +="`.
- [ ] Mutations, each with the test it turns red:
  - `min` -> `max` in `effective_personal`'s tiers branch -> `test_global_self_repo_human_resolves_human`
  - a silent layer treated as the floor -> `test_global_self_repo_silent_resolves_self`
  - unknown ranked above the floor -> `test_global_typo_reads_human_with_warning`
  - int-min takes the larger -> `test_global_maxphases_smaller_wins`
  - `cli_approval_allowed` skips the repo-false short-circuit -> `test_cli_approval_global_true_repo_false_is_false`
  - `cli_approval_allowed` reads a corrupt repo as silent -> `test_cli_approval_global_true_repo_corrupt_is_false`
  - `template_config` keeps `autopilot.mode` -> `test_no_template_spells_a_personal_key`
  - `plan_rebuild` writes -> `test_rebuild_never_writes_without_apply`
  - an unreadable profile read as absent -> `test_rebuild_profile_unreadable_exit_3`
  - `write_global_config` skips `backup` -> `test_write_global_config_backs_up_first`
  - `heal_config` writes after a `BackupError` -> `test_heal_config_refuses_without_backup`
  - rotation sorts ascending and deletes the newest -> `test_backup_rotation_keeps_newest_20`
  - `apply_restore` skips backing up the current file -> `test_restore_roundtrip`
  - `heal_config` calls `refresh_profile` -> `test_defaults_writers_never_touch_profile`
  - `resolve_config` skips the personal pass -> `test_repo_self_global_human_is_held_down`
  - `explain_config` prints the merged value for a personal key -> `test_explain_personal_row_matches_resolve_config`
- [ ] Must-allow non-vacuity: `effective_personal` ignores the global layer -> `test_global_self_repo_silent_resolves_self` (a second, independent mutation of the same test).
- [ ] Record in the commit message that each went red alone.

### Step 9: verify rule, version, budgets
Files: .crew/verify.json, plugin/crew/BUDGETS.md, plugin/crew/.claude-plugin/plugin.json, plugin/PLUGINS.md, .claude-plugin/marketplace.json, CHANGELOG.md
Test: python3 scripts/check-marketplace.py; python3 scripts/_test/self-claims.py; python3 -m pytest plugin/crew/tests/ -q; python3 plugin/crew/tests/sabotage.py
Risk: low - version drift and self-claims are caught by check-marketplace
- [ ] `.crew/verify.json` gets a new rule:
  - paths: `crew_guards.py`, `crew_config.py`, `crew_backup.py`, `crew_ticket.py`, `test_crew_config_personal.py`, `test_crew_config_rebuild.py`, `test_crew_backup.py` and `sabotage_config_layers.py`
  - run: `python3 -m pytest plugin/crew/tests/test_crew_config_personal.py plugin/crew/tests/test_crew_config_rebuild.py plugin/crew/tests/test_crew_backup.py plugin/crew/tests/test_crew_config.py plugin/crew/tests/test_crew_ticket.py -q`
  - `seconds` timed on this machine, and a `why` naming the measurement and `reach: local`
- [ ] Re-measure BUDGETS.md's `crew-markdown-lines` claim.
- [ ] Set the crew version to one patch above origin/main's crew version at landing, in plugin.json, marketplace.json and PLUGINS.md, in the last plugin/crew commit. The CHANGELOG entry flags three behaviour changes:
  - new repos no longer spell the personal keys, and existing ones are shown their shadows;
  - `/crew:config` can write `.crew/config.json`, only through `--apply`;
  - a global value holds a wider repo value down.
