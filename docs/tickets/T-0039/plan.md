# T-0039 plan            spec: .work/tickets/T-0039/spec.md

Anchors checked against `origin/main` at 502cb137 (crew 1.0.42). The owner's 2026-09-26 decision ("appy automatically") is folded in: every additive pattern is applied without asking; untracking and already-committed secrets are reported, never acted on. The optional second opinion is skipped: the design reuses git's own matcher (`git check-ignore`, `git ls-files -ci`) rather than re-implementing gitignore semantics, which is the part a second opinion would have probed. Single-family opinion.

## Design (settled; the steps below implement it)

One module, `plugin/crew/hooks/scripts/crew_gitignore.py`, standard library only, three subcommands:

- `check --root R [--json]` - read-only. Prints one line per finding: `detected <lang> (<evidence>)`, `missing <pattern> - <reason>`, `covered <pattern>`, `tracked <pattern> matches N tracked file(s): <first 4>`, `conflict <pattern> would override <negation> at <file>:<line> - not added`, `needs-owner <path> is tracked and secret-shaped - rotate and decide on history`, `unknown <reason>`. Exit 0 current, 1 additions pending, 2 usage, 3 owner decision needed (a tracked secret), 4 could not tell.
- `apply --root R` - writes ONLY the managed block of the root `.gitignore`, prints a unified diff of what it changed, then the `check` report. Exit 0 written or already current, 3 as `check`, 4 could not tell (nothing written), 5 refused (opt-out line, non-regular `.gitignore`, or an active ticket whose Touch does not cover `.gitignore`; nothing written).
- `summary --root R` - the one line `/crew:status` prints, from the same measurement.

Measurement, every step by git, never by string comparison:
1. Files: `git -c core.fsmonitor=false ls-files -z --cached --others --exclude-standard` with `GIT_OPTIONAL_LOCKS=0`, 10s timeout. Ignored files are never evidence.
2. Detection: each `LANGUAGES` row names evidence (extensions and manifest basenames) and the directories that hold a manifest. Anchored rows (`/<dir>/bin/`, `/<dir>/obj/`, `/<dir>/target/`, `/<dir>/build/` for gradle, `/<dir>/vendor/` for composer) emit one pattern per manifest directory; unanchored rows (`__pycache__/`, `node_modules/`, `.terraform/`) emit one pattern.
3. Covered: a candidate's probe path (each row carries one, e.g. `__pycache__/x.pyc`) is tested with `git -c core.excludesFile= check-ignore --no-index -q`; 0 is covered, 1 is missing, anything else is `unknown`. The global excludes file is disabled because it does not travel with a clone.
4. Tracked: candidates are written to a temp exclude file and `git ls-files -z --cached --ignored --exclude-from=<tmp>` names the tracked files each would match (run per candidate). Secret-shaped rows (`SECRETS`) with a tracked match produce `needs-owner`.
5. Conflict: every `!` line in the tracked `.gitignore` files (from `git ls-files '*.gitignore' '.gitignore'`) is taken as a literal path when it has no wildcard; a directory candidate that is a parent of that path is a `conflict`. A negation with a wildcard under a candidate directory is also `conflict` (cannot be measured safely, so not added).

The managed block, placed at the TOP of the root `.gitignore` on first write so every human line below it wins by git's last-match rule:

```
# crew:gitignore:managed - maintained by crew_gitignore.py; crew only ever adds here.
# Put your own rules below this block; a rule below wins over one in it.
<patterns, each preceded by a one-line "# <lang>: <reason>" comment, grouped by language>
# crew:gitignore:end
```

Block content is the previous block's entries plus the new ones - crew never drops an entry. The full new text is computed first; written through a temp file in the same directory and `os.replace`; the original newline style (CRLF or LF, taken from the first line ending) and a UTF-8 BOM are kept. A second marker pair, a missing end marker or a start marker below a non-comment human line is `unknown` (exit 4), never repaired.

