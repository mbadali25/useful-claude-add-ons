# T-0038 plan            spec: .work/tickets/T-0038/spec.md

Work in a fresh worktree, `/repos/personal/uca-t-0038`, on branch `T-0038-build`, cut from origin/main (`502cb137` or later). Every line number below is origin/main's at `502cb137`. Re-grep each quoted string before editing, because other tickets land in between. This is data-safety work. For one file, and only for a pre-0.20 config, migrate stops being "never overwrites". The in-process undo and `--rollback` must put the user's original `config.json` back byte-identical, and never remove it. Each behaviour gets must-allow and must-block tests, and a sabotage mutation that must go red. There is no second opinion (step 3 of `/crew:plan`): the design is direction.md's approved recommendation, and the spec's Unknowns record the two decisions it leaves (stub, and schema 1 to 6). Heavy runs are serial under `flock /root/crew-tmp/heavy.lock`, with `TMPDIR=/root/crew-tmp/t-0038`.

### Step 1: the upgrade stage in the plan (preview)
Files: plugin/crew/tests/test_migrate.py, plugin/crew/hooks/scripts/crew_migrate.py
Test: python3 -m pytest plugin/crew/tests/test_migrate.py -q -p no:cacheprovider
Risk: high. If the stage is too wide, a 0.20 config gets rewritten. If it is too narrow, a pre-0.20 repo stays stranded. If the unmigrated check goes missing, a half-upgraded config reaches crew.json.
- [ ] In `test_migrate.py`, add the helper `_write_config(repo, cfg)`. Also add `V1_CONFIG = {"tier": 0, "tracker": "files"}`, which has no `schema` key, the same shape as `test_upgrade.py:411-412`.
- [ ] Write the must-allow tests:
  - `test_pre_0_20_preview_shows_both_stages_and_writes_nothing`, parametrised `[absent, 3]`. The snapshot before equals the one after. The output contains `upgrade  .crew/config.json` and `## Config`.
  - `test_schema_7_config_is_never_rewritten`: the fixture config, `--apply`, and `config.json`'s `(sha256, mtime_ns)` is unchanged.
- [ ] Write the must-block tests:
  - `test_unmigrated_block_is_a_conflict_and_nothing_is_written`: `{"qa": "oops"}` with no schema. `--apply` exits 1, the snapshot is unchanged, and stderr or stdout names `qa`.
  - `test_schema_zero_or_negative_is_refused`, parametrised `[0, -1]`. Exit 1, snapshot unchanged.
- [ ] Run them and watch them fail.
- [ ] Update `_load_legacy` (`crew_migrate.py:316-338`):
  - A missing `schema` key returns the config with `upgrade_from = None`.
  - An int (not bool) from 1 to `crew_state`'s `SCHEMA_CURRENT - 1` returns `upgrade_from = schema`.
  - An int of 0 or less raises `MigrateError(".crew/config.json schema {n} is not a schema crew ever wrote; nothing is migrated")`.
  - The present-non-int refusal at `:327-331` and the `> LEGACY_SCHEMA_MAX` refusal at `:332-335` stay byte-identical.
  - Add a module-level `_upgrade_module()`. It puts `os.path.join(<this file's dir>, os.pardir, os.pardir, "skills", "crew-graph", "scripts")` on `sys.path` if it is absent, then imports and returns `crew_upgrade`. On `ImportError` or `OSError` it raises `MigrateError(f"cannot load crew_upgrade from {path}: {exc} - a pre-0.20 config needs it; nothing is migrated")`. It is called only when the upgrade stage runs, so a schema-7 migrate never imports it.
