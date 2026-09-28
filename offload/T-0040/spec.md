# T-0040 on Windows, crew runs its shell-heavy jobs in WSL2 when WSL is usable, recommends installing it when it is not, and says which shell it used and why          status: spec   risk: med
## Intent
On a Windows machine, crew detects whether WSL2 is usable from the Windows side: `wsl.exe` present, a WSL2 distro, and `python3` and `git` inside it. It records the answer as a machine fact. Crew's long-running shell jobs then run through one wrapper, `crew_wsl.py run`: the per-step test runs and verification-map commands during `/crew:implement`, and graphify builds. The wrapper routes the job into WSL when the resolved route is `wsl`. Otherwise it runs the job in the native shell exactly as today, and it prints the reason. The route is a preference, `wslRouting.mode` (`auto` | `wsl` | `native`, default `auto`), settable on both layers.

Repo location is weighed, not ignored. A checkout on a Windows drive is reached from WSL through `/mnt/<drive>`, and that path is about 71x slower for small writes, so `auto` routes such a repo into WSL only when `crew_wsl.py measure` has shown WSL to be faster for that repo. A checkout inside WSL's own filesystem, opened from Windows through `\\wsl$\` or `\\wsl.localhost\`, routes to WSL. Crew offers an in-WSL clone with the measured numbers and never makes one.

When WSL is not installed, crew recommends it with the measured reason and the exact command (`wsl --install -d Ubuntu`, elevated, then a reboot), and never runs it. Every fallback is explicit. `/crew:status` gains a `shell` line on Windows only. It says which shell crew uses and why, so a silent fallback cannot hide a slow machine. Hooks do not change, and nothing changes on Linux, macOS or inside a WSL session.

## Exclusions
- No hook changes. `plugin/crew/hooks/hooks.json`, every hook `.sh`/`.ps1` and `crew_platform.py` stay byte-identical. This includes the SessionStart `platform-sync` path and its `DERIVED_KEYS`, and the Stop-hook verify gate. A SessionStart hook must answer fast on every machine, and `wsl.exe` can take seconds to start a stopped VM.
- `verify-gate.sh --all` is not routed, and neither is anything that writes crew's own records: gate records, approval receipts, review ledgers, metrics. The gate fingerprints git index entries (`plugin/crew/hooks/scripts/verify_fingerprint.py:206`). A WSL git reading a Windows checkout sees different stat data and filemode, and a record written that way would disagree with the one the native Stop hook writes.
- Never installs WSL, never runs `wsl --install` or `wsl --update`, and never enables a Windows feature. It recommends only.
- Never clones, moves or copies a repository into WSL. It offers, with numbers, and the owner decides, because a move changes paths that other tools and sessions use.
- Writes no `wsl.exe` wrapper into `.crew/verify.json` and changes nothing in `resolve-tools.sh`. The map stays shared across machines. `wsl.exe -e <tool>` for a WSL-only tool is resolve-tools' existing, separate mechanism.
- Adds no ticket status. The needs-owner status belongs to T-0037, which is not merged, so the install recommendation is printed by `/crew:init`, `/crew:config` and `/crew:status`.
- Does not route interactive or one-off commands, git operations, or `sabotage.py`/pytest runs in this repository's own agent workflow (`heavy-run`).
- No behaviour change on Linux, macOS or inside WSL: no probe, no subprocess, no status line, and `run` executes the command exactly as native.

