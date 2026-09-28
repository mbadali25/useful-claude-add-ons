# T-0040 plan            spec: .work/tickets/T-0040/spec.md

Work happens in the worktree `/repos/personal/uca-t-0040` on branch `T-0040-build`, which Implement creates from origin/main. Anchors are origin/main `bebbb97f` (crew 1.0.46). Re-grep each quoted anchor before its step, because T-0070 and T-0075 edit `crew_config.py` and may land first. If a line is gone or its meaning changed, stop and re-read. Never re-anchor by guess.

Every step writes its tests first and runs them red, then implements. Heavy runs go through `/root/crew-tmp/heavy-run <command>` with `TMPDIR=/root/crew-tmp/t-0040`, one at a time, after checking `free -g`. That covers pytest over more than one file, `sabotage.py`, `build.py` and graphify. No test calls a real `wsl.exe`. Every probe and run goes through an injected `runner`, and the cache path is monkeypatched to `tmp_path`. The real `~/.claude/crew/` is never read or written by a test.

### Step 1: `wslRouting` block on both config layers
Files: plugin/crew/hooks/scripts/crew_config.py, plugin/crew/templates/config.template.json, plugin/crew/templates/global.template.json, plugin/crew/tests/test_crew_config.py
Test: python3 -m pytest plugin/crew/tests/test_crew_config.py -q -p no:cacheprovider
Risk: low. A block missing from one layer fails `test_every_global_key_is_a_real_repo_config_key` (`plugin/crew/tests/test_crew_config.py:102-110`). A template that drifts fails `:55-72`.
- [ ] Tests first. Add `test_wsl_routing_is_on_both_layers`: `default_config()["wslRouting"] == {"mode": "auto", "distro": None}`, and the same for `default_global_config()`. Run it red.
- [ ] Add `"wslRouting": {"mode": "auto", "distro": None}` to `default_config()`, after the `platform` block (`plugin/crew/hooks/scripts/crew_config.py:322-327`), with a comment. The comment says that `platform.*` is derived and rewritten by platform-sync (`crew_platform.py:72-75`), so the routing preference lives here instead.
- [ ] Add the same block to `default_global_config()`, after `route` (`:563`), with a comment. The comment says whether WSL is worth using is a fact about the machine, and a repo may still override it.
- [ ] Regenerate both templates as `json.dumps(..., indent=2) + "\n"`, written with `newline="\n"`. Rerun the Test command green, including the two template tests and `test_the_global_template_is_not_a_copy_of_the_repo_one` (`:76-90`, where `platform` stays repo-only).
- [ ] If origin/main by now carries T-0075's `enum_values` in `crew_config.py`, register `wslRouting.mode` with `("auto", "wsl", "native")` there, and add that value to its parametrised refusal test. If it does not, record "Ruling: no enum registry on main yet - crew_wsl.mode() normalises instead - a bad value is written but read as native and named".

### Step 2: `crew_wsl.py` pure functions: host OS, path translation, output decoding, repo location
Files: plugin/crew/hooks/scripts/crew_wsl.py, plugin/crew/tests/test_crew_wsl.py
Test: python3 -m pytest plugin/crew/tests/test_crew_wsl.py -q -p no:cacheprovider
Risk: med. A wrong translation sends a job to the wrong directory. Every refusal returns None plus a reason, never a guessed path.
- [ ] Tests first:
  - `test_to_wsl_path`, parametrised over the spec's five mappings, plus a lowercase drive letter and a trailing separator.
  - `test_to_wsl_path_refuses`: another distro's `\\wsl$` path, `\\server\share`, and a relative path.
  - `test_repo_location`: `windows-drive`, `wsl-fs`, or `unknown` for anything else.
  - `test_decode_utf16_and_utf8`: bytes of `"Ubuntu\r\n"` encoded as UTF-16LE with a BOM, UTF-16LE without one, and UTF-8.
  - `test_host_os`: `platform.system()` and `MSYSTEM` are monkeypatched to give `windows`, `windows-bash`, `linux`, `macos` and `wsl`. `wsl` is Linux with `microsoft` in the osrelease text passed in.