- [ ] Change `build_plan`'s config branch (`crew_migrate.py:463-477`) when the stage runs:
  - Call `upgraded, notes = crew_upgrade.upgrade_config(copy.deepcopy(cfg))`.
  - If `notes["unmigrated"]` is non-empty, append the conflict `.crew/config.json: the pre-0.20 upgrade left these blocks unmigrated (wrong type, left as written): <list> - fix them by hand, then preview again`, and add no config or crew.json write.
  - Otherwise, insert this as `plan["writes"][0]`: `{"path": ".crew/config.json", "data": _config_bytes(upgraded), "why": f"upgrade: schema {from or 'absent'} -> {SCHEMA_CURRENT} (crew_upgrade.upgrade_config)", "pre_sha256": _sha(raw), "replaces": True, "original": raw}`.
  - Put `crew_upgrade._absent_global_headline(notes)` (when not None) followed by `crew_upgrade._config_lines(notes)` into `plan["upgrade"]`.
  - Build crew.json from `upgraded`, and assert `to_legacy(crew) == upgraded`.
  - Append to crew.json's `notes`: `f"config.json upgraded from schema {from or 'absent'} to {SCHEMA_CURRENT} in the same apply (crew_upgrade.upgrade_config); rollback restores the original"`.
- [ ] Add `_config_bytes(cfg)`, which returns `(json.dumps(cfg, indent=2, sort_keys=True) + "\n").encode("utf-8")`.
- [ ] Update `render_plan` (`:531-550`). Replacing writes print as `  upgrade  {path}  ({why})`, not `write`. Each `plan["upgrade"]` line prints as `  upgrade  {line}`.
- [ ] Update the module docstring (`:1-72`). The table gains the `.crew/config.json` (no schema, or 1-6) row: upgraded in place, then migrated, original restored by rollback. The "Nothing a user owns is deleted or moved in place" paragraph (`:21-24`) names that one exception. "Standard library only" becomes "Standard library, plus crew's own `crew_upgrade` for a pre-0.20 config".
- [ ] Run the Test command.

### Step 2: apply writes config.json in place, and the in-process undo restores it
Files: plugin/crew/tests/test_migrate.py, plugin/crew/hooks/scripts/crew_migrate.py
Test: python3 -m pytest plugin/crew/tests/test_migrate.py -q -p no:cacheprovider
Risk: high. If the undo is wrong, a crash deletes the user's only config.
- [ ] Write the must-allow tests:
  - `test_pre_0_20_config_upgrades_then_migrates_in_one_apply`, parametrised `[absent, 3]`. After `--apply`, `json.loads(config.json) == crew_upgrade.upgrade_config(original)[0]`, `crew.json`'s `migratedFrom.schema == 7`, and a `notes` entry names the original schema.
  - `test_pre_0_20_second_apply_is_a_no_op`: the second `--apply` prints `nothing to write`, and the snapshot is unchanged.
  - `test_upgraded_config_bytes_match_crew_upgrade_run`: two copies of the V1 repo, one through `crew_migrate --apply` and one through `crew_upgrade.run(root, {})`. `config.json` bytes are equal (Linux).
- [ ] Write the must-block test `test_crash_mid_apply_on_a_pre_0_20_repo_restores_config_json`, parametrised `fail_at [1, 2, "last"]`. Model it on `test_crash_mid_apply_leaves_the_old_tree` (`test_migrate.py:216-239`) with the V1 config. Assert that the whole-tree bytes equal `before` and that `config.json` exists.
- [ ] Watch them fail.
- [ ] In `apply_plan` (`crew_migrate.py:598-672`):
  - The manifest target for a replacing write becomes `{"path", "existed": True, "sha256": new, "originalSha256": pre_sha256}`. `createdDirs` ignores it.
  - `.crew/config.json` is already in `sources` (`:623-626`), so the backup is taken before the manifest is written.
  - In the `except BaseException` block (`:662-670`), a landed path whose item has `replaces` is restored with `atomic_write(path, item["original"])` instead of `_remove`. Keep a `landed` list of `(item, path)`.
- [ ] Run the Test command, including every existing test unchanged.

