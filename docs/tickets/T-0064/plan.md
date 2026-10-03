# T-0064 plan            spec: .work/tickets/T-0064/spec.md

Work in a fresh worktree, `/repos/personal/uca-t-0064` on branch `T-0064-build` off origin/main. The anchors are origin/main `502cb137` (crew 1.0.42). Re-grep each quoted string before its step. If a line has moved (T-0063 edits `crew_refresh_check.py`, T-0070 edits `crew_status.py`), re-anchor from the new line and keep the test unchanged. Every step writes its must-refuse test and its must-allow neighbour first and watches both fail for the stated reason. Then it implements, then adds sabotage mutations that must go red. Heavy runs (pytest, `sabotage.py`, graphify) are serial under `flock /root/crew-tmp/heavy.lock` with `TMPDIR=/root/crew-tmp/t-0064`. No second opinion is needed. The design is one set difference (denylisted files minus files `.graphifyignore` excludes), computed by git's own matcher, plus three callers. Step 1 comes first. Steps 2-4 depend on it and are independent of each other. Steps 5 and 6 run last.

### Step 1: `crew_graph_ignore.py` - the denylist, the coverage set, `--check` and `--write`
Files: plugin/crew/hooks/scripts/crew_graph_ignore.py, plugin/crew/tests/test_graph_ignore.py, plugin/crew/tests/sabotage_refresh.py, .crew/verify.json
Test: python3 -m pytest plugin/crew/tests/test_graph_ignore.py -q -p no:cacheprovider
Risk: high. A false "covered" is the defect this ticket exists to close. The unknown-never-covered test and the `.gitignore`-is-not-coverage test bound it.
- [ ] Resolve the `Read(/x)` anchoring unknown first. Read the Claude Code permissions documentation for the path forms of `Read(...)` rules (`//abs`, `~/home`, `/x`, `./x`, a bare `x`). Record the answer in the module docstring with its source URL. If the documentation is unclear, emit `/x` under both readings, as the spec says.
- [ ] Tests first, in `plugin/crew/tests/test_graph_ignore.py`. Fixtures are git repos under `tmp_path`, made with `crew_fixtures.make_repo` where it fits, and every write uses `newline="\n"`:
  - `test_uncovered_denylisted_file_is_named`: a tracked `config/env.php`, a `.claude/secrets-denylist` holding `config/`, and no `.graphifyignore`. `main(["--root", root, "--check"])` returns 1, and stdout names `config/env.php`.
  - `test_covered_denylisted_file_passes`: the same fixture after `main([... "--write"])`. `--check` returns 0.
  - `test_each_source_contributes`, parametrised over the built-in (a tracked `.env`), `.claude/secrets-denylist` (`secrets/`), `settings.json` `{"permissions": {"deny": ["Read(./secrets/**)"]}}` and the same in `settings.local.json`. Each source alone makes its file uncovered (exit 1).
  - `test_env_example_is_not_denylisted`: a tracked `.env.example` alone gives exit 0.
  - `test_gitignore_alone_does_not_cover_a_tracked_file`: a tracked `.env` with `.env` in `.gitignore` only gives exit 1.
  - `test_negation_in_graphifyignore_uncovers`: `.graphifyignore` holding `config/` then `!config/env.php` gives exit 1, naming `config/env.php`.
  - `test_untracked_and_ignored_files_are_candidates`: an untracked `.env` that `.gitignore` ignores, with no `.graphifyignore`, gives exit 1. The listing is `--cached --others` with no `--exclude-standard`, so `graphify --no-gitignore` is covered too.
  - `test_out_of_repo_read_rules_are_skipped`: `Read(~/.ssh/**)` and `Read(//etc/passwd)` alone give exit 0, and `--json` lists them under `skipped`.
  - `test_unknowns_never_read_as_covered`, parametrised: unparseable `settings.json`, `.graphifyignore` unreadable (chmod 000, skipped under root and on Windows, with the reason), a nested `sub/.graphifyignore`, a deny-all `Read` / `Read(*)` / `Read(**)` rule, and git missing (the `git` argument injected as a nonexistent binary). Each returns 2 with a reason on stdout, never 0.
  - `test_write_is_idempotent_and_additive`: a pre-existing `.graphifyignore` with comments and `vendor/`. `--write` appends one block headed `# crew: secrets denylist (crew_graph_ignore.py --write)`, holding only the missing patterns, leaves the original bytes as a prefix and is LF-only (checked with `b"\r" not in data`). A second `--write` leaves the file byte-identical.
  - `test_write_never_truncates_on_a_failed_build`: monkeypatch the block builder to raise. `--write` exits non-zero and `.graphifyignore` is byte-identical to before (the root CLAUDE.md `open(p, "w")` landmine).
  - `test_check_is_read_only`: an mtime snapshot of every file in the fixture around `--check` shows no change. The only scratch space is a `tempfile.TemporaryDirectory` outside the repo.
  - Run them and watch them fail (ModuleNotFoundError).