- [ ] Create `crew_wsl.py` with a module docstring that names the spec and the no-hook rule. It holds `host_os(system=None, env=None, osrelease=None)`, `to_wsl_path(path, distro=None) -> (str|None, reason)`, `repo_location(path)` and `decode(data: bytes) -> str`. `decode` treats NUL bytes as UTF-16LE and strips the BOM and `\0`, matching `plugin/crew/skills/crew-setup/scripts/platform.ps1:8`. Standard library only, and it imports no crew module at import time.
- [ ] Run the Test command green.

### Step 3: the probe, its states, and the machine-local cache
Files: plugin/crew/hooks/scripts/crew_wsl.py, plugin/crew/tests/test_crew_wsl.py
Test: python3 -m pytest plugin/crew/tests/test_crew_wsl.py -q -p no:cacheprovider
Risk: high within this ticket. The recurring repo bug is an unknown collapsing into a safe-looking value. A probe that could not run must read `unknown`, never `not-installed`.
- [ ] Tests first:
  - `test_probe_classifies` is fed through a fake `runner(argv, timeout) -> (rc, stdout_bytes, stderr_bytes)` plus a fake `which`. It is parametrised over:
    - `usable`: `wsl.exe --list --verbose` shows `* Ubuntu Running 2`, and the in-distro `command -v python3 git` succeeds
    - `not-installed`: `which("wsl.exe")` is None
    - `no-distro`: UTF-16LE "Windows Subsystem for Linux has no installed distributions"
    - `wsl1-only`: VERSION 1
    - `no-python3`
    - `broken`: rc 1 with stderr, which is quoted verbatim in `detail`
    - `broken`: `subprocess.TimeoutExpired`
    - `unknown`: the runner raises `OSError`
  - `test_probe_failure_is_unknown_not_absent`.
  - `test_probe_never_installs`: the fake runner records every argv, and none contains `--install`, `--update` or `--set-default-version`.
  - `test_probe_honours_configured_distro`: with `wslRouting.distro = "Debian"`, every in-distro call uses `-d Debian`.
  - `test_cache_write_is_atomic_and_lf`: `json.dump` is monkeypatched to raise, and the prior cache stays byte-identical with no `*.tmp` left behind.
  - `test_cache_is_machine_local`: `PROBE_PATH` is `os.path.join(os.path.dirname(crew_state.GLOBAL_CONFIG_PATH), "wsl-probe.json")`.
  - `test_not_installed_recommendation`: the text names `wsl --install -d Ubuntu`, an elevated shell, a reboot, and the measured fork and write numbers from direction.md.
- [ ] Implement `probe(runner=None, which=shutil.which, distro=None) -> dict` with `state`, `distro`, `version`, `python3`, `git`, `detail`, `probedAt` and `host`. It returns `{"state": "n/a"}` without calling the runner unless `host_os()` is `windows` or `windows-bash`. The calls are:
  - `wsl.exe --list --verbose` (timeout 15s)
  - `wsl.exe -d <distro> -e sh -c 'command -v python3; command -v git'` (timeout 30s, which covers a cold VM start)

  Add `load_cache()`, which returns `{"state": "unknown", "detail": "never probed"}` when the cache is absent or unreadable. Add `write_cache(result)`, which computes the text first and then writes a temp file with `newline="\n"` and calls `os.replace`, and `recommendation(result)`.
- [ ] CLI `probe [--json] [--write]`. It prints the state, the reason, and for `not-installed` the recommendation. `--write` is the only path that writes the cache. It exits 0 for every state, including `unknown`: the state is data, not a failure.
- [ ] Run the Test command green.