### Step 3: rollback restores config.json
Files: plugin/crew/tests/test_migrate.py, plugin/crew/hooks/scripts/crew_migrate.py
Test: python3 -m pytest plugin/crew/tests/test_migrate.py -q -p no:cacheprovider
Risk: high. If rollback trusts a forged manifest, it could restore arbitrary bytes over `config.json`.
- [ ] Write the must-allow tests:
  - `test_pre_0_20_rollback_restores_config_json_byte_identical`: the `_bytes_only(_snapshot)` before apply equals the one after rollback, and exit is 0.
  - `test_hard_kill_before_config_replace_rolls_back_without_touching_it`: set the manifest to `committing` and put `config.json` back to its original bytes by hand. Rollback exits 0, and `config.json` is unchanged.
- [ ] Write the must-block tests:
  - `test_rollback_refuses_when_config_json_was_edited_after_apply`: append a space. Exit 1, and `crew.json` is still present.
  - `test_rollback_refuses_when_the_backed_up_original_does_not_match_the_manifest`: edit `<backup>/sources/.crew/config.json`. Exit 1, nothing changed.
  - `test_rollback_refuses_a_config_target_without_an_original_hash`: delete `originalSha256` from the manifest entry. Exit 1, nothing changed.
- [ ] Watch them fail.
- [ ] Change `_TARGET_RE` (`:145-148`) to also accept `\.crew/config\.json`. In `_manifest_entries` (`:698-721`), a `.crew/config.json` target must carry `existed is True` and a str `originalSha256`. Any other target must carry `existed` False or no `existed` key. Otherwise raise the existing "which migrate never writes; refusing the whole rollback".
- [ ] In `rollback` (`:724-767`), before any change, read `<backup>/sources/.crew/config.json` for each `existed` target, and refuse unless its sha equals `originalSha256`. The edited check: current sha equal to `sha256` means restore, equal to `originalSha256` means already original and nothing to do, anything else means edited and is refused. Restore with `atomic_write`, never `os.remove`. The staged-temp cleanup loop stays.
- [ ] Run the Test command.

### Step 4: the CLI works from a clean interpreter, and a missing crew_upgrade is refused
Files: plugin/crew/tests/test_migrate.py, plugin/crew/hooks/scripts/crew_migrate.py
Test: python3 -m pytest plugin/crew/tests/test_migrate.py -q -p no:cacheprovider -k "cli or missing_crew_upgrade"
Risk: med. The test `context.py` hides a missing `sys.path` insert (`plugin/crew/tests/context.py`).
- [ ] Write `test_crew_migrate_cli_upgrades_a_pre_0_20_repo_from_a_clean_interpreter`. It runs `subprocess.run([sys.executable, CREW_MIGRATE, "--root", repo], env={**os.environ, "PYTHONPATH": ""}, cwd=tmp_path, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False)` on the V1 repo, and asserts exit 0 with `upgrade  .crew/config.json` in stdout.
- [ ] Write the must-block test `test_missing_crew_upgrade_is_refused_and_nothing_written`. It monkeypatches `crew_migrate._upgrade_module` to raise `crew_migrate.MigrateError("cannot load crew_upgrade ...")`. Then it monkeypatches `builtins.__import__` so `crew_upgrade` raises `ImportError` and calls the real `_upgrade_module` once. `--apply` exits 1 and the snapshot is unchanged in both cases.
- [ ] Run the Test command, then the whole `test_migrate.py`.

### Step 5: crew_upgrade's user-facing strings name /crew:migrate
Files: plugin/crew/skills/crew-graph/scripts/crew_upgrade.py, plugin/crew/tests/test_upgrade.py
Test: python3 -m pytest plugin/crew/tests/test_upgrade.py plugin/crew/tests/test_guards.py plugin/crew/tests/test_install_policy.py -q -p no:cacheprovider
Risk: low. `crew_upgrade.main`'s structure is untouched, so `test_guards.py:234` and the `sabotage.py` UPGRADE anchors hold.
- [ ] Add `test_unmigrated_report_points_at_migrate`: `_config_lines(upgrade_config({"qa": "oops"})[1])` contains `/crew:migrate` and does not contain "run `/crew:upgrade` again". Watch it fail.
- [ ] At `crew_upgrade.py:1136`, change the text to "run `/crew:migrate` again". At `:1490`, change it to `"schema was not stamped; fix these and re-run /crew:migrate"`. `:1140` ("may be pinned by an earlier /crew:upgrade") stays, because it is historical and asserted at `test_upgrade.py:450` and `:1219`.
- [ ] Update the `_absent_global_headline` docstring (`:1212-1214`) to say the other `--check-global` findings live in `/crew:config`, because upgrade.md step 4b is gone.
- [ ] Run the Test command.