- [ ] Implement `plugin/crew/hooks/scripts/crew_graph_ignore.py`, stdlib only, with `sys.dont_write_bytecode = True` like `crew_status.py`:
  - `BUILTIN_PATTERNS`: `.env`, `.env.*`, `!.env.example`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`.
  - `denylist(root)` returns `(patterns, sources, skipped, unknown)`. It reads the built-ins, `.claude/secrets-denylist` (optional, gitignore syntax) and `permissions.deny` `Read(...)` entries from `.claude/settings.json` and `.claude/settings.local.json`, translated to root-anchored gitignore patterns. It never raises: each failure lands in `unknown`.
  - `candidates(root, git="git")` runs `git -c core.fsmonitor=false ls-files -z --cached --others` with `GIT_OPTIONAL_LOCKS=0` and returns the NUL-split paths, or None with a reason. It also names any `.graphifyignore` other than the root one.
  - `_ignored(paths, patterns, git)`: `git init -q` a scratch repo in a `TemporaryDirectory`, write the patterns to its `.git/info/exclude` (LF), and run `git -C <scratch> check-ignore --no-index --stdin -z -v -n` with the paths on stdin. Parse the NUL records. A path is ignored when its last matching pattern does not start with `!`. So negation, directory rules and anchoring follow git's rules, not a re-implementation.
  - `coverage(root, git="git")` returns `{"status": "covered"|"uncovered"|"unknown", "uncovered": [...], "reason", "sources", "skipped"}`, where uncovered = `_ignored(candidates, denylist)` minus `_ignored(candidates, root .graphifyignore lines)`. Any unknown from the steps above makes the status `unknown`.
  - `write(root, git="git")` appends the missing patterns under the marked block. It builds the full text into a variable first, writes a temp file in the same directory with `newline="\n"`, then calls `os.replace`. It returns the patterns added.
  - CLI: `--root`, `--check` (exit 0 covered, 1 uncovered, 2 unknown), `--write` (exit 0, or 2 when the denylist itself is unknown), `--json`. The text output names at most 10 paths, then `(+N more)`. It prints paths only, never file content.
- [ ] Add a `.crew/verify.json` rule: paths `plugin/crew/hooks/scripts/crew_graph_ignore.py`, `plugin/crew/tests/test_graph_ignore*.py`. Command: `python3 -m pytest plugin/crew/tests/test_graph_ignore.py plugin/crew/tests/test_graph_ignore_graphify.py plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_status.py -q`.
- [ ] Sabotage, appended to `REFRESH_MUTATIONS` in `plugin/crew/tests/sabotage_refresh.py` with a new target `IGNORE`:
  - "gitignore counts as coverage" reads `.gitignore` into the coverage patterns (red on `tests/test_graph_ignore.py::test_gitignore_alone_does_not_cover_a_tracked_file`).
  - "an unknown reads as covered" returns `covered` where the status would be `unknown` (red on `test_unknowns_never_read_as_covered`).
  - "negation ignored" treats any match as ignored (red on `test_negation_in_graphifyignore_uncovers`).
  - "write truncates first" opens the target in `w` mode before building the text (red on `test_write_never_truncates_on_a_failed_build`).
  - "a source is dropped" skips `settings.local.json` (red on `test_each_source_contributes`).
- [ ] Run the Test command. It must be all green.

### Step 2: the real-graphify fixture test
Files: plugin/crew/tests/test_graph_ignore_graphify.py
Test: flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0064 python3 -m pytest plugin/crew/tests/test_graph_ignore_graphify.py -q -p no:cacheprovider
Risk: med. If graphify changes how it records nodes, the canary may never appear, even without the ignore. The control test catches that and fails loudly instead of passing vacuously.
- [ ] `pytestmark = pytest.mark.skipif(shutil.which("graphify") is None, reason="graphify not on PATH - the denylist-never-reaches-the-graph proof DID NOT RUN")`.
- [ ] Fixture: a git repo with `app.py` (`def main(): pass`), `config/secrets.py` (`def canary_t0064_secret(): return 1`), `init.php` (`<?php function canary_t0064_php() {}`), `keys/k.pem`, and `.claude/secrets-denylist` holding `config/`, `/init.php` and `keys/`. Commit it.
- [ ] `test_canary_reaches_the_graph_without_the_ignore` (the control), parametrised over `["graphify", "update", "."]` and `["graphify", ".", "--no-viz", "--code-only"]`. With no `.graphifyignore`, both canaries appear in some file under `graphify-out/`. If they do not, the test fails with "graphify no longer records the canary; the leak test below proves nothing until the canary is changed".
- [ ] `test_denylisted_symbols_never_reach_the_graph`, parametrised the same way. Run `crew_graph_ignore.py --write`, assert `--check` exits 0, delete `graphify-out/`, then build. Neither canary nor `config/secrets.py` nor `init.php` appears in any file under `graphify-out/`, and `app.py`'s `main` does, so a build that produced nothing cannot pass.
- [ ] Each graphify call gets a timeout of 300 s and runs with `cwd=` the fixture. The fixture sets `HOME` to a temp directory so graphify writes no user state.
- [ ] Run the Test command. It must be all green, or skipped with the reason above, and the report says which.

### Step 3: the refresh check refuses an uncovered build
Files: plugin/crew/hooks/scripts/crew_refresh_check.py, plugin/crew/tests/test_refresh_check.py, plugin/crew/tests/sabotage_refresh.py
Test: python3 -m pytest plugin/crew/tests/test_refresh_check.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py plugin/crew/tests/test_completion_audit_refresh_artifacts.py plugin/crew/tests/test_crew_autopilot.py -q -p no:cacheprovider
Risk: high. A refusal that lets the command through is the leak. One that fires on a covered repo stops every ticket with a graph.
- [ ] Tests first, reusing `test_refresh_check.py`'s existing stale-graph fixture (the one behind `test_graph_behind_is_stale`, `plugin/crew/tests/test_refresh_check.py:196`):
  - `test_graph_refresh_refused_while_denylisted_path_uncovered`: add a tracked `.env`. The graph artifact is `unknown`, with `refreshable` False and a reason containing `.env` and `crew_graph_ignore.py --write`. `main` returns 1, and the rendered line contains "stop - a refresh cannot settle this".
  - `test_graph_refresh_named_once_covered`: the same repo with `.env` in `.graphifyignore` is `stale`, refreshable, with the command `graphify update .`.
  - `test_graph_refresh_unknown_coverage_stops`: an unparseable `.claude/settings.json` makes the graph artifact `unknown`, non-refreshable, with the reason "denylist coverage unknown: …".
  - `test_autopilot_does_not_settle_a_refused_graph`: `crew_autopilot._settles` (`plugin/crew/hooks/scripts/crew_autopilot.py:247`) is False on the refused artifact. It asserts the existing behaviour, and no autopilot code changes.
  - Watch the first and third fail (the entry is `stale` today).
- [ ] Implement in `_graph` (`plugin/crew/hooks/scripts/crew_refresh_check.py:489-506`). After `if not code: return None` and before the `which("graphify")` check, call `crew_graph_ignore.coverage(root)`. On `uncovered`, return `_entry("graph", graph_out, UNKNOWN, "graphify would read N secrets-denylisted path(s) .graphifyignore does not exclude: <few>; run crew_graph_ignore.py --write, and if a graph was built before, see crew-graph SKILL 'Tainted graph'", command, refreshable=False)`. On `unknown`, return the same shape with "denylist coverage unknown: <reason>". Extend the module docstring's `graph` paragraph (`:30-35`) by one sentence.
- [ ] Sabotage, in `sabotage_refresh.py`:
  - "the refresh check skips the coverage call" (red on `tests/test_refresh_check.py::test_graph_refresh_refused_while_denylisted_path_uncovered`).
  - "a refused graph stays refreshable" flips `refreshable=False` to True (red on `test_autopilot_does_not_settle_a_refused_graph`).
  - "unknown coverage passes" (red on `test_graph_refresh_unknown_coverage_stops`).
- [ ] Run the Test command. It must be all green.

### Step 4: `/crew:status` flags the gap
Files: plugin/crew/hooks/scripts/crew_status.py, plugin/crew/tests/test_status.py, plugin/crew/tests/sabotage_refresh.py
Test: python3 -m pytest plugin/crew/tests/test_status.py -q -p no:cacheprovider
Risk: low. It is one line in a 40-line budget. Read-only is already pinned by two tests.
- [ ] Tests first:
  - `test_status_flags_uncovered_denylisted_path`: a tracked `.env` and no `.graphifyignore`. The output has one line starting `graph-ignore  UNCOVERED` that names `.env` and `crew_graph_ignore.py --write`.
  - `test_status_graph_ignore_ok_and_unknown`, parametrised. A covered repo gives `graph-ignore  ok`. An unparseable `settings.json` gives `graph-ignore  unknown - <reason>`.
  - The existing `test_status_is_read_only`, `test_status_never_runs_a_configured_fsmonitor_hook` and `test_status_output_fits_forty_lines_on_a_busy_repo` (`plugin/crew/tests/test_status.py:57`, `:154`, `:66`) stay green unchanged.
- [ ] Implement `_graph_ignore_line(root)` in `crew_status.py`, beside `_codemap_line` (`plugin/crew/hooks/scripts/crew_status.py:141`). It calls `crew_graph_ignore.coverage(root)`, which already runs git with `core.fsmonitor=false` and `GIT_OPTIONAL_LOCKS=0`. Append the line in `collect` after the codemap line (`:198`). Update the docstring's list of what it reads.
- [ ] Sabotage, in `sabotage_refresh.py`: "status hides an uncovered path" makes the line always `ok` (red on `tests/test_status.py::test_status_flags_uncovered_denylisted_path`).
- [ ] Run the Test command. It must be all green.

### Step 5: docs, version and changelog
Files: plugin/crew/skills/crew-graph/SKILL.md, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/commands/onboard.md, plugin/crew/commands/upgrade.md, plugin/crew/commands/status.md, plugin/crew/README.md, plugin/PLUGINS.md, docs/guides/crew/**, .crew/codemap/**, docs/diagrams/**, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json
Test: (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py) && python3 scripts/check-marketplace.py && python3 scripts/_test/self-claims.py && python3 scripts/sync-updates.py --check
Risk: med. Stale docs are the owner's standing complaint (root CLAUDE.md, 2026-09-26 rule), and a missed version bump strands every installed copy.
- [ ] `plugin/crew/skills/crew-graph/SKILL.md`:
  - **Build** (`:41-65`) opens with `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_graph_ignore.py --root . --check`. On exit 1, stop, name the paths and offer `--write`. On exit 2, stop and report the reason. Never build around it.
  - A new `## Secrets denylist` section lists the three sources, says `.gitignore` never protects a tracked file from graphify (graphify 0.9.65 `detect.py:1598-1623`), and says the root `.graphifyignore` is the only file checked.
  - A new `## Tainted graph` section: delete the `graph.out` directory, run `--write`, then rebuild. If the output is tracked, commit the rebuild. Anything built before the fix is treated as holding secret-derived text until then.
  - **Freshness** (`:81-88`) adds that the post-commit hook bypasses crew, so `/crew:status`'s `graph-ignore` line is the warning.