### Step 4: decide, run and measure
Files: plugin/crew/hooks/scripts/crew_wsl.py, plugin/crew/tests/test_crew_wsl.py
Test: python3 -m pytest plugin/crew/tests/test_crew_wsl.py -q -p no:cacheprovider
Risk: high. This is the step that changes where a user's tests run. `wsl` mode must refuse loudly, `auto` must say why it fell back, and a non-Windows host must be untouched.
- [ ] Tests first:
  - `test_decide` is a table over mode (`auto`/`wsl`/`native`/`"bogus"`) x state (every Step 3 state plus `n/a`) x location (`windows-drive`/`wsl-fs`/`unknown`) x measured (`none`/`wsl-faster`/`native-faster`). The expected `(route, reason, exit)` follows the spec's rules, and every native reason names its state.
  - `test_off_windows_is_inert`, parametrised over `linux`, `macos` and `wsl`. The runner is a mock that fails the test if called. `run -- 'printf "a\n"; echo b >&2; exit 3'` is compared, run for real through `subprocess`, with `bash -c` of the same string: identical stdout, stderr and rc.
  - `test_run_argv_for_wsl`: the command string arrives in argv unchanged, with quotes, `$VAR`, and a `/c/x` path.
  - `test_run_passes_exit_code_through` for 0, 1 and 7.
  - `test_run_prints_one_route_line_to_stderr`: exactly one `crew-wsl: ` line, on stderr only, on Windows only.
  - `test_run_preflight_missing_tool`: in `auto`, native plus the reason; in `wsl`, exit 3 and the child never runs.
  - `test_measure_reports_both_sides`: an injected timer and runner, 50 forks and 200 writes per side, and the result carries host, date, repo location and both sides' seconds. `measure --write` stores it in the cache's `measured` key.
- [ ] Implement:
  - `mode(cfg)`, which normalises through `crew_config.resolve_config(root)`, imported lazily.
  - `decide(mode, probe, location, measured, host)`.
  - `wsl_argv(cmd, cwd, distro)`.
  - `run(cmd, root=".", runner=None)`, which runs a preflight `wsl.exe -d <distro> -e sh -c 'command -v <first word>'`. The first word comes from `shlex.split`, and a parse failure means native plus a reason.
  - `measure(root, runner=None, timer=time.perf_counter)`.
  - The CLI subcommands `run -- <cmd>` (one argument) and `measure [--write]`.
- [ ] Run the Test command green.

### Step 5: the `/crew:status` shell line, Windows only
Files: plugin/crew/hooks/scripts/crew_wsl.py, plugin/crew/hooks/scripts/crew_status.py, plugin/crew/tests/test_status.py
Test: python3 -m pytest plugin/crew/tests/test_status.py plugin/crew/tests/test_crew_wsl.py -q -p no:cacheprovider
Risk: med. `crew_status.py` is read-only by a tested contract (`plugin/crew/hooks/scripts/crew_status.py:15-19`, `plugin/crew/tests/test_status.py:57`), so the line must run no `wsl.exe` and write nothing.
- [ ] Tests first:
  - `test_status_has_no_shell_line_off_windows`: on Linux, output is byte-identical with and without a cache file.
  - `test_status_shell_line_on_windows`: `crew_wsl.host_os` is monkeypatched to `windows-bash`, parametrised over `usable` with mode `auto` and `wsl-fs`, `not-installed`, `unknown` and `broken`. Each asserts the exact line text.
  - `test_status_shell_line_runs_no_subprocess`: `subprocess.run` inside `crew_wsl` is monkeypatched to raise.
  - Rerun `test_status_is_read_only` and `test_status_output_fits_forty_lines_on_a_busy_repo` with the Windows line forced on.
- [ ] Implement `crew_wsl.status_line(root)`, which returns None off Windows and otherwise `shell    <route> - <reason>` from the cache and config only. Call it from `collect()` after the `verify` line (`crew_status.py:208`). Append the line only when it is not None.
- [ ] Run the Test command green.