### Step 6: sabotage for the new behaviour
Files: plugin/crew/tests/sabotage_migrate.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0038 python3 plugin/crew/tests/sabotage.py
Risk: med. A mutation whose anchor is not unique, or that stays green, means the matching test is vacuous.
- [ ] Append to `MIGRATE_FIX_MUTATIONS`, each with the exact anchor text as implemented in steps 1-3:
  - "migrate refuses an absent schema again": the absent-key branch replaced by the old refusal. It goes red on `test_pre_0_20_config_upgrades_then_migrates_in_one_apply`.
  - "migrate skips the upgrade stage": `upgraded` set to `cfg`. It goes red on `test_pre_0_20_config_upgrades_then_migrates_in_one_apply`.
  - "migrate ignores unmigrated blocks": the `if notes["unmigrated"]` condition set to `False`. It goes red on `test_unmigrated_block_is_a_conflict_and_nothing_is_written`.
  - "in-process undo removes config.json": the restore call replaced with `_remove(path)`. It goes red on `test_crash_mid_apply_on_a_pre_0_20_repo_restores_config_json`.
  - "rollback removes config.json": the restore replaced with `os.remove(path)`. It goes red on `test_pre_0_20_rollback_restores_config_json_byte_identical`.
  - "rollback skips the backup hash check": the check removed. It goes red on `test_rollback_refuses_when_the_backed_up_original_does_not_match_the_manifest`.
  - "manifest config target needs no existed flag": the `existed is True` requirement dropped. It goes red on `test_rollback_refuses_a_config_target_without_an_original_hash`.
- [ ] Run the Test command. Every new entry must report RED, and the whole run must end with the tree restored. Confirm with `git status --porcelain plugin/crew`, which shows only this ticket's edits.

### Step 7: upgrade.md becomes a stub, and the per-hop text moves to crew-setup
Files: plugin/crew/commands/upgrade.md, plugin/crew/skills/crew-setup/upgrade-report.md, plugin/crew/tests/test_upgrade.py, plugin/crew/tests/sabotage.py, plugin/crew/tests/test_migrate.py, plugin/crew/.budget-allowance.json, scripts/_test/instruction-budgets.py, plugin/crew/BUDGETS.md
Test: python3 -m pytest plugin/crew/tests/test_upgrade.py plugin/crew/tests/test_migrate.py -q -p no:cacheprovider && python3 scripts/check_instructions.py && python3 scripts/_test/instruction-budgets.py
Risk: med. The allowance, the Windows count and the markdown-lines claim all move together.
- [ ] Rename `test_upgrade_md_documents_the_current_migration` (`test_upgrade.py:1444-1451`) to `test_upgrade_report_documents_the_current_migration`. Point it at `skills/crew-setup/upgrade-report.md`. Watch it fail, because the file does not exist yet.
- [ ] Add `test_upgrade_command_is_a_removal_stub` to `test_migrate.py`. `commands/upgrade.md` has 12 lines or fewer, its description starts with `Removed`, it names `/crew:migrate`, and it contains neither `crew_upgrade.py` nor a fenced block. Watch it fail.
- [ ] Create `plugin/crew/skills/crew-setup/upgrade-report.md`, titled `# Relaying a pre-0.20 upgrade (read by /crew:migrate)`. Carry over the following:
  - the NO MACHINE-GLOBAL CONFIG headline rule (`upgrade.md:107-117`), pointing at `/crew:config` and `crew_config.py --check-global`;
  - the "Blocks left unmigrated" and "May be pinned by an earlier upgrade" bullets;
  - every `**Schema N → N+1**` bullet from `upgrade.md:182-271`, verbatim, including `**Schema 6 → 7**`;
  - the global-theme warning (`:272-279`);
  - the "did not do" list from `:341-363`, minus the codemap, graph and model-pin lines that no longer apply.
  Leave out the model table (`:295-339`), per the spec's Exclusions.
