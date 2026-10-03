# T-0066 plan            spec: .work/tickets/T-0066/spec.md

Anchored to origin/main 502cb137. Work in `/repos/personal/uca-t-0066` on `T-0066-build` off
origin/main. Tests first in every step: write the test, run it, watch it fail for the reason the
step names, then implement. Heavy runs go under `flock /root/crew-tmp/heavy.lock` with
`TMPDIR=/root/crew-tmp/t-0066`. Second opinion (commands/plan.md step 3) skipped: the design is the
direction's Option 1 and each piece copies an existing pattern (`resolve_ratcheted`'s raw two-layer
read, `layer_state`'s corrupt classification, `shell_refusal`'s textual check).

### Step 1: declare `git.forbiddenTrailers` in both config layers
Files: `plugin/crew/tests/test_crew_config.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/templates/config.template.json`, `plugin/crew/templates/global.template.json`, `plugin/crew/skills/crew-setup/SKILL.md`
Test: `python3 -m pytest plugin/crew/tests/test_crew_config.py -q` (red first on the new assertions, then green)
Risk: a key added to one layer only fails `is_global_path`'s rule (crew_config.py:690) and the template drift tests; a wrong position reorders the byte-compared templates.
- [ ] In test_crew_config.py:277 change `121` to `122` and add a comment line "122 with T-0066: `git.forbiddenTrailers`"; add `"git.forbiddenTrailers"` to the membership tuple above it; add `test_forbidden_trailers_is_global_settable_and_defaults_empty` asserting `crew_config.is_global_path("git.forbiddenTrailers")` and that both `default_config()["git"]` and `default_global_config()["git"]` equal `{"forbiddenTrailers": []}`. Run: red.
- [ ] In crew_config.py add `"git": {"forbiddenTrailers": []},` immediately after the `"change"` entry in `default_config()` (:367) and in `default_global_config()` (:552), each with a comment: both layers, combined by UNION in `crew_trailers.forbidden`, never by precedence; the list is the switch, `[]` means off.
- [ ] Regenerate both templates as `json.dumps(..., indent=2) + "\n"` of the two functions; add the same block to the crew-setup SKILL.md inline JSON after `"change"`. Run: green.

