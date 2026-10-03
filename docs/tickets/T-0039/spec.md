# T-0039 crew keeps a repo's .gitignore right for the languages in it          status: spec   risk: med
## Intent
A new read-only-by-default script, `crew_gitignore.py`, detects the languages and build tools actually present in a repository (from `git ls-files`, never a raw walk) and compares a curated, vendored table of ignore patterns against what the repository's own ignore files already do, measured with `git check-ignore`. `apply` adds whatever is missing inside ONE marker-delimited managed block - automatically, without asking, per the owner's 2026-09-26 decision - and never edits, reorders or removes a line a human wrote, the `.crew` policy block included. It runs at `/crew:init` Phase 1, at `/crew:onboard` (first run and `--refresh`), is checked read-only at `/crew:implement` step 6, and `/crew:status` shows it as one line.
## Exclusions
- No `git rm --cached`, no untracking and no history rewrite, ever. A tracked file a new pattern matches is named in the report; a tracked secret-shaped file is a `needs-owner` line and exit 3, never fixed by crew (rotation and history are the owner's decision).
- Never touches the `.crew/*` policy block or its closed un-ignore list: the table carries no `.crew` or `.work` pattern, so `scripts/check-marketplace.py::check_crew_ignore_policy` is unaffected.
- Never deletes an entry, even inside its own managed block: a pattern whose language has left the repo stays (harmless, and someone may rely on it).
- No ambiguous build-output patterns in the table: `build/` and `dist/` unanchored, Go `vendor/`, `*.tfvars` and `.terraform.lock.hcl` are never added, because repositories legitimately commit them (GitHub Actions commit `dist/`, Go modules may vendor, tfvars are often reviewed config).
- No runtime fetch of templates: the table is vendored in the script with provenance, not downloaded.
- No new `.crew/config.json` key; the opt-out is a `# crew:gitignore:off` line in `.gitignore` (report only, never write). So `CONFIG.md` and the config templates do not change.
- Nested `.gitignore` files are read (git reads them) but never written; only the repository root `.gitignore` is written.
- `.gitignore` does not become a refresh-artifact path (`crew_refresh_check.REFRESH_ARTIFACT_PATHS` is unchanged) - see Unknowns.
- This repository's own `.gitignore` is not changed by this ticket; `check` is run against it and its output quoted in the PR body. Applying it here is a follow-up.
- Non-crew repositories (the Obsidian vault named in direction.md) are out of scope: only a repo with a crew config runs these steps.
## Evidence
- Setup appends one fixed block today, secrets plus the `.crew` policy and `.work/`: `plugin/crew/skills/crew-setup/SKILL.md:358-396`; Phase 1 writes it: `plugin/crew/skills/crew-setup/phases.md:223-234`, done-when `:232-234`. Nothing looks at languages.
- The one existing additive gitignore merge, the precedent to reuse in spirit: `plugin/crew/hooks/scripts/webtest_scaffold.py:213-219` (`merge_ignore`), called at `:261-262`; `/crew:init` documents it at `plugin/crew/commands/init.md:36-44`.
- The policy checker parses this repo's `.gitignore` and marked sources: `scripts/check-marketplace.py:1168-1185` (constants), `:1372` (`check_crew_ignore_policy`); its docstrings record measured git behaviour the new script must also respect - trailing space stripped, trailing tab not, leading space significant, first-char `#` only is a comment (`scripts/check-marketplace.py:1199-1262`), and that a repo `.gitignore` outranks `core.excludesFile`.
- The completion audit sees what git sees, so ignored files are outside it: `docs/guides/crew/src/daily-workflow-scope.md:96-97`. This is why an ignore line written inside a ticket without Touch would let the ticket hide its own files.
- Refresh-artifact allow-list, deliberately left alone: `plugin/crew/hooks/scripts/crew_refresh_check.py:168-173`; implement step 6 runs it: `plugin/crew/commands/implement.md:85-104`.
- Active ticket and Touch APIs the `apply` refusal uses: `plugin/crew/hooks/scripts/crew_ticket.py:761` (`resolve_active`), `:841` (`touch_for`), `:404` (`in_touch`), `:822` (`effective_mode`).
- Status report: `plugin/crew/hooks/scripts/crew_status.py:36` (`MAX_LINES = 40`), `:39-49` (`_git` with `core.fsmonitor=false`, `GIT_OPTIONAL_LOCKS=0`), `:185-209` (`collect`); tests `plugin/crew/tests/test_status.py:57` (read-only), `:66` (40 lines), `:154` (no fsmonitor); line table `plugin/crew/commands/status.md:24-36`.
- Onboard: executable-knowledge list `plugin/crew/commands/onboard.md:183-202`, `--refresh` `:204-249`. Command budget: `onboard.md` is 249 lines against a 255 allowance (`plugin/crew/.budget-allowance.json`), `implement.md` 111 against the 120-line budget, `status.md` 57, `init.md` 48; growth past an allowance is a hard fail (`plugin/crew/BUDGETS.md:26-29`), and `plugin/crew/BUDGETS.md:10` carries the `crew-markdown-lines` claim every `.md` edit moves.
- Sabotage harness: modules imported at `plugin/crew/tests/sabotage.py:67-77`, concatenated at `:3047-3049`; module shape `plugin/crew/tests/sabotage_webtest.py:1-40`.
- Verify rules live in `.crew/verify.json`; no rule covers `crew_status.py` or `test_status.py` today.
- Current version: `plugin/crew/.claude-plugin/plugin.json` = 1.0.42 on origin/main 502cb137; version claims in `plugin/PLUGINS.md` and `.crew/codemap/marketplace-registration.md`.
- Docs that describe the touched commands: `plugin/crew/README.md:445` (onboard refresh), `:762` (script table), `:2159-2170` (setup gitignore), `:2357`, `:2375` (command table); `plugin/PLUGINS.md:146`, `:155`; `docs/guides/crew/src/quickstart.md:20-21`, `:83`; built by `docs/guides/crew/src/build.py`.
## Unknowns
- Owner question, recommendation first: keep `.gitignore` OUT of the refresh-artifact paths. Recommended because an approved ticket could then write an ignore line outside Touch and hide its own out-of-scope files from the completion audit (daily-workflow-scope.md:96). Consequence: inside a ticket, `apply` refuses unless the active ticket's Touch covers `.gitignore`, and the additions land at the next `/crew:onboard`, `/crew:onboard --refresh` or `/crew:init` run outside a ticket. The alternative (allow-list it) needs a scope-guard change and its own sabotage set; not planned. Proceeding on the recommendation unless the owner says otherwise at approval.
- Placement: the managed block goes at the TOP of `.gitignore` on first write, so every human line below it - negations included - wins by git's last-match rule. A directory pattern still cannot be re-included below by a human negation, so a candidate that would exclude a directory containing a path some `!` line re-includes is reported as `conflict` and not added. Resolved by tests in plan Step 2.
- Provenance of the vendored table: resolved at implement Step 1 by reading github/gitignore (CC0-1.0) via `gh api` and recording the file names and commit sha in the module and in `plugin/crew/NOTICE.md`; if unreachable, record the template file names and the read date and say so in the PR body - accepted as risk.
- Line endings and BOM: an existing CRLF file is written back CRLF, a BOM is kept; resolved by tests in plan Step 3. Windows parity (`pwsh` shim not needed - the script is invoked with python) accepted as risk until win-repo-2 runs it.
- Very large repos: `git ls-files` and `check-ignore` bounded by a timeout; a timeout is `unknown` (exit 4), never "current". Accepted as risk beyond that.
- Crew version: several tickets bump crew concurrently; implement takes the next free patch version on origin/main at that time and re-sets it last.
## Touch
- `plugin/crew/hooks/scripts/crew_gitignore.py`
- `plugin/crew/hooks/scripts/crew_status.py`
- `plugin/crew/tests/test_crew_gitignore.py`
- `plugin/crew/tests/test_status.py`
- `plugin/crew/tests/sabotage_gitignore.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/commands/onboard.md`
- `plugin/crew/commands/implement.md`
- `plugin/crew/commands/status.md`
- `plugin/crew/commands/init.md`
- `plugin/crew/skills/crew-setup/SKILL.md`
- `plugin/crew/skills/crew-setup/phases.md`
- `plugin/crew/README.md`
- `plugin/crew/NOTICE.md`
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.budget-allowance.json` - only if onboard.md cannot fit the six lines of headroom it has
- `plugin/crew/.claude-plugin/plugin.json`
- `plugin/PLUGINS.md`
- `.claude-plugin/marketplace.json`
- `.crew/verify.json`
- `.crew/codemap/crew.md`
- `.crew/codemap/marketplace-registration.md`
- `docs/diagrams/process-crew-lifecycle.mmd` - anchors implement.md, so refreshed when the refresh check names it
- `docs/guides/crew/src/quickstart.md`
- `docs/guides/crew/src/daily-workflow.md`
- `docs/guides/crew/crew-1.0-*`
- `CHANGELOG.md`
- `TODO.md`
## Acceptance checks
- [ ] `test_crew_gitignore.py::test_detects_languages_from_tracked_and_untracked_files_only`: a fixture with `app/x.py`, `web/package.json`, `src/App/App.csproj`, `infra/main.tf` and an ignored `node_modules/pkg/setup.py` detects python, node, dotnet, terraform - and not from the ignored file.
- [ ] `test_check_reports_missing_and_exits_1` and `test_apply_adds_only_inside_the_managed_block`: every human line keeps its bytes and order, the block sits at the top between `# crew:gitignore:managed` and `# crew:gitignore:end`, and a second `apply` changes nothing and exits 0.
- [ ] `test_covered_pattern_is_not_added`: a pattern already effective through the repo's own ignore files is not duplicated, and a machine-global `core.excludesFile` does NOT count as covered (it does not travel with a clone).
- [ ] `test_tracked_match_is_added_and_named` and `test_tracked_secret_is_needs_owner_exit_3`: a pattern matching a tracked file is added and the file named; a tracked `*.pem`/`.env` is a `needs-owner` line and exit 3; nothing is untracked.
- [ ] `test_conflict_with_human_negation_is_not_added`: `!src/App/bin/keep.txt` below makes `/src/App/bin/` a `conflict` line, not an addition.
- [ ] `test_never_emits_crew_or_work_patterns` and `check-marketplace.py` passes over a fixture `.gitignore` after `apply`.
- [ ] `test_apply_refuses_inside_a_ticket_whose_touch_lacks_gitignore` (exit 5, file byte-identical) and `test_apply_allowed_when_touch_covers_gitignore`; a broken active-ticket pointer also refuses.
- [ ] `test_opt_out_line_reports_and_never_writes`; `test_crlf_and_bom_are_preserved`; `test_write_is_atomic_and_leaves_original_on_failure` (a raising render leaves the original bytes, per CLAUDE.md's truncating-open landmine).
- [ ] `test_git_failure_is_unknown_exit_4`: not a repo, git missing, a timeout and an undecodable `.gitignore` each print `unknown` with the reason and exit 4 - never 0.
- [ ] `test_status.py::test_status_gitignore_line_*`: `/crew:status` shows one `gitignore` line (`current`, `N missing (<langs>)`, `owner: ...`, `unknown (<reason>)`), stays within 40 lines, stays read-only and never runs fsmonitor.
- [ ] sabotage: `sabotage_gitignore.py` entries, run by `sabotage.py`, each turn a named test red - covered-check disabled, human line rewritten, tracked-secret downgraded to exit 0, git failure read as current, Touch refusal removed, `.crew` pattern allowed, block placed at the bottom, atomic write replaced by truncating open.
- [ ] `.crew/verify.json` gains a rule mapping `crew_gitignore.py`, `crew_status.py`, `test_crew_gitignore.py`, `test_status.py` and `sabotage_gitignore.py` to `python3 -m pytest plugin/crew/tests/test_crew_gitignore.py plugin/crew/tests/test_status.py -q`.
- [ ] `/crew:init` Phase 1, `/crew:onboard` (first run and `--refresh`), `/crew:implement` step 6 and `/crew:status` describe the new step; `validate-prompts.py` passes; `check_instructions.py` budgets pass with no allowance growth unless justified; `python3 scripts/check-marketplace.py` and `python3 scripts/_test/self-claims.py` pass.
- [ ] crew version bumped in `plugin.json`, `marketplace.json` and `plugin/PLUGINS.md`; CHANGELOG entry; README, quickstart and daily-workflow guides updated and rebuilt with `docs/guides/crew/src/build.py`; `.crew/codemap/crew.md` refreshed.