- [ ] `plugin/crew/skills/crew-setup/SKILL.md`: a new `## 3e. .graphifyignore from the secrets denylist` after 3c (`:358-414`) runs `crew_graph_ignore.py --root . --write` and reports what it added. It names `.claude/secrets-denylist` as the place for repo-specific paths.
- [ ] `plugin/crew/commands/onboard.md` step 1 (`:11-22`) and `plugin/crew/commands/upgrade.md` step 3 (`:61-73`) each gain one clause: "after that skill's denylist check passes".
- [ ] `plugin/crew/commands/status.md`: a `graph-ignore` row in the line table (`:25-37`).
- [ ] `plugin/crew/README.md`: a `crew_graph_ignore.py` row beside the `crew_refresh_check.py` row (`:762`), and that row gains "refuses the graph while a denylisted path is uncovered".
- [ ] `plugin/PLUGINS.md` "The code graph" (`:68-80`): one sentence on the denylist check.
- [ ] `docs/guides/crew/src/troubleshooting.md`: a `## Graph refresh refused: secrets-denylisted path` section (the message, `--write`, tainted-graph runbook). Rebuild with `python3 docs/guides/crew/src/build.py` and commit the regenerated `crew-1.0-troubleshooting.{html,docx,pdf}`. If the build cannot run here, say so and name what did not rebuild.
- [ ] `.crew/codemap/crew.md`: the refresh-check section (`:609-637`) gains the coverage gate and a `crew_graph_ignore.py` entry with `path:line` anchors. Run `/crew:onboard --refresh crew` semantics by hand and advance the `anchor:`.
- [ ] `docs/diagrams/process-crew-lifecycle.mmd`: node `rf1` (`:130`) notes the graph refusal. Re-render per `/crew:diagram refresh`, and advance the provenance header.
- [ ] Version: bump crew from 1.0.42 to the next patch free on origin/main at implement time, in both `plugin/crew/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, with a `CHANGELOG.md` entry.
- [ ] Run the Test command. It must be all green.

### Step 6: this repo's own check, the full gates and sabotage
Files: .graphifyignore
Test: python3 plugin/crew/hooks/scripts/crew_graph_ignore.py --root . --check && flock /root/crew-tmp/heavy.lock env TMPDIR=/root/crew-tmp/t-0064 python3 plugin/crew/tests/sabotage.py
Risk: med. A new mutation that stays green means its test does not test what it names.
- [ ] Run `crew_graph_ignore.py --root . --check` in the worktree. If it reports an uncovered file, run `--write` and commit `.graphifyignore`, and say in the PR that the next `graphify update .` rebuild excludes it. Otherwise create no file and record "covered, nothing denylisted" in the PR.
- [ ] Run every `.crew/verify.json` rule reached by the diff: the new rule, the refresh-check rule, the prompts rule, the docs rule, `check-marketplace.py`, and ruff and pylint over `**/*.py`. Run `python3 -m pytest plugin/crew/tests/ -q` once under the heavy lock.
- [ ] Run `sabotage.py`. Every new mutation from Steps 1, 3 and 4 is RED on its named test, and no existing mutation changed colour. Quote any failure verbatim.
- [ ] PR body: the Docs list (every file from Step 5), what was not verified (Windows, and graphify versions other than 0.9.65), and the cross-reference that TSS's follow-up is to write `.claude/secrets-denylist` from its guard's `PROTECTED` list.