### Step 6: sabotage entries, and a check of each neighbouring case
Files: plugin/crew/tests/sabotage_wsl.py, plugin/crew/tests/sabotage.py
Test: /root/crew-tmp/heavy-run python3 plugin/crew/tests/sabotage.py
Risk: med. A mutation whose `find` string does not match is a silent no-op. The harness refuses those (`plugin/crew/tests/test_sabotage_harness.py`), and that refusal is confirmed.
- [ ] Write `WSL_MUTATIONS` in `sabotage_wsl.py` in the documented shape `(label, target, find, replace, test)`, with the seven entries the spec lists. Each entry names the one test that must go red.
- [ ] Register it: import it at `plugin/crew/tests/sabotage.py:67-79` and concatenate it at `:3050-3052`.
- [ ] Run the Test command. Every WSL entry must report red for real, with the named test failing on an assertion, and the tree must be restored byte-identical.
- [ ] Check each neighbouring case, then run again. The neighbour is the case the fix sits beside:
  - Off-Windows inertness is checked for `macos` as well as `linux`.
  - `unknown` must not read as `not-installed`, and `broken` must not read as `usable` either.
  - The other distro's `\\wsl.localhost` path is checked, not only `\\wsl$`.

  Add a test for any neighbour not already covered.

### Step 7: a verify.json rule for the new code
Files: .crew/verify.json
Test: python3 -m pytest plugin/crew/tests/test_crew_wsl.py plugin/crew/tests/test_status.py -q -p no:cacheprovider
Risk: low. A rule with no `seconds` reads as unknown cost.
- [ ] Add a rule. Its paths are `plugin/crew/hooks/scripts/crew_wsl.py`, `plugin/crew/hooks/scripts/crew_status.py`, `plugin/crew/tests/test_crew_wsl.py`, `plugin/crew/tests/test_status.py` and `plugin/crew/tests/sabotage_wsl.py`. Its run is the Test command above. Its `seconds` is measured with `/usr/bin/time` under heavy-run, and its `why` names the host, date and load, matching rule 9's style.
- [ ] Run `bash plugin/crew/skills/crew-setup/scripts/map-audit.sh` and confirm the rule parses.

