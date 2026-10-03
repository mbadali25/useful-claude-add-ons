# T-0065 plan            spec: .work/tickets/T-0065/spec.md

Work happens in a fresh worktree, `/repos/personal/uca-t-0065`, on branch `T-0065-build` off origin/main. Anchors are origin/main `502cb137` (crew 1.0.42).

Before each step, re-grep every quoted string. T-0064 and T-0070 edit `crew_status.py`, T-0050 edits `crew_upgrade.py`, and T-0038 edits `commands/upgrade.md`. If one of them lands first, re-anchor from the new line and keep the test unchanged.

Every step follows the same order:
1. Write the must-refuse test and its must-allow neighbour.
2. Watch both fail for the stated reason.
3. Implement.
4. Add the sabotage mutations that must go red.

Heavy runs (pytest, `sabotage.py`, `run-tests.sh`, verify-gate) are serial under `flock /root/crew-tmp/heavy.lock`, with `TMPDIR=/root/crew-tmp/t-0065`. Check `free -g` first.

No second opinion is needed. There are four independent fixes, each a small read or write path with a direct test. Steps 1-2 (item 3), 3 (item 10), 4 (item 8) and 5-6 (item 7) are independent of each other. Step 7 runs last.

### Step 1: `verify_agents.py` - which verify.json agents are not installed here
Files: plugin/crew/hooks/scripts/verify_agents.py, plugin/crew/tests/test_verify_agents.py, plugin/crew/tests/sabotage_review.py, .crew/verify.json
Test: python3 -m pytest plugin/crew/tests/test_verify_agents.py -q -p no:cacheprovider
Risk: med. A false "installed" is the defect. It reproduces the silent under-review that `/crew:review` warns about (`plugin/crew/commands/review.md:78-86`). The unknown-never-installed test bounds it.
- [ ] Tests first, in `plugin/crew/tests/test_verify_agents.py`.
  - Setup: every fixture sets `HOME` and `CLAUDE_CONFIG_DIR` to a `tmp_path` directory with `monkeypatch`, so no test reads the real `~/.claude`.
  - Setup: the helper `_home(tmp_path, user_agents=(), plugins={}, enabled={}, project_settings=None)` writes `agents/<name>.md` with frontmatter `name: <name>`. It writes `plugins/installed_plugins.json` as `{"version": 2, "plugins": {"<p>@<mkt>": [{"installPath": ...}]}}`, with an `agents/<a>.md` under each installPath. It writes `settings.json` with `enabledPlugins`.
  - Setup: every write uses `newline="\n"`.
  - `test_missing_agent_is_named`: a verify.json rule `{"paths": ["**/*.php"], "agents": ["php-developer"]}`. `main(["--root", root, "--check"])` returns 1, and stdout names `php-developer` and `**/*.php`.
  - `test_installed_agents_resolve`, parametrised over:
    - `security` (crew role, via `crew_state.ROLE_TIERS`)
    - `crew:reviewer`
    - a user agent `sql-pro`
    - a project agent `.claude/agents/dba.md` whose frontmatter says `name: dba`
    - `voltagent:security-auditor` from an enabled plugin `voltagent@mkt`
    - bare `security-auditor` resolving to that plugin agent
    
    Each returns 0.
  - `test_frontmatter_name_wins_over_file_stem`: a file `x.md` with `name: y` resolves `y` and not `x`.
  - `test_disabled_or_unregistered_plugin_agent_is_missing`, parametrised:
    - `enabledPlugins: {"voltagent@mkt": false}` in the project `.claude/settings.local.json`, with `true` at user scope, makes it missing (narrowest scope wins, as in `crew_endpoints.gizmoduck_installed`, `plugin/crew/hooks/scripts/crew_endpoints.py:822`)
    - `other:thing`, whose plugin is not in the registry, is missing
  - `test_unknowns_never_read_as_installed`, parametrised over:
    - an unparseable `installed_plugins.json`, for a name that only a plugin could supply
    - an unparseable user `settings.json`, for the same name
    - an unparseable `.crew/verify.json`
    
    Each returns 2, and the reason is on stdout.
  - `test_crew_roles_resolve_even_when_registry_unreadable`: a crew role still resolves (returns 0) when the registry is unreadable. The unknown touches only names it could have supplied.
  - `test_no_agents_named_is_ok`: a verify.json with no `agents` key returns 0 and says `no agents named`.
  - `test_check_is_read_only`: an mtime snapshot of the fixture and the fake home, taken around `--check`, is unchanged.
  - Run them and watch them fail with ModuleNotFoundError.