- [ ] Replace `commands/upgrade.md` with the stub below, then run the Test command:
```
---
description: Removed - use /crew:migrate, which upgrades a pre-0.20 config itself
allowed-tools: Read
---

`/crew:upgrade` was removed. It is not an alias and does nothing.
`/crew:migrate` now brings a pre-0.20 `.crew/config.json` (no `schema`, or 1-6)
up to the current schema and migrates it in the same run, with one backup and
one rollback. Graph facts for the code map come from `/crew:onboard --refresh
<subsystem>`. Tell the user that, and stop.
```
- [ ] Retarget the `sabotage.py:807-812` entry: `UPGRADE_DOC` (`:126`) becomes `os.path.join(CREW, "skills", "crew-setup", "upgrade-report.md")`, the label becomes "the current migration loses its entry in upgrade-report.md", and the test id is the renamed test. The line count stays at 3378.
- [ ] Remove the `plugin/crew/commands/upgrade.md` entry from `.budget-allowance.json` (`:30-33`).
- [ ] Run `scripts/_test/instruction-budgets.py` and read the measured Windows count. Re-pin `:271-275`, `:287`, `:291` and `:502-504` from 19 to that number (expected 18, which is 8 allowance plus 10 stale-name). The reason goes in the docstring: T-0038 retired upgrade.md's allowance.
- [ ] Update `BUDGETS.md`:
  - `:19-24`: 9 becomes 8 command files. Replace the savings figure with the sum over the remaining allowance entries of (lines - 120), computed with a one-line python over the JSON.
  - `:11`: re-measure the `crew-markdown-lines` claim with `git ls-files 'plugin/crew/*.md' | xargs cat | wc -l` and the file count, after the new file is `git add`ed. Do this again in Step 13 after the last doc edit.
- [ ] Run the Test command.

### Step 8: migrate.md documents the upgrade stage
Files: plugin/crew/commands/migrate.md
Test: python3 -m pytest plugin/crew/tests/test_rules_generation_path.py -q -p no:cacheprovider && python3 scripts/check_instructions.py
Risk: low. The budget is 120 lines, and migrate.md is 111 today.
- [ ] Add these to Step 1's list (`migrate.md:18-26`):
  - `every upgrade line - a pre-0.20 config (no schema, or 1-6) is brought to the current schema in the same apply; read ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/upgrade-report.md and relay each line as it says`;
  - an unmigrated-block CONFLICT is fixed by hand.
- [ ] Change apply item 3 (`:55-56`) to "Never deletes, and overwrites exactly one file: a pre-0.20 `.crew/config.json`, whose original is in the backup and which rollback restores byte-identical."
- [ ] Add a table row (`:58-65`): `.crew/config.json` (no schema, or 1-6), upgraded in place, then as above.
- [ ] Add one sentence under Rollback (`:101-104`): an autoClear conversion edits `config.json` after apply, so rollback then refuses that file by name, the same as it does for `crew.json`.
- [ ] Trim wording elsewhere if needed. `wc -l` must be 120 or less.
- [ ] Run the Test command.