### Step 8: docs, per the owner rule for plugin/crew changes
Files: plugin/crew/skills/crew-setup/platform.md, plugin/crew/skills/crew-setup/phases.md, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/skills/crew-setup/global-config.md, plugin/crew/skills/crew-execute/SKILL.md, plugin/crew/skills/crew-graph/SKILL.md, plugin/crew/commands/status.md, plugin/crew/commands/config.md, plugin/crew/commands/implement.md, plugin/crew/README.md, plugin/crew/CONFIG.md, plugin/PLUGINS.md, docs/guides/crew/**, .crew/codemap/**, .claude/rules/**, docs/diagrams/**, plugin/crew/BUDGETS.md, plugin/crew/.budget-allowance.json
Test: (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py) && python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check && python3 scripts/check-marketplace.py
Risk: med. `BUDGETS.md`'s `crew-markdown-lines` claim moves with every resize and is checked. Command files have line budgets, so procedure goes into `platform.md`, not into the commands.
- [ ] `platform.md`: add a "Routing heavy jobs through WSL" section. It covers:
  - the probe states and what each does under each mode
  - the measured table from direction.md, with host and date
  - why a Windows-drive repo is routed only when measured
  - the in-WSL clone offer (offer only, with `measure` numbers, never automatic)
  - the install recommendation, which is never run
  - what is not routed (hooks, `verify-gate.sh --all`, record-writing jobs, git)
  - the Git Bash `python3`/`python`/`py -3` resolution

  Update `:185-186` to point at it.
- [ ] `phases.md` Phase 0 (`:64-90`): on Windows, run `crew_wsl.py probe --write`. When the state is `usable`, also run `measure --write`. Report the numbers, and ask about the mode and any clone. Update the "Done when" line.
- [ ] `crew-setup/SKILL.md`: add `"wslRouting"` to the config JSON example (`:154` area) and add a pointer in `:50-54`. `global-config.md`: add the `wslRouting` block to "Ask, one block at a time".
- [ ] `crew-execute/SKILL.md:32-36` and `commands/implement.md` §4 (`:69-72`): on Windows, run the step's test and the map's checks through `crew_wsl.py run -- "<command>"`, and print its route line. `crew-graph/SKILL.md:44`: the same for the graphify build. `commands/status.md`: add a `shell` row to the table (`:24-37`), with "Windows only". `commands/config.md`: add one line on probing and routing.
- [ ] `plugin/crew/README.md` (`:83-128`): add a short routing paragraph that links to `platform.md`. `CONFIG.md`: add `wslRouting.mode` and `wslRouting.distro` rows next to `:789-792`, plus a paragraph beside `:804-807` on why the preference is not in `platform.*`. `plugin/PLUGINS.md`: add the behaviour to the crew row.
- [ ] `docs/guides/crew/src/troubleshooting.md` (`:70` table area): add a "slow on Windows" entry that names `/crew:status`'s `shell` line. Then rebuild with `/root/crew-tmp/heavy-run python3 docs/guides/crew/src/build.py` and commit the HTML, DOCX and PDF outputs.
- [ ] `.crew/codemap/crew.md`: add a DERIVED entry for `crew_wsl.py`, with repo-relative `path:line` anchors and an updated `anchor:`. Regenerate `.claude/rules/` with `crew_instructions.py rules --root .`. `docs/diagrams/data-flow-crew-config.mmd`: add `wslRouting` and the probe cache, then render with the crew-diagrams render script.
- [ ] Re-measure `git ls-files 'plugin/crew/*.md' | xargs wc -l` and update `BUDGETS.md`. Touch `.budget-allowance.json` only if `scripts/check_instructions.py` reports a touched command over budget.
- [ ] Run the Test command green.

### Step 9: version bump, changelog, full gate
Files: plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, CHANGELOG.md
Test: python3 scripts/check-marketplace.py && /root/crew-tmp/heavy-run python3 -m pytest plugin/crew/tests/ -q -p no:cacheprovider
Risk: low. Shipping without a bump leaves every installed copy stale forever (CLAUDE.md, "Stop and ask").
- [ ] Bump crew to the next patch above origin/main's version at implement time, in `plugin.json`, in `marketplace.json`, and at the `plugin-version:crew` claim at `plugin/PLUGINS.md:14`. Add a CHANGELOG entry that names the new key, the new module, the status line, and "hooks unchanged".
- [ ] Run the hooks-unchanged check from the spec's Acceptance list. It must exit 0.
- [ ] Run the Test command. Quote any failure verbatim, and name which suites ran and which did not (`drift-detection.sh` is not run by this ticket).
- [ ] Delete untracked `.crew/.verify-gate*.json`, `.crew/.scope-base` and `.crew/metrics.md` bookkeeping before bundling. They stay untracked (T-0068).

### Step 10: native Windows acceptance by win-repo-2
Files: plugin/crew/skills/crew-setup/platform.md
Test: on dadeush-legion, native Windows Git Bash: python crew_wsl.py probe --json; python crew_wsl.py measure; python crew_wsl.py run -- "python3 -m pytest plugin/crew/tests/test_crew_wsl.py -q"
Risk: med. This is the only real-WSL evidence. If it disagrees with the fixtures, the fixtures are wrong and Steps 3-4 reopen, rather than the numbers being adjusted.
- [ ] The owner's win-repo-2 session runs the three Test commands twice, once with the repo on a Windows drive and once inside WSL's ext4 through `\\wsl.localhost\`. It records the output verbatim: the state, the route line, forks and writes per side, and the pytest result.
- [ ] Confirm or refute each Unknown the spec assigned to this run: `--cd` with the translated path, and MSYS conversion of the command string. On refutation, amend the spec and re-plan before changing code.
- [ ] Write the measured table into `platform.md`'s routing section with host and date. The PR body carries the same numbers, plus the statement that `dadeush-lenovo` and `dadeush-desktop` were not measured.