- [ ] Implement `plugin/crew/hooks/scripts/verify_agents.py`. It is stdlib only, with `sys.dont_write_bytecode = True`.
  - `named(root)` returns `({name: [rule paths...]}, problem)` from `.crew/verify.json` `rules[*].agents`.
  - `installed(root)` returns `(names, unknown_reasons)`, where `names` is the set of resolvable spellings. It collects:
    - crew roles, both bare and as `crew:<role>`, from `crew_state.ROLE_TIERS`
    - the files in the plugin's own `agents/` directory, found from `__file__`
    - `<config>/agents/*.md` and `<root>/.claude/agents/*.md`, bare
    - for each enabled plugin in `<config>/plugins/installed_plugins.json`, `<plugin>:<name>` plus bare `<name>` from its installPath's `agents/*.md`
  - `<config>` is `CLAUDE_CONFIG_DIR`, or `~/.claude` when that is unset. The enabled scope order and the treatment of a malformed scope follow `gizmoduck_installed`'s docstring (`crew_endpoints.py:822`). That logic is re-implemented generically for any plugin key, because `gizmoduck_installed` is gizmoduck-specific.
  - `check(root)` returns `{"status": "ok"|"missing"|"unknown", "missing": {...}, "unknown": [...], "notChecked": ["managed-policy agents", "--agents"]}`. A name is `missing` only when every source it could come from was read cleanly. Otherwise it is `unknown`.
  - CLI: `--root`, `--check` (exit 0, 1 or 2), `--json`.
- [ ] Add a `.crew/verify.json` rule covering `plugin/crew/hooks/scripts/verify_agents.py` and `plugin/crew/tests/test_verify_agents.py`. Its command is `python3 -m pytest plugin/crew/tests/test_verify_agents.py plugin/crew/tests/test_status.py -q`.
- [ ] Add these sabotage mutations to `REVIEW_FIX_MUTATIONS`:
  - "an unreadable registry reads as installed" returns `ok` where an unknown is set. It goes red on `tests/test_verify_agents.py::test_unknowns_never_read_as_installed`.
  - "enabledPlugins ignored" counts every registered plugin. It goes red on `test_disabled_or_unregistered_plugin_agent_is_missing`.
  - "file stem instead of frontmatter name" goes red on `test_frontmatter_name_wins_over_file_stem`.
- [ ] Run the Test command. Everything must be green.

### Step 2: `/crew:status` shows the agents line
Files: plugin/crew/hooks/scripts/crew_status.py, plugin/crew/tests/test_status.py, plugin/crew/tests/sabotage_review.py
Test: python3 -m pytest plugin/crew/tests/test_status.py -q -p no:cacheprovider
Risk: low. This is one line in a 40-line budget, and read-only behaviour is already pinned (`plugin/crew/tests/test_status.py:57`, `:154`).
- [ ] Write the tests first:
  - `test_status_flags_uncovered_verify_agent`: the fixture's verify.json names `php-developer`, and the fake home has no agents. The output has one line starting `agents   MISSING php-developer`.
  - `test_status_agents_ok_and_unknown`, parametrised: a crew role gives `agents   ok (1 named)`, and an unparseable registry with a plugin-only name gives `agents   unknown - <reason>`.
  - `test_status_is_read_only`, `test_status_never_runs_a_configured_fsmonitor_hook` and `test_status_output_fits_forty_lines_on_a_busy_repo` stay unchanged and green.
