# L-0685 gizmoduck bootstrap.sh without sudo, and a CI and containers guide (external report item 9)          status: spec   risk: med
Split from T-0108 on 2026-10-04. Written against origin/main `155fe6d8` (gizmoduck 0.5.6). Filed as L-0685. Its direction is `direction.md` beside this file. The owner was not available; defaults taken are under "Open questions for the owner".

## Intent
`bootstrap.sh` can set gizmoduck up in a CI job or a container. As root it runs without `sudo`. With `--user` it installs every tool that needs no package manager into the gizmoduck tool home and names the ones it had to skip. `--dry-run` prints the plan and changes nothing. The script exits non-zero when a tool failed, so a pipeline can gate on it. The README gains a "CI and containers" section that says what to bake into an image and states plainly that gizmoduck runs inside a container but never drives Docker itself.

## Exclusions
- No Python change. `gizmoduck.py`, `routine.py` and `scanners/**` are untouched; finding tools in the tool home is L-0684 and must already be on main.
- `bootstrap.ps1` is untouched: it already installs per user without admin rights (`plugin/gizmoduck/bootstrap.ps1:15`, `:44`).
- No Docker image, no Dockerfile shipped, no `docker run` anywhere. The standing decision at `scanners/zap.py:3-8` and `bootstrap.sh:179-183` stays, and the comment telling the next reader not to "fix" it stays.
- Debian and Ubuntu only for the system mode, as today. No `apk`, `dnf` or `brew` support.
- `--user` does not install anything that needs a package manager: nmap, wkhtmltopdf, a Java runtime, perl. It reports them; it does not try.
- No version pinning of the tools and no checksum verification of downloads. Both are worth having and both are bigger than this ticket; one `TODO.md` bullet each.
- The Nuclei template download stays a hard failure (`bootstrap.sh:76-88`).
- `pip3 install --user` for checkov and semgrep stays as it is (`:117-126`); see Unknowns.
- No change to `plugin/crew/**`; PR body says `Docs: none for crew - gizmoduck only`. No path in `HARNESS` or `SEAM` (`scripts/check-tooling-pr.py:58-95`). No hook, no new command, no registered entry, no count changes.
- The guides under `docs/guides/gizmoduck/` have no source in the repo and are not rebuilt; one `TODO.md` bullet.

## Design
- Arguments: `--user`, `--dry-run`, `-h` / `--help`. Anything else: usage on stderr, exit 2, nothing done.
- Privilege, decided once at the top into one variable:
  - `--user`: no elevation anywhere.
  - otherwise, `id -u` is 0: no `sudo` prefix.
  - otherwise, `sudo` on PATH: `sudo`, with `-n` added when stdin is not a terminal so a password prompt cannot hang a pipeline.
  - otherwise: exit 2 with one message saying there is no root and no `sudo`, and to re-run with `--user`. It does not switch modes on its own.
- apt calls run with `DEBIAN_FRONTEND=noninteractive`.
- Tool home in `--user` mode: `$GIZMODUCK_HOME`, else `$XDG_DATA_HOME/gizmoduck`, else `$HOME/.local/share/gizmoduck`. This is the same rule as `scanners/base.py` `tool_home()` from L-0684, and a test holds the two together.
- `--user` destinations: nuclei binary in `<home>/bin`; trivy through its install script with `-b <home>/bin`; testssl.sh cloned to `<home>/testssl.sh` with a link in `<home>/bin`; sqlmap cloned to `<home>/sqlmap` with the wrapper script in `<home>/bin`; dependency-check unzipped to `<home>/dependency-check` with a link in `<home>/bin`; ZAP unzipped under `<home>/zap` with `zap.sh` linked in `<home>/bin`; nikto cloned to `<home>/nikto` (found by L-0684 at `<home>/nikto/program/nikto.pl`); checkov and semgrep as today. Downloads are staged in `<home>/.download`, not `/tmp`, for the reason the script already gives at `:57-62`.
- `--user` and a tool that needs a package: if the command is already on PATH it is reported as present; otherwise it goes on a SKIPPED list, separate from FAILED. ZAP and dependency-check need Java; without a suitable `java` they are FAILED with a message naming the package to add to the image, not installed half-way.
- `--user` checks `curl`, `unzip`, `git` and `python3` first. A missing one is exit 2 before anything is downloaded, naming every missing command.
- GitHub release lookups go through one function replacing the three copies. It sends `Authorization: Bearer $GITHUB_TOKEN` only when that variable is set, and never prints it.
- `--dry-run`: one `plan:` line per tool with its destination and how it would be installed (`as root`, `via sudo`, `user`, or `SKIPPED (needs a package manager)`), the resolved tool home, then exit 0. No network call, no file written, no directory created.
- Exit status: 0 when nothing failed; 1 when any tool failed or the template download failed; 2 for a usage or precondition error. When tools were skipped and none failed, the status is 0 and the last line starts `GIZMODUCK_BOOTSTRAP_SKIPPED:` followed by the names, the same shape as `GIZMODUCK_ROUTINE_INCOMPLETE` (`gizmoduck.py:736`).
- Flag as a behaviour change in the CHANGELOG: `bootstrap.sh` used to exit 0 after a partial install; it now exits 1.
- The file stays LF. It is edited as text, never rewritten through `pathlib.write_text` without `newline="\n"`.