### Step 9: every live doc stops presenting /crew:upgrade as a command
Files: plugin/crew/README.md, plugin/crew/CONFIG.md, plugin/PLUGINS.md, plugin/crew/commands/onboard.md, plugin/crew/skills/crew-graph/SKILL.md, plugin/crew/skills/crew-graph/reconcile.md, plugin/crew/skills/crew-providers/SKILL.md, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/skills/crew-setup/global-config.md, INSTALLATION.md, TODO.md
Test: python3 scripts/check_instructions.py && python3 scripts/check-marketplace.py && git grep -n "crew:upgrade" -- plugin/crew/README.md plugin/crew/CONFIG.md plugin/PLUGINS.md plugin/crew/commands plugin/crew/skills INSTALLATION.md docs/guides/crew/src
Risk: low. The PLUGINS.md row must match the stub's frontmatter description exactly.
- [ ] Update `README.md`:
  - `:864`: "the same policy `crew_upgrade.upgrade_config` (run by `/crew:migrate` for a pre-0.20 config) uses".
  - `:898`: "`/crew:upgrade` now runs `--check-global`" becomes "`/crew:config` runs `--check-global`".
  - `:1203`: "The migrate report's upgrade lines say so out loud".
  - Row `:2372`: `| /crew:upgrade | Removed - /crew:migrate upgrades a pre-0.20 config itself |`.
  - Row `:2376`: append "; a pre-0.20 config (no schema, or 1-6) is upgraded to the current schema first, in the same backup and rollback".
- [ ] Update `CONFIG.md` §4 (`:236-253`): add one paragraph. A config below `SCHEMA_CURRENT` or with no `schema` is brought forward by `/crew:migrate`'s upgrade stage (`crew_upgrade.upgrade_config`), which rewrites `.crew/config.json` in place, backed up and restored by `--rollback`. A present non-integer, or 0 or less, is refused.
- [ ] Update `PLUGINS.md`:
  - `:72`: "and `/crew:onboard --refresh` uses it to fold graph facts into the code map".
  - `:80`: "`crew_upgrade.py` never sets that flag".
  - `:158`: the row becomes the stub's exact description.
  - `:208`: "the reconcile shape `/crew:onboard --refresh` reads".
- [ ] Update `onboard.md`:
  - `:210`: "the same `crew_upgrade.py` path `/crew:migrate` uses for config".
  - `:233`: "If an earlier upgrade run left contradictions there".
  - `:249`: "exactly as the upgrade report does".
  - Line count must not grow. It is 255 against allowance 255 (`.budget-allowance.json`).
- [ ] Update the skills:
  - `crew-graph/SKILL.md:177` and `reconcile.md:3`, `:89`: `/crew:onboard --refresh` is the one caller of the reconcile.
  - `crew-providers/SKILL.md:42` and `crew-setup/SKILL.md:258`: `/crew:migrate` (upgrade stage) in place of `/crew:upgrade`.
  - `crew-setup/global-config.md:69`: "the findings `/crew:migrate`'s upgrade stage and `/crew:config` report".
- [ ] `INSTALLATION.md:303`: "`/crew:onboard --refresh` reads it to fold graph facts into the code map".
- [ ] `TODO.md`: at `:2008`, `:2268`, `:2278`, `:2656`, `:3850-3856` and `:4110`, append " - moot since T-0038: upgrade.md is a removal stub" to each entry that cites `commands/upgrade.md` line numbers. Nothing else in TODO.md changes.
- [ ] Run the Test command. The grep may list only the stub (`commands/upgrade.md`), lines saying it was removed, and `crew_upgrade`'s historical "may be pinned by an earlier /crew:upgrade" if a doc quotes it.

### Step 10: the quickstart guide and its rebuilt outputs
Files: docs/guides/crew/src/quickstart.md, docs/guides/crew/crew-1.0-quickstart.html, docs/guides/crew/crew-1.0-quickstart.docx, docs/guides/crew/crew-1.0-quickstart.pdf
Test: python3 docs/guides/crew/src/build.py --guide quickstart && git diff --stat -- docs/guides/crew/
Risk: low. If `soffice` is absent, stop as needs-owner (spec Unknowns).
- [ ] `quickstart.md:22`: "Existing 0.20 or older repos: `/crew:migrate`". At `:88`, "If the repository already used crew 0.20 or earlier (an older config is upgraded in the same run), or you just ran `/crew:init`:".
- [ ] Run `command -v soffice`, then the Test command. Only the three quickstart outputs may change.

