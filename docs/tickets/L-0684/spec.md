# L-0684 gizmoduck tool lookup: one tool home, and an explicit override beats PATH (external report item 10)          status: spec   risk: med
Split from T-0108 on 2026-10-04. Written against origin/main `155fe6d8` (gizmoduck 0.5.6). Filed as L-0684. Its direction is `direction.md` beside this file. The owner was not available; defaults taken are under "Open questions for the owner".

## Intent
Every gizmoduck adapter finds its tool by one rule, in one order: the tool's own override variable, then the gizmoduck tool home (`GIZMODUCK_HOME`, default `~/.local/share/gizmoduck` on Linux and macOS), then PATH, then the platform's well-known location. An override that is set but does not resolve makes that tool unavailable and `doctor` names the variable; it never falls through to a different install. The variables and the order are documented.

## Exclusions
- No change to `bootstrap.sh` or `bootstrap.ps1`. Installing into the tool home is L-0685.
- No change to what any tool does once found: no argv, parser, timeout or default changes. Safe Nuclei defaults are T-0108.
- No change to `plugin/crew/**`; PR body says `Docs: none for crew - gizmoduck only`. No path in `HARNESS` or `SEAM` (`scripts/check-tooling-pr.py:58-95`).
- No hook, no new command, no new registered entry; no count in `plugin/PLUGINS.md`, `plugin/README.md` or `README.md` changes.
- `GIZMODUCK_MSYS2_BIN` (`scanners/testssl.py:50-57`) keeps its current behaviour. It locates a helper directory for Git Bash, not a scanner.
- No Windows default for the tool home. With `GIZMODUCK_HOME` unset on Windows there is no tool home and the existing `LOCALAPPDATA` locations stay as the last step, exactly as today.
- No new per-tool override variables for the seven PATH-only adapters. They gain the tool home through `base.which`; that is enough for L-0685.
- `doctor`'s exit status rule does not change: only a missing Nuclei or missing templates make it non-zero (`gizmoduck.py:1364-1367`).
- The guides under `docs/guides/gizmoduck/` have no source in the repo and are not rebuilt; one `TODO.md` bullet.

## Design
- `scanners/base.py`:
  - `tool_home()` returns a `Path` or `None`: `GIZMODUCK_HOME` when set and not empty; otherwise, when `os.name != "nt"`, `$XDG_DATA_HOME/gizmoduck` if `XDG_DATA_HOME` is set, else `~/.local/share/gizmoduck`; otherwise `None`. It does not create the directory.
  - `which(binary)` returns `<tool home>/bin/<binary>` when that is a file the process may execute, else `shutil.which(binary)`. All ten adapters and `find_nuclei` therefore see the tool home's `bin` ahead of PATH.
  - `override(var)` returns one of three states with the value: `unset`, `ok`, `broken`. "Could not tell" is its own state and is never folded into `unset`. Read at call time, never at import.
- `scanners/zap.py` `_resolve_zap_command`, in order: (1) `GIZMODUCK_ZAP_HOME` set: a `zap.sh` or `zap.bat` in that directory, else a `zap-*.jar` under it with `java`; if neither, return `None` and stop. (2) `<tool home>/zap`, same search. (3) a wrapper via `base.which`. (4) `%LOCALAPPDATA%\Programs\zap` jar with `java`, as today.
- `scanners/nikto.py` `_resolve_argv` and `is_available`, in order: (1) `GIZMODUCK_NIKTO_PL` set: that file with `perl`, else `None` and stop. (2) `<tool home>/nikto/program/nikto.pl` with `perl`. (3) `nikto` via `base.which`. (4) the `LOCALAPPDATA` path with `perl`. `is_available` and `_resolve_argv` share one resolver so they cannot disagree.
- `scanners/testssl.py` `_resolve_command`, same four steps with `GIZMODUCK_TESTSSL_SH`, `<tool home>/testssl.sh/testssl.sh` and `bash`.
- `gizmoduck.py` `find_nuclei` resolves through the same `which` (tool home `bin` first), then `~/go/bin/nuclei` as today. It uses `base.tool_home`; it does not keep a second copy of the default path.
- `gizmoduck.py` `cmd_doctor` prints one line for the tool home (the path, and whether it exists) and one line per lookup variable that is set: `OK` with the path when it resolves, `!!` naming the variable, its value and the tool it disables when it does not. These lines do not change the exit status.
- Flag as a behaviour change in the CHANGELOG: where an override is set and a different copy is on PATH, the override now wins; where an override is set and stale, the tool is now unavailable instead of quietly using the PATH copy.