## Evidence
All at origin/main `155fe6d8`, read 2026-10-04.
- `plugin/gizmoduck/bootstrap.sh:13` - `set -uo pipefail`, deliberately no `-e`; `:21-30` `try_install` collects failures in `FAILED`.
- `plugin/gizmoduck/bootstrap.sh:32-37` - prerequisites: `sudo apt-get` when `apt-get` exists, silently nothing otherwise.
- `plugin/gizmoduck/bootstrap.sh:63-71` - Nuclei staged in `/opt`, moved to `/usr/local/bin`, all through `sudo`.
- `plugin/gizmoduck/bootstrap.sh:90-96` - nmap and nikto are bare `sudo apt-get install`.
- `plugin/gizmoduck/bootstrap.sh:98-108`, `:152-168` - testssl.sh and sqlmap cloned into `/opt` through `sudo`.
- `plugin/gizmoduck/bootstrap.sh:110-115` - trivy's install script piped to `sudo sh -s -- -b /usr/local/bin`; the `-b` destination is already a parameter.
- `plugin/gizmoduck/bootstrap.sh:117-126` - checkov and semgrep through `pip3 install --user`, no `sudo`.
- `plugin/gizmoduck/bootstrap.sh:128-150`, `:170-203` - dependency-check and ZAP unzipped into `/opt` through `sudo`; Java installed through apt when missing (`:149`, `:175-177`).
- `plugin/gizmoduck/bootstrap.sh:48-49`, `:130-131`, `:185-186` - three unauthenticated calls to the GitHub releases API, the same four-command pipeline each time.
- `plugin/gizmoduck/bootstrap.sh:246-254` - failures are printed; `:256-268` the script ends on a `cat`, so its exit status is 0 regardless.
- `plugin/gizmoduck/bootstrap.sh:179-183` and `plugin/gizmoduck/scripts/scanners/zap.py:3-8` - Docker deliberately not used.
- `plugin/gizmoduck/README.md:23-28` - the whole install section; nothing on CI, containers, root or `sudo`.
- `plugin/gizmoduck/README.md:95-97` - `routine` is described as the CLI for scheduled and headless runs.
- `plugin/gizmoduck/bootstrap.ps1:15`, `:44` - Windows installs under the user's own `Programs` directory with no admin.
- `plugin/gizmoduck/scripts/_test/` - no test of `bootstrap.sh` exists (file listing at origin/main).
- `.crew/verify.json:263-267` - the rule for `plugin/gizmoduck/**` runs the gizmoduck pytest suite, so a pytest-driven bootstrap test is covered by the existing rule.
- `.github/workflows/pytest-crew.yml:32`, `:123` - the gizmoduck suite runs on Linux runners, where `bash` exists.
- `plugin/gizmoduck/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:230`, `plugin/PLUGINS.md:449` - the three version sites.

## Unknowns
- **`pip3 install --user` on an externally managed Python** (Ubuntu 24.04, the platform the script names at `:3-4`) may be refused by pip. Not verified here. Resolve at implement by reading what the step prints in a clean Ubuntu 24.04 container. If it is refused today on main, that is an existing defect: record it in `TODO.md` and in the README section's list of what to pre-install; do not widen this ticket to fix it without the owner.
- **Upstream layouts.** nikto's repository keeps `program/nikto.pl` (the Windows installer relies on the same path); the ZAP Crossplatform zip extracts to `ZAP_<version>/` (`bootstrap.sh:201`). Resolve at implement by listing one real download of each and quoting the listing in the PR.
- **Does trivy's install script work unprivileged with `-b` into a user directory?** Expected yes, since `-b` is its documented destination flag. Resolve with one real `--user` run, by hand, in a throwaway container; quote the result.
- **A real end-to-end `--user` run cannot be part of the suite** (suites must not install anything). Accepted as risk, covered by the manual check below; say in the PR which manual runs were done and which were not.
- **Fake `id` and `sudo` on PATH in the tests.** The privilege decision must call `id -u` and `command -v sudo`, not read `$EUID`, or the tests cannot simulate root. Resolved by design.
- **Does a Windows leg ever collect the gizmoduck suite?** The workflow read here runs it on Linux. The new tests skip with a stated reason when `bash` is not found, so an unknown leg cannot fail on a missing tool.