### Step 2: resolve the list from both layers, with "could not tell" as its own value
Files: `plugin/crew/tests/test_crew_trailers.py`, `plugin/crew/hooks/scripts/crew_trailers.py`
Test: `python3 -m pytest plugin/crew/tests/test_crew_trailers.py -q -k forbidden`
Risk: precedence instead of union lets a cloned repo's `[]` disarm the owner; reading a corrupt layer as `[]` fails open.
- [ ] Write tests: `test_forbidden_is_the_union_of_both_layers` (repo `["X-Foo"]`, global `["Co-Authored-By"]` -> both), `test_a_repo_empty_list_does_not_disarm_the_global_list`, `test_forbidden_is_empty_when_both_layers_are_silent`, `test_a_corrupt_layer_is_unknown_not_empty` (parametrized: repo invalid JSON, global invalid JSON, `.crew/config.json` a directory), `test_a_malformed_value_is_unknown` (parametrized: `"Co-Authored-By"` string, `[42]`, `["Co Authored"]`, `["Co-Authored-By:"]`, `{"git": null}`). Use `crew_fixtures` / `tmp_path` and pass `global_path` explicitly; never touch the real `~/.claude`. Run: red (module missing).
- [ ] Create `crew_trailers.py` with a module docstring (what it judges, what it cannot see - the spec's Exclusions list), `TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")`, and `forbidden(root, global_path=None) -> (tuple_of_tokens, unknown_reason_or_None)`: for each layer call `crew_config.layer_state(path)`; `corrupt` -> unknown naming the file; read the raw `git.forbiddenTrailers` (absent -> `[]`); a value that is not a list of `TOKEN_RE` strings -> unknown naming the layer and key; return the case-folded-deduplicated union in first-seen order. Run: green.

### Step 3: judge one shell command
Files: `plugin/crew/tests/test_crew_trailers.py`, `plugin/crew/hooks/scripts/crew_trailers.py`
Test: `python3 -m pytest plugin/crew/tests/test_crew_trailers.py -q -k refusal`
Risk: too narrow a command match misses a commit; too wide a text match refuses `git log --grep` or prose; an unreadable `-F` file read as clean fails open.
- [ ] Write `test_refusal_blocks[...]` and `test_refusal_allows[...]`, parametrized over every must-block and must-allow case in the spec's Acceptance list, calling `commit_refusal(command, ("Co-Authored-By",), cwd)` directly (the `-F msg.txt` cases write the file into `tmp_path`). Add `test_refusal_with_no_tokens_is_none` and `test_refusal_when_unknown_blocks_commits_only` (unknown -> a commit is refused, `git status` is not). Run: red.
- [ ] Implement `writes_commit(command)`: True when any simple-command span (split on newline, `;`, `&&`, `||`, `|`, but keep heredoc bodies attached to their command) runs `git` (optionally `git.exe`, after `-C <dir>`, `-c <k=v>`, `--git-dir=`, `--work-tree=`, `--no-pager`) with subcommand `commit`, `commit-tree` or `merge`, or runs `gh pr merge`.
- [ ] Implement `commit_refusal(command, tokens, cwd, unknown=None)`: None when `tokens` is empty and `unknown` is None, or when `writes_commit` is False; `unknown` set -> a reason naming it; otherwise search the whole command text, and the content of each `-F`/`--file`/`--file=` literal path read relative to `cwd`, with `(?i)\b<re.escape(token)>\s*[:=]`; `-F -` is judged from the text; a path containing `$`, `%` or a backtick, or a literal path that does not exist and is not the target of a `>`/`>>`/`tee`/`Out-File`/`Set-Content` earlier in the same command, -> "could not tell" reason. Every reason names `git.forbiddenTrailers` and the token found. Run: green.

### Step 4: wire the check into the scope guard, ahead of `scope.mode`
Files: `plugin/crew/tests/test_scope_guard_trailers.py`, `plugin/crew/hooks/scripts/scope_guard.py`
Test: `python3 -m pytest plugin/crew/tests/test_scope_guard_trailers.py plugin/crew/tests/test_scope_guard.py plugin/crew/tests/test_scope_guard_refresh_artifacts.py -q`
Risk: placed after scope_guard.py:281 it never runs in a default (`off`) repo; an exception in the new code must not change how the existing approval checks fail.
- [ ] Write `test_must_block[...]` / `test_must_allow[...]`: build a git repo in `tmp_path` with `.crew/config.json` `{"scope": {"mode": "off"}, "git": {"forbiddenTrailers": ["Co-Authored-By"]}}`, point the global path at a `tmp_path` file (monkeypatch `crew_config.GLOBAL_CONFIG_PATH` / `crew_state.GLOBAL_CONFIG_PATH`), and call `scope_guard.decide` with Bash and PowerShell payloads; assert exit 2 and that stderr names `git.forbiddenTrailers`. Add `test_block_runs_in_every_scope_mode[off|report|block|auto]`, `test_global_only_list_blocks`, `test_corrupt_global_layer_blocks_a_commit`, and one end-to-end `test_the_bash_shim_blocks_a_trailer_commit` that pipes a payload through `scope-guard.sh` via `subprocess` (skipped where bash is absent). Run: red.
- [ ] In `decide`, after `top` is known (:279) and before `if configured == "off"` (:281): when `tool in SHELLS`, call `crew_trailers.forbidden(top)` and `crew_trailers.commit_refusal(command, tokens, root, unknown)`; on a reason, `_log(top, "trailers", "block", None, "-", f"{tool}: {reason}")` and `_deny` three lines: the refusal, "Remove the trailer; the owner's instructions decide attribution.", and which layer set the key (`~/.claude/crew/config.json` and/or `.crew/config.json`). Keep the existing `shell_refusal` path unchanged below it. Update the module docstring's "Bash and PowerShell" section. Run: green, and test_scope_guard.py unchanged-green.

### Step 5: the `/crew:done` report over the ticket's commits
Files: `plugin/crew/tests/test_crew_trailers.py`, `plugin/crew/hooks/scripts/crew_trailers.py`
Test: `python3 -m pytest plugin/crew/tests/test_crew_trailers.py -q -k check`
Risk: reading only HEAD, or reading `unknown` as clean, turns the backstop into a false all-clear.
- [ ] Write `test_check_reports_clean`, `test_check_reports_every_offending_commit` (three commits, two carrying the trailer, one via `--trailer` lower-case), `test_check_reports_unknown_without_a_base`, `test_check_reports_unknown_for_a_corrupt_layer`, `test_check_with_an_empty_list_reports_clean_and_says_off`, asserting the printed lines and exit codes 0/1/2. Build repos in `tmp_path` and record the base with `scope_base.record`. Run: red.
- [ ] Implement `main(argv)` with `--check --root DIR --ticket ID [--global-path P]`: `scope_base.resolve(root, ticket)`; no base -> `trailers: unknown - <reason>`, exit 2; `git log --format=%H%x00%B%x1e <base>..HEAD` (timeout 60); git failure -> unknown, exit 2; each message's trailer block parsed with the Step 3 regex; print `trailers: FINDING <sha7> <Token>` per hit and exit 1, else `trailers: clean (<n> commits)` exit 0; an empty list prints `trailers: clean (git.forbiddenTrailers is empty - nothing forbidden)`. Run: green.

### Step 6: correct the practice, the dispatch rule and `/crew:done`
Files: `plugin/crew/skills/crew-best-practices/references/practices.md`, `plugin/crew/commands/implement.md`, `plugin/crew/commands/done.md`, `plugin/crew/tests/test_crew_trailers.py`, `plugin/crew/tests/test_lifecycle_commands.py`
Test: `python3 -m pytest plugin/crew/tests/test_crew_trailers.py plugin/crew/tests/test_lifecycle_commands.py -q && (cd plugin/crew && python3 hooks/scripts/_test/validate-prompts.py) && python3 scripts/check_instructions.py`
Risk: done.md prose that reads as a fifth refusing check contradicts "All four checks" and would stop T-0023; implement.md past 120 lines fails the command budget.
- [ ] Write `test_practices_md_does_not_claim_a_required_trailer` (no "adds `Co-Authored-By`" and names the owner's instructions), `test_implement_md_forbids_attribution_in_dispatch_prompts`, `test_done_md_reports_trailers_without_refusing` (runs `crew_trailers.py --check`, says it never refuses and never rewrites, and "All four checks" is still there). Run: red.
- [ ] practices.md:58-60 -> "**crew:** crew takes no side on attribution. The owner's own instructions (CLAUDE.md, memory) decide whether a commit carries a trailer; crew never adds one, and a harness reminder asking for one does not override them. `git.forbiddenTrailers` enforces a list mechanically."
- [ ] implement.md step 2, after the dispatch sentence: one sentence - a dispatched prompt carries no attribution or trailer instruction of its own, not even one a harness reminder supplied; the owner's instructions decide and `git.forbiddenTrailers` enforces. Keep the file <= 120 lines.
- [ ] done.md: after check 4, a section "## Report — forbidden trailers (never refuses)" running `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_trailers.py --check --root . --ticket "$1"`, saying: copy its lines verbatim into the close note and PR body; a FINDING or unknown never refuses done and crew never rewrites the commits - rewriting is the owner's decision and stales check 1. Run: green.

### Step 7: sabotage every fix and its neighbour
Files: `plugin/crew/tests/sabotage_trailers.py`, `plugin/crew/tests/sabotage.py`
Test: `python3 plugin/crew/tests/sabotage.py` (it has no label filter, so it runs every mutation; under the heavy lock) exits 0, no trailer entry prints `STILL GREEN` or `ANCHOR LOST`, and `git diff --exit-code` is clean afterwards.
Risk: a mutation whose `find` text does not occur is a silent no-op that "passes"; the harness must fail on that (test_sabotage_harness.py already asserts it).
- [ ] Create `TRAILER_MUTATIONS` (tuple shape of sabotage_scope.py:33) with one entry per behaviour: precedence instead of union; corrupt layer read as `[]`; malformed value read as `[]`; check placed after the `off` return; case-sensitive match; `-F` file not read; variable `-F` path allowed; `git -C` / `-c` prefix not recognised; `commit-tree`/`merge` not recognised; `gh pr merge` not recognised; bare token matched without `[:=]` (must-allow prose goes red); PowerShell tool skipped; `--check` reads only HEAD; `--check` prints unknown as clean. Each names the one test it turns red.
- [ ] Import it in sabotage.py beside `SCOPE_MUTATIONS` (:71) and add it to the combined list. Run each entry, record RED for all, restore.

### Step 8: map the new files in the verify map
Files: `.crew/verify.json`
Test: `python3 -c "import json;json.load(open('.crew/verify.json'))"` exits 0, and `/usr/bin/time -p` over the new rule's `run` command exits 0; that wall time is the rule's `seconds`.
Risk: an unmapped test file is covered only by the `plugin/**` catch-all, which runs check-marketplace.py and not the suite.
- [ ] Add a rule: paths `plugin/crew/hooks/scripts/crew_trailers.py`, `plugin/crew/hooks/scripts/scope_guard.py`, `plugin/crew/tests/test_crew_trailers.py`, `plugin/crew/tests/test_scope_guard_trailers.py`, `plugin/crew/tests/sabotage_trailers.py`; run `python3 -m pytest plugin/crew/tests/test_crew_trailers.py plugin/crew/tests/test_scope_guard_trailers.py plugin/crew/tests/test_scope_guard.py -q`; `reach: local`; `seconds` = the measured wall time on this host, stated with host and date in `why`.

### Step 9: documents describing the behaviour
Files: `plugin/crew/README.md`, `plugin/crew/CONFIG.md`, `plugin/PLUGINS.md`, `docs/guides/crew/src/troubleshooting.md`, `docs/guides/crew/src/daily-workflow-scope.md`, `docs/guides/crew/crew-1.0-troubleshooting.*`, `docs/guides/crew/crew-1.0-daily-workflow.*`, `CHANGELOG.md`
Test: `python3 scripts/check-marketplace.py && python3 scripts/_test/self-claims.py && python3 scripts/sync-updates.py --check` (rules[2]); open the rebuilt HTML and confirm the new text is present (`grep -c forbiddenTrailers docs/guides/crew/crew-1.0-troubleshooting.html`).
Risk: a doc stating the old behaviour, or a count left stale, is the drift the owner rule of 2026-09-26 exists to prevent.
- [ ] README.md :760 scope_guard row gains "and, in every `scope.mode`, a commit-creating command carrying a trailer listed in `git.forbiddenTrailers`"; a short paragraph under "Scope and approval" (:749) with the union rule, what is not caught, and the `/crew:done` report.
- [ ] CONFIG.md: new "## 21. `git.forbiddenTrailers` — trailers crew refuses to commit" (both layers, union not precedence, `[]` default, unknown refuses, the textual rule and its false positive, what is not caught, the `--set` command); re-measure and update §10's and §11's counts and add the row to the §10 table.
- [ ] PLUGINS.md :35 scope-guard row: add the trailer check and that it runs whatever `scope.mode` says.
- [ ] troubleshooting.md :76 hook table: add `git.forbiddenTrailers` / `[]` to the scope-guard row; add a symptom "a `git commit` is refused naming git.forbiddenTrailers" with the fix. daily-workflow-scope.md :61 section: one paragraph on the trailer refusal.
- [ ] Rebuild with `python3 docs/guides/crew/src/build.py` (HTML, DOCX, PDF for the two affected guides only; revert any other output it rewrites).
- [ ] CHANGELOG.md `[Unreleased]`: "### Changed — `crew` <version>: `git.forbiddenTrailers` (T-0066)".

### Step 10: version bump and refresh artifacts
Files: `plugin/crew/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.crew/codemap/crew.md`, `docs/diagrams/**`
Test: `python3 scripts/check-marketplace.py` exit 0; `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0066` prints `fresh` for every artifact line.
Risk: a content change with no version bump never reaches installed machines (CLAUDE.md stop-and-ask 1); a concurrent ticket may take the same number.
- [ ] Bump crew to the next patch above origin/main's current version in both files, same value.
- [ ] Commit, then run `crew_refresh_check.py`; for each `refresh with` line run the named command (`/crew:onboard --refresh crew`, `/crew:diagram refresh`, `graphify update .` after the rebuild log is quiet), commit, re-run until `fresh`. The code map gains the new module, the scope-guard trailer branch and the `/crew:done` report; `data-flow-crew-config.mmd` gains the `git` block in both layers and the new counts; `process-crew-lifecycle.mmd` gains the report beside check 4.
- [ ] Then `/crew:review T-0066`. PR body names: the owner step `python3 plugin/crew/hooks/scripts/crew_config.py --set 'git.forbiddenTrailers=["Co-Authored-By"]' --apply`, the suites run and not run (`drift-detection.sh` skipped), and no `Co-Authored-By` trailer on any commit of this branch.