- [ ] Implement `_agents_line(root)` in `crew_status.py`, beside `_verify_line` (`plugin/crew/hooks/scripts/crew_status.py:128`). It calls `verify_agents.check(root)` and shows at most three names, then `(+N more)`. In `collect` (`:197`), append it after the verify line. Add it to the module docstring.
- [ ] Add the sabotage mutation "status hides a missing agent", which always returns `ok`. It goes red on `tests/test_status.py::test_status_flags_uncovered_verify_agent`.
- [ ] Run the Test command. Everything must be green.

### Step 3: `provider_probe.py` - one real call, from the repo root
Files: plugin/crew/hooks/scripts/provider_probe.py, plugin/crew/tests/test_provider_probe.py, plugin/crew/tests/sabotage_review.py, .crew/verify.json
Test: python3 -m pytest plugin/crew/tests/test_provider_probe.py plugin/crew/tests/test_review_run_launch.py -q -p no:cacheprovider
Risk: low. The probe is a new entry point that reuses `review_run.command_for` and `launch` (`plugin/crew/hooks/scripts/review_run.py:127`, `:140`), so the probe and a real review run the same command line.
- [ ] Write the tests first, using a stub `codex` written with `crew_fixtures.write_shim` into `tmp_path/fakebin` and put first on PATH:
  - The stub checks its own argv and `os.getcwd()`. If `--skip-git-repo-check` is missing, if `-C` is not followed by `<root>`, or if the cwd is not `<root>`, it prints `Not inside a trusted directory and --skip-git-repo-check was not specified.` to stderr and exits 1.
  - Otherwise it prints two JSONL events, `{"type":"item.completed","item":{"type":"agent_message","text":"OK"}}` and `{"type":"turn.completed"}` (the shapes `review_verdict.codex_final_message` reads, `plugin/crew/hooks/scripts/review_verdict.py:127-160`), and exits 0.
  - `test_codex_probe_runs_from_the_repo_root`: run `provider_probe.py codex --root <repo>` as a subprocess with `cwd=<an unrelated tmp dir>`. It exits 0 and prints `codex: ok`.
  - `test_codex_probe_reports_a_failed_call`: the stub always fails. The probe exits 1 and prints `codex: FAILED - Not inside a trusted directory ...`.
  - `test_codex_probe_reports_an_incomplete_stream`: the stub exits 0 with no `turn.completed`. The probe exits 1 with `the Codex event stream has no completed turn`, so exit 0 is never read as a pass.
  - `test_probe_not_installed`: with codex absent from PATH, the probe exits 2 and prints `codex: not installed`.
  - `test_copilot_probe_needs_a_model`: `provider_probe.py copilot` with no `--model` exits 2 and says the model is required (the same rule as `review_run.run`, `:365-368`).
  - `test_review_command_keeps_the_trust_flags`: `review_run.command_for("codex", "codex", "/r", "p", "", "")` contains `--skip-git-repo-check` and `["-C", "/r"]`.
- [ ] Implement `plugin/crew/hooks/scripts/provider_probe.py`:
  - CLI: `<provider> --root . [--model M] [--effort E] [--timeout 120]`. `root` is taken absolute.
  - It builds the command with `review_run.command_for(provider, shutil.which(provider), root, "Reply with the single word OK.", model, effort)` and runs it with `review_run.launch(cmd, root, timeout)`.
  - codex: the message and error come from `review_verdict.codex_final_message`. copilot: the output is stdout.
  - Exit 0 prints `<provider>: ok (<model or default>)`. Exit 1 prints `<provider>: FAILED - <error or first stderr line or 'timed out'>`. Exit 2 means not installed, or a usage error.
  - It never touches the review ledger.