## Touch
- `plugin/gizmoduck/bootstrap.sh`
- `plugin/gizmoduck/scripts/_test/test_bootstrap.py` - new
- `plugin/gizmoduck/README.md` - the install section and a new "CI and containers" section
- `plugin/gizmoduck/skills/gizmoduck/SKILL.md` - the bootstrap sentence names the two modes
- `plugin/gizmoduck/commands/doctor.md` - names the --user option beside bootstrap.sh
- `plugin/gizmoduck/docs/antivirus-exclusions.md` - only if it lists the Linux install paths; add the tool home beside them
- `plugin/gizmoduck/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `CHANGELOG.md`
- `TODO.md` - follow-up bullets: version pinning, download checksums, the gizmoduck guides
- `.crew/codemap/**` - re-anchor only, owner's standing rule
- `.claude/rules/**` - regenerated
- `graphify-out/**` - rebuilt by graphify update, committed as it leaves them

## Acceptance checks
Rule for every pytest line: `.crew/verify.json` `plugin/gizmoduck/**` (`python3 -m pytest plugin/gizmoduck/scripts/_test/ -q`). Every test runs the script only with `--dry-run` or into a refusal, with `HOME`, `GIZMODUCK_HOME` and `XDG_DATA_HOME` under `tmp_path` and a PATH made of a temp directory holding fakes (`id`, `sudo`, `curl`, `git`, `unzip`, `python3` as needed) plus the system `bash` and coreutils. The fake `curl`, `git` and `sudo` append to a log file; a test that expects no action asserts that log is empty. Nothing is installed and no network is reached.
- [ ] `bash -n plugin/gizmoduck/bootstrap.sh` exits 0.
- [ ] `file plugin/gizmoduck/bootstrap.sh` does not report CRLF line terminators.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/test_bootstrap.py -q` passes, with these tests by name:
  - `test_unknown_option_is_exit_2_and_does_nothing`
  - `test_help_exits_0_and_names_user_and_dry_run`
  - `test_dry_run_writes_nothing_and_calls_nothing` - `tmp_path` home is empty afterwards and the fakes' log is empty, in system mode and in `--user` mode.
  - `test_root_uses_no_sudo` - fake `id` prints 0; every `plan:` line says `as root`; no line mentions `sudo`.
  - `test_non_root_with_sudo_plans_via_sudo` - fake `id` prints 1000, fake `sudo` present.
  - `test_non_root_without_sudo_is_exit_2_and_points_at_user_mode` - the message contains `--user`; nothing is planned or run.
  - `test_sudo_is_non_interactive_without_a_terminal` - the planned prefix is `sudo -n` when stdin is not a terminal.
  - `test_user_mode_plans_every_tool_under_the_tool_home` - no `plan:` line names `/opt` or `/usr/local`.
  - `test_user_mode_tool_home_matches_base_tool_home` - parametrized over `GIZMODUCK_HOME` set, only `XDG_DATA_HOME` set, neither set; the path the script prints equals `scanners.base.tool_home()` in the same environment.
  - `test_user_mode_lists_package_only_tools_as_skipped` - with no `nmap` and no `wkhtmltopdf` on PATH, both are SKIPPED and neither is FAILED; with a fake `nmap` on PATH it is reported present.
  - `test_user_mode_missing_prerequisite_is_exit_2_naming_it` - parametrized over `curl`, `unzip`, `git`, `python3`.
  - `test_github_token_is_never_printed` - `GITHUB_TOKEN` set to a marker string; the marker is in neither stdout nor stderr of a `--dry-run`.
  - `test_script_exit_status_is_1_when_a_tool_failed` - drives the script's final summary with a pre-set failure (for example by sourcing it with a guard the implementer adds for this, or a stub install function) and asserts exit 1; and exit 0 with a last line starting `GIZMODUCK_BOOTSTRAP_SKIPPED:` when tools were only skipped.
  - Every test is skipped with a reason, not failed, when `bash` cannot be found.
- [ ] Sabotage, by hand, quoted in the PR: put an unconditional `sudo` back on one install step; `test_root_uses_no_sudo` and `test_user_mode_plans_every_tool_under_the_tool_home` go red. Restore; green. Then make `--dry-run` create the tool home; `test_dry_run_writes_nothing_and_calls_nothing` goes red.
- [ ] `python3 -m pytest plugin/gizmoduck/scripts/_test/ -q` passes whole.
- [ ] Manual, by hand, in a throwaway Ubuntu 24.04 container, quoted verbatim in the PR, or stated as not done: (a) as root with no `sudo` installed, `./bootstrap.sh` then `python3 scripts/gizmoduck.py doctor`; (b) as an unprivileged user, `./bootstrap.sh --user` then `doctor`, with the SKIPPED line and doctor's scanner listing. Never run either on the workstation or a CI runner's host.
- [ ] shellcheck: no new findings in `plugin/gizmoduck/bootstrap.sh` against the merge-base, using the command in `.crew/verify.json` (`uvx --from shellcheck-py==<the version pinned there> shellcheck`). If the tool is not available, say so; that is not a pass.
- [ ] `plugin/gizmoduck/README.md` has a "CI and containers" section covering: root in a container, `--user`, what is skipped and which packages to add to an image (nmap, a Java 17 runtime, perl, wkhtmltopdf), `GIZMODUCK_HOME` and the Nuclei template directory as cache paths, `GITHUB_TOKEN` and `NVD_API_KEY` supplied from the pipeline's secret store and never written into a manifest, the three exit statuses, `--dry-run`, and the Docker statement. `git grep -n -- "--user" -- plugin/gizmoduck/README.md` and `git grep -n "GIZMODUCK_BOOTSTRAP_SKIPPED" -- plugin/gizmoduck/README.md` both hit.
- [ ] The README names no real host, account, pipeline or organisation; examples use `example.com` and placeholders only.
- [ ] Version bumped in all three places one patch past what origin/main holds at push time, committed, then `python3 scripts/check-marketplace.py` passes.
- [ ] `CHANGELOG.md` has a heading entry naming the version, this ticket, and the exit-status change.
- [ ] ruff and pylint: no new findings against the merge-base for the new test file.
- [ ] `python3 scripts/check-tooling-pr.py` exits 0. Exit 77 means the check did not run; report that.

## Dependencies
Must land before this ticket:
- L-0684 - **not started** (spec written 2026-10-04): defines the tool home and makes `base.which` look in its `bin`. Without it a `--user` install is invisible to gizmoduck. `test_user_mode_tool_home_matches_base_tool_home` imports its `tool_home()`.
- T-0107 - **done** (merged as #273): the `routine` CLI the CI section points at.
- L-0599 - **done** (merged as #315, gizmoduck 0.5.6).

No hard dependency on T-0108 (direction; safe Nuclei defaults), but the CI section should mention the safe defaults if T-0108 has landed by then; merge origin/main first (merge, never rebase) and re-bump.

This ticket blocks: nothing.

## Size
About 150 production lines, all in `bootstrap.sh` (argument parsing 20, privilege decision 20, tool-home and destination variables 20, `--user` branches across nine install functions 60, release-lookup helper 10, dry-run and exit summary 20). No new parser, no state machine, no harness path.

## Open questions for the owner
Each has a default already taken; none blocks the build.
1. Not root and no `sudo`: exit 2 and point at `--user`. Alternative: switch to `--user` automatically and say so.
2. Exit 1 after a partial install, where the script used to exit 0. Alternative: keep 0 and add `--strict`.
3. Skipped-only is exit 0 with a `GIZMODUCK_BOOTSTRAP_SKIPPED:` last line. Alternative: a distinct non-zero status, as `routine` uses 4.
4. `GITHUB_TOKEN` is used for release lookups when present. Alternative: a gizmoduck-specific variable name.
5. If `pip3 install --user` turns out to be refused on Ubuntu 24.04, should `--user` create a virtual environment under the tool home for checkov and semgrep? Default taken: no, record it as a follow-up.

## Approval
Spec approved for cloud hand-off by the orchestrator under the owner's standing authority, 2026-10-04. Plan: to be written by the implementing session.