Table (`LANGUAGES`, `NOISE`, `SECRETS`) is vendored from github/gitignore (CC0-1.0) with the template file name per row and the commit read, and never carries a `.crew` or `.work` pattern:
- python (`*.py`, `pyproject.toml`, `requirements*.txt`, `setup.py`, `Pipfile`): `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `*.egg-info/`
- node (`package.json`): `node_modules/`, `npm-debug.log*`, `yarn-error.log*`, `.pnpm-store/`
- dotnet (`*.csproj`, `*.fsproj`, `*.vbproj`): `/<dir>/bin/`, `/<dir>/obj/` per project dir; `.vs/`, `*.user`, `TestResults/`
- terraform (`*.tf`): `.terraform/`, `*.tfstate`, `*.tfstate.*`, `crash.log`, `crash.*.log`
- rust (`Cargo.toml`): `/<dir>/target/`; java maven (`pom.xml`): `/<dir>/target/`; gradle (`build.gradle`, `build.gradle.kts`): `.gradle/`, `/<dir>/build/`; composer (`composer.json`): `/<dir>/vendor/`; go (`go.mod`): `*.test`
- `NOISE`, always: `.DS_Store`, `Thumbs.db`, `desktop.ini`, `*.swp`, `.idea/`, `.vscode/*`, `!.vscode/settings.json`, `!.vscode/tasks.json`, `!.vscode/launch.json`, `!.vscode/extensions.json`
- `SECRETS`, always: `.env`, `.env.*`, `!.env.example`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa`, `id_ed25519`

Refusal inside a ticket: `crew_ticket.resolve_active(root)` (`plugin/crew/hooks/scripts/crew_ticket.py:761`); an active ticket whose `touch_for` (`:841`) does not cover `.gitignore` by `in_touch` (`:404`) refuses `apply` with exit 5 and names the ticket; a broken pointer refuses too. No active ticket: `apply` proceeds.

### Step 1: the table, detection and the git reader
Files: plugin/crew/hooks/scripts/crew_gitignore.py, plugin/crew/tests/test_crew_gitignore.py
Test: python3 -m pytest plugin/crew/tests/test_crew_gitignore.py -q -k "detect or table or git_failure"
Risk: med - a detection that reads ignored files would recommend from vendored dependencies; a git failure read as "no files" is the unknown collapsing into "current"
- [ ] write the tests first and watch them fail: `test_detects_languages_from_tracked_and_untracked_files_only` (fixture from the spec's first Acceptance line, built with real `git init`/`git add` in `tmp_path`); `test_anchored_rows_emit_one_pattern_per_manifest_dir` (`src/A/A.csproj`, `src/B/B.csproj` give `/src/A/bin/`, `/src/B/bin/`, and nothing for a repo-root `bin/`); `test_never_emits_crew_or_work_patterns` (every pattern in every table row); `test_every_row_has_reason_probe_and_provenance`; `test_git_failure_is_unknown_exit_4` parametrised over not-a-repo, git missing from PATH, a `subprocess.TimeoutExpired`, and a `.gitignore` that is not UTF-8
- [ ] fetch provenance: `gh api repos/github/gitignore/commits/main --jq .sha`, and the templates `Python.gitignore`, `Node.gitignore`, `VisualStudio.gitignore`, `Terraform.gitignore`, `Rust.gitignore`, `Maven.gitignore`, `Gradle.gitignore`, `Composer.gitignore`, `Go.gitignore`, `Global/macOS.gitignore`, `Global/Windows.gitignore`, `Global/JetBrains.gitignore`, `Global/VisualStudioCode.gitignore`, `Global/Vim.gitignore`; keep only the Design's patterns, each row citing its template and the sha in a module constant `PROVENANCE`
- [ ] implement `_git(root, *args, timeout=10)` returning `(ok, stdout, reason)` with `core.fsmonitor=false`, `GIT_OPTIONAL_LOCKS=0`, `stdin=DEVNULL`, as `plugin/crew/hooks/scripts/crew_status.py:39-49`; `list_files`, `detect`, and the `LANGUAGES`/`NOISE`/`SECRETS` tables

### Step 2: `check` - covered, missing, tracked, conflict, needs-owner
Files: plugin/crew/hooks/scripts/crew_gitignore.py, plugin/crew/tests/test_crew_gitignore.py
Test: python3 -m pytest plugin/crew/tests/test_crew_gitignore.py -q -k "check or covered or tracked or conflict or secret"
Risk: high - the covered check is what stops duplicates and the tracked check is what stops an ignore from looking like it took effect; each must fail to `unknown`, never to `covered` or "no tracked files"
- [ ] tests first: `test_check_reports_missing_and_exits_1`; `test_covered_pattern_is_not_added` (covered by the root `.gitignore`, and separately by a nested `web/.gitignore`); `test_global_excludes_file_does_not_count_as_covered` (`core.excludesFile` set in the fixture's `GIT_CONFIG_GLOBAL` ignoring `__pycache__/` still reports it missing); `test_tracked_match_is_added_and_named` (tracked `src/App/bin/tool.exe`); `test_tracked_secret_is_needs_owner_exit_3` (tracked `certs/server.pem`, then separately a tracked `.env`); `test_conflict_with_human_negation_is_not_added` (`!src/App/bin/keep.txt`); `test_wildcard_negation_under_candidate_is_conflict` (`!src/App/bin/*.keep`); `test_check_is_read_only` (tree, index mtime and `.gitignore` bytes unchanged)
- [ ] implement `measure(root)` returning a dict of findings plus `state` in {`current`, `pending`, `owner`, `unknown`} and `check`'s printer and exit codes from the Design; a `check-ignore` status other than 0 or 1 makes the whole result `unknown` with that status in the reason, as `scripts/check-marketplace.py:1263` treats 128

### Step 3: `apply` - the managed block, atomically, and the refusals
Files: plugin/crew/hooks/scripts/crew_gitignore.py, plugin/crew/tests/test_crew_gitignore.py
Test: python3 -m pytest plugin/crew/tests/test_crew_gitignore.py -q -k "apply or opt_out or crlf or atomic or marker or ticket"
Risk: high - this is the only writer; a truncating open or a rewritten human line loses someone's ignore rules
- [ ] tests first: `test_apply_adds_only_inside_the_managed_block` (every human line's bytes and relative order unchanged, the block first, markers exact); `test_apply_is_idempotent` (second run: no diff, exit 0); `test_apply_keeps_previous_block_entries` (an entry whose language left stays); `test_apply_creates_gitignore_when_absent`; `test_opt_out_line_reports_and_never_writes` (exit 5); `test_non_regular_gitignore_refuses` (a symlink and a directory); `test_crlf_and_bom_are_preserved`; `test_write_is_atomic_and_leaves_original_on_failure` (monkeypatch the renderer to raise: original bytes intact, no temp left); `test_duplicate_or_unterminated_marker_is_unknown`; `test_apply_refuses_inside_a_ticket_whose_touch_lacks_gitignore` (fixture with `crew_ticket.py activate`, exit 5, bytes identical); `test_apply_allowed_when_touch_covers_gitignore`; `test_broken_active_pointer_refuses`; `test_policy_block_survives_apply` (a §3c block below is byte-identical and `git check-ignore` still un-ignores `.crew/verify.json`)
- [ ] implement `render(text, patterns)` as a pure function; `apply` computes the whole text, writes `<.gitignore>.crew-tmp-<pid>` with `newline=""`, `os.replace`s it, and prints the diff via `difflib.unified_diff`

### Step 4: the `/crew:status` line
Files: plugin/crew/hooks/scripts/crew_status.py, plugin/crew/tests/test_status.py
Test: python3 -m pytest plugin/crew/tests/test_status.py -q
Risk: low - status must stay read-only, bounded and within 40 lines
- [ ] tests first: `test_status_gitignore_line_current`, `test_status_gitignore_line_missing_names_languages`, `test_status_gitignore_line_owner`, `test_status_gitignore_line_unknown_when_git_fails`; the existing `test_status_is_read_only` (`plugin/crew/tests/test_status.py:57`), 40-line (`:66`) and fsmonitor (`:154`) tests stay green
- [ ] in `collect` (`plugin/crew/hooks/scripts/crew_status.py:185-209`) append `gitignore ` + `crew_gitignore.summary(root)` after the codemap line; an import failure prints `gitignore unknown (crew_gitignore.py not importable)`, never omits the line

### Step 5: wire it into init, onboard, implement and status docs
Files: plugin/crew/skills/crew-setup/phases.md, plugin/crew/skills/crew-setup/SKILL.md, plugin/crew/commands/init.md, plugin/crew/commands/onboard.md, plugin/crew/commands/implement.md, plugin/crew/commands/status.md, plugin/crew/BUDGETS.md, plugin/crew/.budget-allowance.json
Test: (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py) && python3 scripts/check_instructions.py && python3 scripts/check-marketplace.py
Risk: med - onboard.md has six lines of headroom under its allowance and implement.md nine under the 120-line budget; growing past either is a hard fail
- [ ] phases.md Phase 1 (after the §3c paragraph, `plugin/crew/skills/crew-setup/phases.md:223-234`): run `crew_gitignore.py apply --root .`, show the diff and report verbatim, no question (owner decision); add "and the managed language block is current" to done-when
- [ ] SKILL.md §3c (`plugin/crew/skills/crew-setup/SKILL.md:358-396`): one paragraph after the block saying language patterns are the managed block's job and never go in this block; the `crew-ignore-policy:list` marker and block bytes are untouched
- [ ] init.md: one line pointing at Phase 1's step, only if it fits under 120 lines
- [ ] onboard.md: item 6 under "Then make the knowledge executable" (`plugin/crew/commands/onboard.md:183-202`) and one sentence in `--refresh` (`:204-249`): run `apply`; exit 5 inside a ticket is reported, not worked around; stay within 255 lines, else raise the allowance with a reason
- [ ] implement.md step 6 (`plugin/crew/commands/implement.md:85-104`): run `crew_gitignore.py check --root .`; exit 1 applies only when Touch covers `.gitignore`, otherwise the PR body carries the missing lines and "applied at the next /crew:onboard"; exit 3 goes to the owner; stay at or under 120 lines
- [ ] status.md: frontmatter description gains "gitignore"; the line table (`plugin/crew/commands/status.md:24-36`) gains the `gitignore` row
- [ ] re-measure and update the `crew-markdown-lines` claim at `plugin/crew/BUDGETS.md:10`

### Step 6: sabotage entries, each naming the test it must turn red
Files: plugin/crew/tests/sabotage_gitignore.py, plugin/crew/tests/sabotage.py
Test: flock /root/crew-tmp/heavy.lock python3 plugin/crew/tests/sabotage.py (only the GITIGNORE entries are new; each must report its target test FAILED)
Risk: med - a mutation whose target stays green means the test does not guard what it names
- [ ] `sabotage_gitignore.py` exporting `GITIGNORE_MUTATIONS` in the `sabotage_webtest.py` shape, one entry per Acceptance sabotage item: covered check always true -> `test_check_reports_missing_and_exits_1`; global excludes not disabled -> `test_global_excludes_file_does_not_count_as_covered`; human line rewritten (strip applied to kept lines) -> `test_apply_adds_only_inside_the_managed_block`; tracked-secret exit 3 downgraded to 0 -> `test_tracked_secret_is_needs_owner_exit_3`; check-ignore status 128 read as not-ignored -> `test_git_failure_is_unknown_exit_4`; Touch refusal removed -> `test_apply_refuses_inside_a_ticket_whose_touch_lacks_gitignore`; `.crew` filter removed and a `.crew/*.log` row added -> `test_never_emits_crew_or_work_patterns`; block appended at the bottom -> `test_apply_adds_only_inside_the_managed_block`; `os.replace` path replaced by a truncating `open(path, "w")` -> `test_write_is_atomic_and_leaves_original_on_failure`; conflict check removed -> `test_conflict_with_human_negation_is_not_added`; status import failure omits the line -> `test_status_gitignore_line_unknown_when_git_fails`
- [ ] register at `plugin/crew/tests/sabotage.py:67-77` (import) and `:3047-3049` (concatenation); run each mutation once by hand first and confirm the named test goes red and the file restores byte-identical (`sha256sum` before and after)
- [ ] for each fix of a finding later in review, add the neighbouring-case test and a mutation here

### Step 7: verify rule, docs, version and changelog
Files: .crew/verify.json, plugin/crew/README.md, plugin/crew/NOTICE.md, plugin/PLUGINS.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, CHANGELOG.md, TODO.md, docs/guides/crew/src/quickstart.md, docs/guides/crew/src/daily-workflow.md, docs/guides/crew/crew-1.0-*, .crew/codemap/crew.md, .crew/codemap/marketplace-registration.md, docs/diagrams/process-crew-lifecycle.mmd
Test: python3 scripts/check-marketplace.py && python3 scripts/_test/self-claims.py && python3 scripts/_test/version-drift.py && python3 -m pytest plugin/crew/tests/test_crew_gitignore.py plugin/crew/tests/test_status.py -q && python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0039
Risk: low - a missed doc or claim fails the gate or leaves the next reader wrong; a missed version bump strands every installed copy
- [ ] `.crew/verify.json`: the rule from the spec's verify Acceptance line
- [ ] README: a `crew_gitignore.py` row in the script table (`plugin/crew/README.md:762` neighbourhood), a sentence in setup (`:2159-2170`) and in onboard refresh (`:445`), and the `/crew:status` command-table row (`:2375`)
- [ ] NOTICE.md: a github/gitignore (CC0-1.0) section naming the templates and the sha from Step 1
- [ ] PLUGINS.md `/crew:status` row (`plugin/PLUGINS.md:155`) matches the new frontmatter description; version claim updated
- [ ] quickstart.md step 3 check and daily-workflow.md step 4 each gain one sentence; rebuild with `python3 docs/guides/crew/src/build.py` and commit the HTML, DOCX and PDF it writes
- [ ] bump crew to the next free patch version on origin/main in `plugin.json`, `marketplace.json` and PLUGINS.md; CHANGELOG entry naming the owner decision, the exit codes and "never untracks"; TODO.md entry for applying to this repo's own `.gitignore` (Exclusions)
- [ ] run `crew_refresh_check.py`; refresh `.crew/codemap/crew.md` (and the diagram if named) until `fresh`; quote `crew_gitignore.py check --root .` against this repo in the PR body