### Step 11: diagram, codemap and generated rules
Files: docs/diagrams/data-flow-crew-config.mmd, .crew/codemap/crew.md, .claude/rules/**
Test: python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check && python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0038
Risk: low.
- [ ] Change the MIGRATE node text in `data-flow-crew-config.mmd:270` to "crew_migrate.py --apply<br/>the ONLY writer of .crew/crew.json<br/>(schema 1). Rewrites config.json only<br/>for a pre-0.20 config (upgrade stage),<br/>backed up and restored by --rollback". Validate it with `mmdc`, or with the Mermaid MCP if `mmdc` is absent. No rendered output is tracked for this diagram.
- [ ] `.crew/codemap/crew.md:725-727`: `crew_migrate.py` reads `.crew/config.json`, rewrites it in place only for a pre-0.20 config (upgrade stage, `crew_migrate.py` `_load_legacy`/`build_plan`), and writes `.crew/crew.json`, with `--rollback` restoring config.json byte-identical. Mark it DERIVED with repo-relative anchors. Leave the `anchor:` alone unless the whole note is re-verified.
- [ ] Run `crew_instructions.py rules --root .` if `--check` reports drift. Then run the Test command and resolve every stale artifact it names.

### Step 12: a verify rule for migrate
Files: .crew/verify.json
Test: python3 -c "import json;json.load(open('.crew/verify.json'))" && python3 scripts/check-marketplace.py
Risk: low.
- [ ] Time `python3 -m pytest plugin/crew/tests/test_migrate.py -q -p no:cacheprovider` with `/usr/bin/time -v` under the heavy lock.
- [ ] After the `crew_upgrade.py` rule (`:171-177`), add `{"paths": ["plugin/crew/hooks/scripts/crew_migrate.py", "plugin/crew/tests/test_migrate.py", "plugin/crew/tests/sabotage_migrate.py", "plugin/crew/commands/migrate.md"], "seconds": <measured, rounded up>, "run": ["python3 -m pytest plugin/crew/tests/test_migrate.py -q"], "reach": "local", "why": "<measured>s on <host>, <date>. The one-time 0.20 and pre-0.20 migration, including the in-place config.json upgrade and its byte-identical rollback. reach: local - fixtures under tmp_path."}`.
- [ ] Run the Test command.

### Step 13: version, changelog and gates
Files: plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, CHANGELOG.md, plugin/crew/BUDGETS.md, graphify-out/**
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0038 python3 -m pytest plugin/crew/tests/ -q -p no:cacheprovider && python3 scripts/check-marketplace.py && python3 scripts/check_instructions.py && python3 scripts/_test/instruction-budgets.py
Risk: med. A content change with no version bump never reaches installed machines (CLAUDE.md "Stop and ask").
- [ ] Read `git show origin/main:plugin/crew/.claude-plugin/plugin.json` and bump crew one patch in `plugin.json:3`, `marketplace.json:218` and `PLUGINS.md:14`.
- [ ] Add a CHANGELOG `[Unreleased]` entry: `crew` <version>: `/crew:upgrade` folded into `/crew:migrate`. It must say:
  - what migrate now does for a pre-0.20 config;
  - that `config.json` is the one file migrate overwrites, and rollback restores it;
  - that the codemap half moved to `/crew:onboard --refresh`;
  - that the stub stays for now.
- [ ] Re-measure the `BUDGETS.md` `crew-markdown-lines` claim after every doc edit.
- [ ] Run the Test command under the heavy lock. Quote any failure verbatim.
- [ ] Commit. Let the post-commit hook rebuild `graphify-out/` (wait for `~/.cache/graphify-rebuild.log` to stop growing). Check that `graph.json`'s `nodes`/`links` and `GRAPH_REPORT.md`'s `## Summary` agree before a follow-up commit.
- [ ] Say which suites did not run: `scripts/_test/drift-detection.sh`, and Windows behaviour of the `config.json` bytes.
- [ ] The PR body names the docs touched. No "Docs: none".