## Evidence
All at origin/main `155fe6d8`, read 2026-10-04.
- `plugin/gizmoduck/scripts/scanners/base.py:37-38` - `which` is `shutil.which` and nothing else.
- `plugin/gizmoduck/scripts/scanners/zap.py:57-58` - `_zap_binary` asks PATH for `zap.bat` / `zap.sh`; `:70-77` builds the jar directories, override then `LOCALAPPDATA`; `:87-92` globs `zap-*.jar` only; `:102-109` PATH wrapper first, jar second.
- `plugin/gizmoduck/scripts/scanners/nikto.py:89-95` - candidates built at import from `GIZMODUCK_NIKTO_PL` and `LOCALAPPDATA`; `:112-119` PATH `nikto` first; `:122-125` `is_available` repeats the logic separately.
- `plugin/gizmoduck/scripts/scanners/testssl.py:64-70` - candidates built at import; `:95-102` PATH first, then the script through `bash`.
- `plugin/gizmoduck/scripts/gizmoduck.py:141-148` - `find_nuclei`: `shutil.which`, then `~/go/bin/nuclei`.
- `plugin/gizmoduck/scripts/gizmoduck.py:1311-1399` - `cmd_doctor`; `:1358-1397` the per-adapter listing; `:1364-1367` the exit-status convention.
- `plugin/gizmoduck/scripts/scanners/{checkov,semgrep,trivy,depcheck,nmap,sqlmap}.py` - each `is_available` is `base.which(<name>) is not None` (for example `trivy.py:98-99`, `sqlmap.py:158-159`).
- `plugin/gizmoduck/scripts/_test/test_routine_cli.py:1081-1095` - `_sanitised_env` empties PATH, moves `HOME` and `LOCALAPPDATA` to a temp directory and pops four `GIZMODUCK_*` variables; it does not know `GIZMODUCK_HOME` or `XDG_DATA_HOME`.
- `plugin/gizmoduck/scripts/_test/test_scanner_nikto.py:23`, `test_scanner_checkov.py:322` - the existing suites replace `base.which` by monkeypatch, so a changed `which` body does not disturb them.
- `plugin/gizmoduck/bootstrap.ps1:15` - Windows tools are extracted under `%LOCALAPPDATA%\Programs`, the location step 4 keeps.
- `git grep -n "GIZMODUCK_ZAP_HOME\|GIZMODUCK_NIKTO_PL\|GIZMODUCK_TESTSSL_SH" origin/main -- plugin/gizmoduck/README.md plugin/gizmoduck/skills plugin/gizmoduck/commands` - no hits: undocumented.
- `plugin/gizmoduck/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:230`, `plugin/PLUGINS.md:449` - the three version sites.
- `.crew/verify.json:263-267` - the `plugin/gizmoduck/**` rule.

## Unknowns
- **Does any existing test rely on the real `shutil.which` finding nothing?** Once a developer has a populated tool home, the new `which` could find real tools from inside a test. Resolve at implement: an autouse fixture in `conftest.py` points `GIZMODUCK_HOME` at an empty temp directory and removes the three override variables and `XDG_DATA_HOME`, so no test reads the real home. Then run the whole gizmoduck suite.
- **Windows executability check.** `os.access(path, os.X_OK)` is true for any existing file on Windows. Accepted as risk: with no default tool home on Windows the `bin` step only runs when `GIZMODUCK_HOME` is set by the operator.
- **A ZAP zip layout where `zap.sh` sits one level down** (`ZAP_<version>/zap.sh`). Resolve at implement by reading what the Crossplatform zip extracts (`bootstrap.sh:199-202` uses `/opt/ZAP_<num>/zap.sh`): the override and tool-home search look in the directory itself and one level below it, wrapper first.
- **Is anyone relying on PATH beating a set override?** Not knowable from the repo. Accepted as risk and flagged in the CHANGELOG.