## Evidence
Anchored to origin/main `bebbb97f` (crew 1.0.46).
- The ask and the measurements. `.work/tickets/T-0040/direction.md` records the owner-approved direction (2026-09-26). Measured on `dadeush-legion` in two independent sessions: 50 trivial forks took 27.7-35.5s in Git Bash against 0.19-0.20s in WSL2; 20 subshell+pipe round trips took 20.4s against 0.28s; 200 small writes took 4.43s on `/mnt/c` against 0.062s on WSL's ext4.
- `plugin/crew/hooks/scripts/crew_platform.py:136-165` `detect()`. On native Windows (`:156-161`) it sets only `os` and `shell` from `MSYSTEM`. `_wsl_facts()` (`:86-133`) detects WSL only when the interpreter runs INSIDE WSL (`/proc/sys/kernel/osrelease`). Nothing asks, from Windows, whether WSL is usable.
- `plugin/crew/hooks/scripts/crew_platform.py:72-75` `DERIVED_KEYS` includes `shell`, and platform-sync rewrites it every SessionStart (`:565-584`). The direction's "set `platform.shell: wsl`" would be overwritten on the next session. That is why the preference goes in a new block, `wslRouting`, and the probe goes in a machine-local cache.
- `plugin/crew/hooks/scripts/crew_platform.py:398-404` already reports a `/mnt/` clone as slow from inside WSL. `plugin/crew/skills/crew-setup/platform.md:57-62` says "prefer WSL when it exists", `:66-78` covers repo location, and `:185-186` says "on native Windows with WSL available ... ask which they want".
- `plugin/crew/skills/crew-setup/scripts/resolve-tools.sh:131-162` probes WSL reachability from Git Bash with `wsl.exe -e true` and reads the distro with `wsl.exe -e sh -c 'echo "$WSL_DISTRO_NAME"'`. `plugin/crew/skills/crew-setup/scripts/platform.ps1:5-8` strips `\0` from `wsl --list --quiet`. That output is UTF-16LE, which the probe has to decode.
- `plugin/crew/README.md:236-240` ("Resolve once at setup ... Never branch at runtime") and `plugin/crew/skills/crew-setup/phases.md:83-84` are the rule the route honours. The route is resolved once, by `/crew:init` or `/crew:config`, recorded, and printed on every run. It is never re-decided silently per command.
- `plugin/crew/hooks/scripts/crew_config.py:322-327` is the repo `platform` block (derived, repo-only). `:393` `default_global_config()` ends at `:563`, with `route` the last block. `plugin/crew/tests/test_crew_config.py:76-90` asserts `platform` is repo-only, and `:102-110` asserts every global key is a real repo key. So `wslRouting` goes in both `default_config()` and `default_global_config()`. `:55-72` holds both templates byte-equal to `plugin/crew/templates/config.template.json` and `plugin/crew/templates/global.template.json`.
- `plugin/crew/hooks/scripts/crew_status.py:192-216` `collect()`. Line count is capped at `MAX_LINES = 40` (`:37`), and `:15-19` makes read-only a tested property (`plugin/crew/tests/test_status.py:57` `test_status_is_read_only`). A `shell` line therefore reads the cache and config and runs no `wsl.exe`.
- `plugin/crew/commands/status.md:24-37` is the line table the new `shell` row joins.
- Heavy jobs the agent runs: `plugin/crew/commands/implement.md:69-72` (§4 Verify runs the verify.json checks), `plugin/crew/skills/crew-execute/SKILL.md:32-36` (each step's test, run red and then green) and `plugin/crew/skills/crew-graph/SKILL.md:44` (`graphify . --no-viz --code-only`).
- Sabotage registry. `plugin/crew/tests/sabotage.py:67-79` imports the sibling mutation tuples, and `:3050-3052` concatenates them.
- `.crew/verify.json` rules. Rule 7 covers `crew_config.py`, the templates and `CONFIG.md`. Rule 8 covers `crew_platform.py`. Rule 9 runs the full suite when `sabotage.py` changes. Rule 12 runs `validate-prompts.py` for commands and skills. Rule 0 runs `check-marketplace.py`. Rule 24 runs `crew_instructions.py rules --check`. No rule names `crew_status.py` or a WSL module.
- Docs that describe this behaviour:
  - `plugin/crew/README.md:83-100` (platform detection, "If WSL is available, run Claude Code inside it") and `:102-128`
  - `plugin/crew/CONFIG.md:789-792`, `:804-807` (`platform.*` rows)
  - `plugin/PLUGINS.md:14` (`<!-- claim: plugin-version:crew -->`), `:38` (the platform-sync row)
  - `docs/guides/crew/src/troubleshooting.md:70`
  - `.crew/codemap/crew.md:24`
  - `docs/diagrams/data-flow-crew-config.mmd`
  - `plugin/crew/BUDGETS.md` (`<!-- claim: crew-markdown-lines -->`, which moves with every `plugin/crew/*.md` resize)
- CLAUDE.md landmines that apply here:
  - Git Bash ships without `python3`, so the commands resolve `python3`/`python`/`py -3` as `plugin/crew/commands/status.md:18-19` does.
  - `pathlib.write_text` converts to CRLF on Windows.
  - Branch on the tool, not the OS.
  - An unknown must not collapse into the safe-looking value: a probe that could not run is `unknown`, never `not-installed`.

## Unknowns
- Whether `wsl.exe --cd <linux path>` accepts the translated path for every repo location (drive, spaces, `\\wsl$`). Resolved by the win-repo-2 acceptance run (Step 10) on `dadeush-legion`, native Windows. Until then the argv construction is fixture-tested only.
- `wsl.exe` output encoding. It is UTF-16LE by default and UTF-8 when `WSL_UTF8=1`. Resolved in code: the decoder detects NUL bytes, and fixtures cover both encodings.
- Git Bash (MSYS) path conversion of the command string handed to `crew_wsl.py run`. It happens when bash launches native python, before crew_wsl sees the string. Resolved by the win-repo-2 run, with the command passed as one argument. If conversion mangles it there, the docs name `MSYS_NO_PATHCONV=1` for that one call, and the PR states the measured behaviour.
- A distro missing the job's tool (graphify, pytest) or `python3`. Resolved by design. `run` checks the first word with `command -v` inside WSL before routing. If it is missing, `auto` runs native and says why, and `wsl` refuses with exit 3.
- Git from inside WSL on a Windows-drive checkout (index stat churn, filemode, autocrlf). Accepted as risk and stated in `platform.md`. `auto` does not route a Windows-drive repo unless it has been measured, and crew's own record-writing jobs are excluded.
- Measurements on `dadeush-lenovo` and `dadeush-desktop`. Accepted as not measured by this ticket. Only win-repo-2 (`dadeush-legion`) is measured, and the PR says so.
- T-0075, in progress, may land first with `enum_values` in `crew_config.py`. Resolved at implement: re-grep origin/main. If `enum_values` exists, register `wslRouting.mode` with `("auto", "wsl", "native")` there too. Either way, `crew_wsl.mode()` treats an unrecognised value as `native` and names it.

## Touch
- `plugin/crew/hooks/scripts/crew_wsl.py` - new: host_os, to_wsl_path, decode, probe, cache, decide, run, measure, status_line
- `plugin/crew/hooks/scripts/crew_config.py` - wslRouting block on both layers
- `plugin/crew/hooks/scripts/crew_status.py` - shell line on Windows only
- `plugin/crew/templates/config.template.json`
- `plugin/crew/templates/global.template.json`
- `plugin/crew/tests/test_crew_wsl.py` - new
- `plugin/crew/tests/test_crew_config.py`
- `plugin/crew/tests/test_status.py`
- `plugin/crew/tests/sabotage_wsl.py` - new
- `plugin/crew/tests/sabotage.py` - register WSL_MUTATIONS
- `plugin/crew/commands/status.md`
- `plugin/crew/commands/config.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/skills/crew-setup/platform.md`
- `plugin/crew/skills/crew-setup/phases.md`
- `plugin/crew/skills/crew-setup/global-config.md`
- `plugin/crew/skills/crew-execute/SKILL.md`
- `plugin/crew/skills/crew-graph/SKILL.md`
- `plugin/crew/README.md`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md` - re-measured Markdown line total
- `plugin/crew/.budget-allowance.json` - only if a touched command file crosses its line budget
- `plugin/PLUGINS.md`
- `docs/guides/crew/**` - src/*.md plus the rebuilt HTML, DOCX and PDF
- `.crew/codemap/**`
- `.claude/rules/**` - regenerated from the codemap by crew_instructions.py
- `docs/diagrams/**`
- `.crew/verify.json`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`

## Acceptance checks
- [ ] Config key on both layers. `test_crew_config.py::test_wsl_routing_is_on_both_layers`: `wslRouting.mode == "auto"` and `wslRouting.distro is None` in `default_config()` and in `default_global_config()`. The existing `test_every_global_key_is_a_real_repo_config_key` and both template byte-equality tests stay green with the updated templates. (rule 7)
- [ ] Path translator. `test_crew_wsl.py::test_to_wsl_path`, parametrised:
  - `C:\repos\x` -> `/mnt/c/repos/x`
  - `D:/a b/c` -> `/mnt/d/a b/c`
  - Git Bash `/c/repos/x` -> `/mnt/c/repos/x`
  - `\\wsl$\Ubuntu\home\u\r` and `\\wsl.localhost\Ubuntu\home\u\r` -> `/home/u/r`

  `test_to_wsl_path_refuses`: a `\\wsl$` path for another distro, a plain `\\server\share` UNC, and a relative path each return None with a reason. (new rule)
- [ ] Probe states, fixture-driven through an injected runner. `test_probe_classifies`, parametrised over the states `usable`, `not-installed` (no `wsl.exe`), `no-distro` (UTF-16LE "no installed distributions"), `wsl1-only`, `no-python3`, `broken` (non-zero exit or timeout, error quoted verbatim) and `unknown` (the runner itself raised). `test_probe_decodes_utf16_and_utf8`. `test_probe_failure_is_unknown_not_absent`: a runner that raises never yields `not-installed`. `test_probe_never_installs`: no runner call contains `--install`, `--update` or `--set-default-version`. (new rule)
- [ ] Repo location is classified from Windows. `test_repo_location`: a drive path is `windows-drive`, and `\\wsl$`/`\\wsl.localhost` paths are `wsl-fs`. `test_decide` covers every (`mode` x probe state x location x measured) combination:
  - `native` always runs native.
  - `auto` routes to WSL only for `usable` plus `wsl-fs`, or for `usable` plus `windows-drive` with a cached measurement showing WSL faster. Anything else runs native with a reason naming the state.
  - `wsl` with anything but `usable` refuses (exit 3) and never falls back silently.
  - An unrecognised mode runs native and names the value.

  (new rule)
- [ ] Nothing changes off Windows. `test_off_windows_is_inert`, parametrised over `linux`, `macos` and `linux` inside WSL:
  - `probe` runs no subprocess (the runner asserts it is never called).
  - `decide` returns native with no message.
  - `run -- <cmd>` produces stdout, stderr and an exit code byte-identical to `bash -c <cmd>`, run for real.
  - `status_line` returns None.

  (new rule)
- [ ] `run` wiring. `test_run_argv_for_wsl` builds `["wsl.exe", "-d", distro, "--cd", <wsl path>, "-e", "bash", "-lc", cmd]`, with the command string passed unchanged. `test_run_passes_exit_code_through` covers 0, 1 and 7. `test_run_prints_one_route_line_to_stderr`. `test_run_preflight_missing_tool`: in `auto` a missing first word in WSL runs native with the reason, and in `wsl` it exits 3. (new rule)
- [ ] Cache and measure. `test_cache_write_is_atomic_and_lf`: a temp file then `os.replace`, `newline="\n"`, and the original is intact when the payload raises. `test_cache_is_machine_local`: the path is beside `crew_state.GLOBAL_CONFIG_PATH` and never under the repo. `test_measure_reports_both_sides` covers 50 forks and 200 writes per side, from an injected timer, with host and date. (new rule)
- [ ] Status. The `shell` line appears only on Windows. `test_status.py::test_status_has_no_shell_line_off_windows`: output on Linux is byte-identical with and without a cache file present. `test_status_shell_line_on_windows`, parametrised over `usable`/`wsl`, `not-installed` (the line names `wsl --install -d Ubuntu`, elevated, reboot), `unknown` ("never probed - run /crew:config") and `broken`. The existing `test_status_is_read_only` and `test_status_output_fits_forty_lines_on_a_busy_repo` stay green, with the Windows line included. (new rule)
- [ ] Hooks unchanged. `git diff --exit-code origin/main -- plugin/crew/hooks/hooks.json 'plugin/crew/hooks/scripts/*.sh' 'plugin/crew/hooks/scripts/*.ps1' plugin/crew/hooks/scripts/crew_platform.py plugin/crew/hooks/scripts/verify-gate.sh plugin/crew/skills/crew-setup/scripts/resolve-tools.sh` exits 0 at the final head.
- [ ] Sabotage. `plugin/crew/tests/sabotage_wsl.py` `WSL_MUTATIONS` is registered in `sabotage.py`, and each entry goes red on its named test:
  - `decide` routes to WSL on a Linux host
  - mode `wsl` silently falls back to native
  - a raising probe reports `not-installed`
  - the UTF-16 decode is removed
  - `to_wsl_path` accepts another distro's `\\wsl$` path
  - `status_line` prints on Linux
  - `run` drops the exit code

  `python3 plugin/crew/tests/sabotage.py` (full, via heavy-run) reports all red for real. (rule 9)
- [ ] Docs, per the owner rule. Every Touch doc describes the probe, the route, the explicit fallback, the in-WSL clone offer (with the measured numbers) and the install recommendation:
  - `platform.md` has a "Routing heavy jobs through WSL" section, with the measured table and host/date.
  - `phases.md` Phase 0 runs `crew_wsl.py probe --write` and `measure` on Windows.
  - `status.md` has the `shell` row.
  - `CONFIG.md` has the `wslRouting.*` rows.

  `(cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py)` passes (rule 12). `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` passes (rule 24). `docs/guides/crew/src/build.py` has been re-run and its outputs committed.
- [ ] Gate. `.crew/verify.json` gains a rule for `crew_wsl.py`, `test_crew_wsl.py`, `sabotage_wsl.py` and `crew_status.py`/`test_status.py`, with a measured `seconds`. The crew version is bumped in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md:14`, with a CHANGELOG entry. `python3 scripts/check-marketplace.py` exits 0 (rule 0).
- [ ] Native Windows, by win-repo-2 on `dadeush-legion` (owner-run, not CI):
  - `crew_wsl.py probe --json` reports the real state.
  - `measure` reports forks and writes for Git Bash and WSL, against the repo on a Windows drive and inside WSL.
  - `run -- python3 -m pytest plugin/crew/tests/test_crew_wsl.py -q` routes as `decide` said and passes.
  - The numbers are recorded in `platform.md` and the PR body. The PR says plainly that the two other Windows hosts were not measured.