- [ ] Add a `.crew/verify.json` rule covering `provider_probe.py` and its test, with the Test command above.
- [ ] Add these sabotage mutations:
  - "the probe drops --skip-git-repo-check" edits `command_for`. It goes red on `tests/test_provider_probe.py::test_codex_probe_runs_from_the_repo_root` and on `test_review_command_keeps_the_trust_flags`.
  - "the probe launches from the caller's cwd" passes `os.getcwd()` as the launch root. It goes red on `test_codex_probe_runs_from_the_repo_root`.
  - "an incomplete stream is ok" ignores the error. It goes red on `test_codex_probe_reports_an_incomplete_stream`.
- [ ] Run the Test command. Everything must be green.

### Step 4: `UPGRADE.md` keeps its history
Files: plugin/crew/skills/crew-graph/scripts/crew_upgrade.py, plugin/crew/tests/test_upgrade.py, plugin/crew/tests/sabotage_migrate.py
Test: python3 -m pytest plugin/crew/tests/test_upgrade.py plugin/crew/tests/test_sabotage_harness.py -q -p no:cacheprovider
Risk: med. `_carried_conflicts` must still read the newest run's section, or answered contradictions come back as new ones.
- [ ] Write the tests first, reusing `test_upgrade.py`'s existing crew-repo fixture:
  - `test_force_keeps_earlier_upgrade_reports`: seed `.crew/codemap/UPGRADE.md` with `# Upgrade report\n...\n## Contradictions\n- old-conflict (verified: false alarm)\n` plus a hand note, `NOTE-T0065`. Run `crew_upgrade.run(root, derived, force=True)` twice.
    - After run 1, the file starts with the new report, then contains `MARKER` (the exact marker line from the spec's Unknowns), then the seeded bytes unchanged.
    - After run 2, the file starts with the newest report, then `MARKER`, then run 1's full file bytes. Nesting, not duplication: exactly one `MARKER` per earlier run.
    - `NOTE-T0065` is present after both runs.
  - `test_carried_conflicts_reads_the_newest_run`: an annotated contradiction in the newest run is carried. One that appears only in an older run below the marker is not re-listed as new.
  - `test_upgrade_report_write_is_atomic`: monkeypatch `_report` to raise. `run(..., force=True)` raises, and `UPGRADE.md` is byte-identical to before. After a normal run, `b"\r" not in data`, and no `UPGRADE.md.*.tmp` sibling remains.
  - `test_first_upgrade_has_no_marker`: with no prior `UPGRADE.md`, the file is the report alone, with no marker.
  - The existing `test_upgrade.py` cases stay green.
- [ ] Implement it in `run` (`plugin/crew/skills/crew-graph/scripts/crew_upgrade.py:1389-1393`):
  - Read the old bytes first.
  - Build `new = report + ("\n" + MARKER + "\n\n" + old if old else "")` fully in memory.
  - Write `UPGRADE.md.<pid>.tmp` with `newline="\n"`, then call `os.replace`. This is the same shape as the config write at `:1341-1346`.
  - `_carried_conflicts` (`:1153-1200`) stops reading at `MARKER`. Add a comment there.
  - `MARKER` becomes a module constant.
- [ ] Add these mutations to `MIGRATE_FIX_MUTATIONS`:
  - "UPGRADE.md overwritten again" writes the report alone. It goes red on `tests/test_upgrade.py::test_force_keeps_earlier_upgrade_reports`.
  - "carried conflicts read past the marker" goes red on `test_carried_conflicts_reads_the_newest_run`.
  - "report written in place" opens `UPGRADE.md` with `"w"` before the report is built. It goes red on `test_upgrade_report_write_is_atomic`.
- [ ] Run the Test command. Everything must be green.

### Step 5: every test gets its own TMPDIR
Files: plugin/crew/tests/conftest.py, plugin/crew/tests/crew_fixtures.py, plugin/crew/tests/test_tmp_hygiene.py, plugin/crew/tests/sabotage_autocycle.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0065 python3 -m pytest plugin/crew/tests/ -q -p no:cacheprovider
Risk: med. Every test inherits the new `TMPDIR`. A test that hardcodes `/tmp`, or a Unix socket path that grows past its length limit, breaks here. The full-suite run is the check.
- [ ] Write the tests first:
  - `test_every_test_gets_its_own_tmpdir`: `os.environ["TMPDIR"]`, `["TEMP"]`, `["TMP"]` and `tempfile.gettempdir()` all resolve under `tmp_path`.
  - `test_subprocess_env_inherits_the_isolated_tmpdir`: `crew_fixtures.shim_env("sh", bindir)` carries `TMPDIR` (`plugin/crew/tests/crew_fixtures.py:952-956`, which today builds `{"PATH": ...}` alone).
- [ ] Reproduce the sender leak on origin/main first, to resolve the spec's Unknown. Run `python3 -m pytest plugin/crew/tests/test_auto_cycle.py -q` under a fresh `TMPDIR`, then count `tmp.*` files that contain `tmux send-keys -t %7` after the run and again after 15 s. Record the count and the kill path that caused it (pytest teardown, `gate_processes`, or timeout) in the step's commit message.
- [ ] Implement:
  - In `conftest.py`, add an autouse fixture `_isolated_tmpdir(tmp_path, monkeypatch)`. It creates `tmp_path / "tmp"`, sets `TMPDIR`, `TEMP` and `TMP` with `monkeypatch.setenv`, and runs `monkeypatch.setattr(tempfile, "tempdir", str(d))`.
  - In `crew_fixtures.shim_env`, copy `TMPDIR`, `TEMP` and `TMP` from `os.environ` when they are set.
- [ ] Add the sabotage mutation "the conftest TMPDIR fixture is not autouse". It goes red on `tests/test_tmp_hygiene.py::test_every_test_gets_its_own_tmpdir`.
- [ ] Run the Test command, the full suite. Everything must be green, with the same pass count as origin/main plus the new tests. Count real-`/tmp` entries before and after the run: `/tmp` must gain no `crew-completion-audit.*` and no `tmp.*` entry with a newer mtime than the run's start. Other sessions write `/tmp` too, so this compares only names that match crew's patterns.

### Step 6: the hooks and the shell suite clean up after themselves
Files: plugin/crew/hooks/scripts/auto-clear.sh, plugin/crew/hooks/scripts/verify-gate.sh, plugin/crew/hooks/scripts/_test/run-tests.sh, plugin/crew/tests/test_tmp_hygiene.py, plugin/crew/tests/sabotage_autocycle.py, .crew/verify.json
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0065 python3 -m pytest plugin/crew/tests/test_tmp_hygiene.py plugin/crew/tests/test_auto_clear.py plugin/crew/tests/test_auto_cycle.py plugin/crew/tests/test_verify_gate_rule_out_tail_read.py plugin/crew/tests/test_verify_gate_python3_shim.py plugin/crew/tests/test_verify_gate_lock_sh.py -q -p no:cacheprovider
Risk: med.
- The auto-clear sender must still type `/clear`. Unlinking the script it is running is safe on POSIX. On Git Bash, `rm` of an open file can fail, which is why the last-line `rm` stays.
- A verify-gate cleanup that runs twice, or out of order, must not remove the lock early. The registry runs in reverse registration order (`plugin/crew/hooks/scripts/verify-gate.sh:617-623`).
- [ ] Write the tests first, in `test_tmp_hygiene.py`. Each gives the hook a fresh `TMPDIR`, `tmp_path/t`.
  - `test_auto_clear_sender_leaves_nothing_after_sending`:
    - Setup: a stub `tmux` that appends its argv to a file, and a machine config with `delaySeconds: 1`. Build it with `test_auto_cycle.py`'s `_sendable` and `_machine` helpers, imported, or copied into `crew_fixtures` if importing them couples the files.
    - Run `auto-clear.sh` and wait up to 10 s for the stub's log to show `/clear`.
    - Assert that `t/` is empty.
  - `test_auto_clear_sender_leaves_nothing_when_killed`:
    - Setup: the same, with delay 5.
    - Once the sender process (found with `pgrep -f` on the `t/` path) is sleeping, send SIGKILL to its process group.
    - Assert that `t/` is empty within 2 s.
    - Watch it fail on origin/main: the file remains.
  - `test_verify_gate_clean_run_leaves_tmpdir_empty`: a fixture repo whose verify.json has one rule running `true`. Run `verify-gate.sh` with a Stop payload, and `t/` is empty afterwards.
  - `test_verify_gate_temp_files_removed_on_term`, parametrised:
    - `rule`: the rule is `sleep 30`. Wait until `t/` holds a file, then send SIGTERM to the gate.
    - `matcher`: a `python3` shim, first on PATH, runs `sleep 5` before `exec`-ing the real interpreter whenever its first argument is `-`. Send SIGTERM during that sleep.
    
    In both cases `t/` is empty after the gate exits. Reuse `crew_fixtures.popen_gate` and `kill_process_group` (`plugin/crew/tests/crew_fixtures.py:303`, `:384`) for spawning and killing.
  - `test_run_tests_sh_leaves_tmpdir_empty`: run `bash plugin/crew/hooks/scripts/_test/run-tests.sh` with `TMPDIR=tmp_path/t` and a 1200 s timeout. Its exit code and its `passed`/`failed` summary line equal origin/main's, which is recorded in the commit message. Afterwards `t/` is empty.
- [ ] Implement:
  - In `auto-clear.sh` (`:188-212`), write `printf 'rm -f -- %q\n' "$send_script"` as the sender's second line too, right after the shebang, before `sleep`. Keep the last-line `rm` as the fallback. Add a comment saying why both exist.
  - In `verify-gate.sh`, change `:744-746`: replace the "deliberately no trap" comment, and after `CHANGED_FILE=$(mktemp ...)` define `_crew_gate_cleanup_changed() { rm -f "$CHANGED_FILE" 2>/dev/null; }` and register it. Do the same for `RULE_OUT_FILE` after `:1603`, registering `_crew_gate_cleanup_rule_out()`, which removes the current value. The existing straight-line `rm`s stay, and a second `rm -f` is harmless.
  - In `run-tests.sh`:
    - Keep one list, `_CREW_TEST_TMP=()`.
    - Set one `trap 'rm -rf "${_CREW_TEST_TMP[@]}"' EXIT`, installed before `:116`.
    - Change each `X=$(mktemp -d)` (`:116`, `:204`, `:238`, `:281`, `:340`, `:379`, `:461`, `:716`, `:830`, `:956`) to append to the list.
    - Remove the `trap` lines at `:117` and `:462`, because the one trap covers them.
- [ ] Add these sabotage mutations to `AUTOCYCLE_MUTATIONS`:
  - "the sender no longer unlinks itself first" goes red on `tests/test_tmp_hygiene.py::test_auto_clear_sender_leaves_nothing_when_killed`.
  - "RULE_OUT_FILE not registered" goes red on `test_verify_gate_temp_files_removed_on_term[rule]`.
  - "CHANGED_FILE not registered" goes red on `test_verify_gate_temp_files_removed_on_term[matcher]`.
  - "run-tests.sh trap overwritten again" re-adds `trap 'rm -rf "$D" "$PD"' EXIT`. It goes red on `test_run_tests_sh_leaves_tmpdir_empty`.
- [ ] Add a `.crew/verify.json` rule. Paths: `plugin/crew/hooks/scripts/auto-clear.sh`, `plugin/crew/hooks/scripts/_test/run-tests.sh`, `plugin/crew/tests/test_tmp_hygiene.py`. Command: `python3 -m pytest plugin/crew/tests/test_tmp_hygiene.py -q`. The existing verify-gate rule already covers `verify-gate.sh`. Add `test_tmp_hygiene.py` to that rule's pytest list.
- [ ] Run the Test command. Everything must be green. Then run `python3 plugin/crew/tests/sabotage.py` under the lock. Every new mutation goes red, and every existing one stays red.

### Step 7: docs, verify map, version
Files: plugin/crew/commands/status.md, plugin/crew/commands/verify.md, plugin/crew/commands/review.md, plugin/crew/commands/model.md, plugin/crew/commands/onboard.md, plugin/crew/commands/upgrade.md, plugin/crew/skills/crew-verification/SKILL.md, plugin/crew/skills/crew-providers/SKILL.md, plugin/crew/skills/crew-setup/scripts/providers.sh, plugin/crew/README.md, plugin/PLUGINS.md, docs/guides/crew/src/working-with-codex.md, docs/guides/crew/src/troubleshooting.md, docs/guides/crew/**, .crew/codemap/crew.md, docs/diagrams/**, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json
Test: (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py) && python3 scripts/check-marketplace.py
Risk: low. The docs must say what the code does, and nothing more.
- [ ] `status.md:24-37`: add an `agents` row. Source: `verify_agents.py`. It says "unknown" when a registry or settings file will not parse.
- [ ] `verify.md` step 8 (`:32`): the report also runs `verify_agents.py --check` and lists every agent a rule names that is not installed here.
- [ ] `review.md:78-86`: step 3 lists the missing agents from `verify_agents.py --check`, instead of resolving them by hand. The resolution rule text (`:70-75`) stays. In step 1 (`:233-241`), `provider_probe.py` is named as the optional real-call check, and the eligibility table is unchanged.
- [ ] `crew-verification/SKILL.md:145-153`: name the checker, and say that `/crew:status` shows it.
- [ ] `model.md:99-103`, the providers skill (`:131-135`) and `providers.sh:8`: replace the hand-typed `codex exec ... "reply OK"` with `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/provider_probe.py codex --root .`. Say why: it runs from the repo root with review's own flags.
- [ ] `onboard.md:227-237` and `upgrade.md:157-167`: `UPGRADE.md` keeps earlier runs below the marker, newest first. `--force` no longer erases an unverified contradictions list. Keep the line saying the `schema <from> -> <current>` header reads as a migration on a current repo.
- [ ] README: add `verify_agents.py` and `provider_probe.py` rows to the script table. Add a sentence at `:1251` on the probe. PLUGINS.md: update the crew row. Guides: `working-with-codex.md:53-58` gets the probe, and `troubleshooting.md` gets "an agent in verify.json is not installed" and "the temp directory fills with crew files". The latter names the patterns and the owner-run cleanup command, and says crew itself never runs that cleanup. Rebuild the guides with `docs/guides/crew/src/build.py`, and check the rebuilt HTML, DOCX and PDF exist and are newer than their sources.
- [ ] `.crew/codemap/crew.md`: update the status, review, upgrade and verify-gate sections, with DERIVED anchors to the new lines and `anchor:` set to the commit. `docs/diagrams/**`: grep for `crew_status`, `UPGRADE` and `auto-clear` nodes. If none names a changed behaviour, the PR body says `Diagrams: none - no node describes these behaviours`.
- [ ] Bump the crew version in `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, and add a CHANGELOG entry covering the four items and the leftover counts.
- [ ] The report names the owner action (clean the listed `/tmp` patterns by hand), the TSS follow-up (item 7's guard frictions), and the gizmoduck follow-up.
- [ ] Run the Test command. Both must be green. Then run the full suite once more under the lock.