## Touch
- `plugin/gizmoduck/scripts/scanners/base.py` - tool_home, which, override
- `plugin/gizmoduck/scripts/scanners/zap.py`
- `plugin/gizmoduck/scripts/scanners/nikto.py`
- `plugin/gizmoduck/scripts/scanners/testssl.py`
- `plugin/gizmoduck/scripts/gizmoduck.py` - find_nuclei and cmd_doctor only
- `plugin/gizmoduck/scripts/_test/test_tool_lookup.py` - new
- `plugin/gizmoduck/scripts/_test/conftest.py` - the autouse isolation fixture
- `plugin/gizmoduck/scripts/_test/test_base.py`
- `plugin/gizmoduck/scripts/_test/test_scanner_zap.py`
- `plugin/gizmoduck/scripts/_test/test_scanner_nikto.py`
- `plugin/gizmoduck/scripts/_test/test_scanner_testssl.py`
- `plugin/gizmoduck/scripts/_test/test_doctor.py`
- `plugin/gizmoduck/scripts/_test/test_routine_cli.py` - the sanitised environment also clears GIZMODUCK_HOME and XDG_DATA_HOME
- `plugin/gizmoduck/README.md` - a "Where gizmoduck looks for tools" section with the order and a table of variables
- `plugin/gizmoduck/skills/gizmoduck/SKILL.md` - one paragraph pointing at that section
- `plugin/gizmoduck/commands/doctor.md` - doctor now reports the tool home and broken overrides
- `plugin/gizmoduck/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `TODO.md` - one follow-up bullet for the gizmoduck guides
- `.crew/codemap/**` - re-anchor only, owner's standing rule
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt by graphify update, committed as it leaves them

## Acceptance checks
Rule for every pytest line: `.crew/verify.json` `plugin/gizmoduck/**` (`python3 -m pytest plugin/gizmoduck/scripts/_test/ -q`). Every test builds its tools as empty executable files under `tmp_path`; none installs or runs a scanner, and none reads the real home.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_tool_lookup.py -q` passes, with these tests by name:
  - `test_tool_home_uses_gizmoduck_home_when_set`
  - `test_tool_home_defaults_under_xdg_data_home_then_local_share` - parametrized over `XDG_DATA_HOME` set and unset.
  - `test_tool_home_is_none_on_windows_without_gizmoduck_home` - `os.name` patched to `nt`.
  - `test_which_prefers_tool_home_bin_over_path` - the same name in both; the tool home's wins.
  - `test_which_ignores_a_non_executable_file_in_tool_home_bin` - POSIX only, skipped with a reason on Windows.
  - `test_override_states_unset_ok_broken`
  - `test_zap_override_beats_path` - a wrapper on PATH and a different one in `GIZMODUCK_ZAP_HOME`; the override's is returned.
  - `test_zap_override_finds_wrapper_not_only_jar`
  - `test_zap_broken_override_is_unavailable_and_does_not_fall_through` - override points at an empty directory, a working wrapper is on PATH; `is_available()` is `False`.
  - `test_zap_tool_home_beats_path`
  - `test_nikto_override_beats_path`, `test_nikto_broken_override_is_unavailable_and_does_not_fall_through`, `test_nikto_tool_home_script_is_found_with_perl`
  - `test_nikto_reads_the_override_at_call_time` - the variable is set after the module is imported and is still honoured.
  - `test_nikto_is_available_agrees_with_resolve_argv` - parametrized over the four steps.
  - `test_testssl_override_beats_path`, `test_testssl_broken_override_is_unavailable_and_does_not_fall_through`, `test_testssl_tool_home_script_is_found_with_bash`
  - `test_find_nuclei_prefers_tool_home_bin`
  - `test_localappdata_is_still_the_last_step` - parametrized over zap, nikto, testssl: nothing else resolves, the `LOCALAPPDATA` location does.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_doctor.py -q` passes, including `test_doctor_reports_tool_home` and `test_doctor_names_a_broken_override_without_changing_exit_status`.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_routine_cli.py -q` passes; the sanitised-environment tests still find no scanner with `GIZMODUCK_HOME` and `XDG_DATA_HOME` set in the parent environment (set both to a populated temp directory in the test that proves it: `test_sanitised_env_clears_tool_home`).
- [ ] Sabotage, by hand, quoted in the PR: make the broken-override branch fall through to PATH; `test_*_broken_override_*` go red. Restore; green. Then swap override and PATH order in `zap.py`; `test_zap_override_beats_path` goes red. Check the `.pyc` timestamp if a restore appears not to take.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/ -q` passes whole.
- [ ] `git grep -n "GIZMODUCK_HOME" -- plugin/gizmoduck/README.md` hits, and the README section lists `GIZMODUCK_HOME`, `GIZMODUCK_ZAP_HOME`, `GIZMODUCK_NIKTO_PL`, `GIZMODUCK_TESTSSL_SH` and `GIZMODUCK_MSYS2_BIN` with the four-step order and the sentence that a set-but-broken override disables the tool.
- [ ] Version bumped in all three places one patch past what origin/main holds at push time, committed, then `python3 scripts/check-marketplace.py` passes.
- [ ] `CHANGELOG.md` has a heading entry naming the version, this ticket, and the two behaviour changes.
- [ ] ruff and pylint: no new findings against the merge-base (`.crew/verify.json` rule for `**/*.py`).
- [ ] `python3 scripts/check-tooling-pr.py` exits 0. Exit 77 means the check did not run; report that.

## Dependencies
Must land before this ticket:
- T-0107 - **done** (merged as #273, gizmoduck 0.5.5): the routine CLI and the sanitised-environment tests this ticket edits.
- L-0599 - **done** (merged as #315, gizmoduck 0.5.6).

No hard dependency on T-0108 (direction; safe Nuclei defaults). Both edit `gizmoduck.py`, the README and the version files: land one, merge origin/main into the other (merge, never rebase), re-bump.

This ticket blocks: L-0685 (bootstrap without sudo installs into the tool home defined here).

## Size
About 110 production lines: `base.py` 35, `zap.py` 25, `nikto.py` 20, `testssl.py` 15, `gizmoduck.py` 15. No new parser, no state machine, no harness path. One small three-state resolver (`unset` / `ok` / `broken`).

## Open questions for the owner
Each has a default already taken; none blocks the build.
1. A set-but-broken override disables the tool. Alternative: warn and fall through to the next step.
2. Default tool home `~/.local/share/gizmoduck` (XDG). Alternative: `~/.gizmoduck`.
3. testssl is included although the report names only ZAP and nikto, because it has the identical defect. Alternative: leave it for a follow-up.
4. Tool home `bin` is searched ahead of PATH. Alternative: PATH first, tool home as a fallback.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
