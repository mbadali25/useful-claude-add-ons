# T-0048 plan            spec: .work/tickets/T-0048/spec.md

Work in a fresh worktree on branch `T-0048-guide-config-ref`, from origin/main (`1e0706ac` or later). Every line number below is origin/main's; re-grep each quoted string before editing. The plan assumes the owner took every recommendation D1-D7 in `direction.md`. If D5 or D6 is declined, drop the rebuild or the DOCX/PDF bullets named in the spec's Unknowns. No behaviour changes, so the one guard-grade part is the checks themselves. Each check gets must-block and must-allow cases and a sabotage that must go red. No second opinion at plan time: the design follows repo precedent (`crew_instructions.py --check`, `sync-updates.py --check`).

### Step 1: the key table, one row per leaf
Files: plugin/crew/hooks/scripts/crew_keys.py, plugin/crew/tests/test_crew_keys.py
Test: python3 -m pytest plugin/crew/tests/test_crew_keys.py -q -p no:cacheprovider
Risk: med. A row that restates a tuple instead of pointing at it is a second definition, which is the drift this ticket exists to remove. The identity tests below are what stop it.
- [ ] Write the tests first and watch them fail:
  - `test_every_leaf_has_a_row`: the union of `crew_config.leaf_paths(default_config())` and `leaf_paths(default_global_config())` is a subset of `KEY_META`'s keys.
  - `test_no_orphan_rows`: every `KEY_META` key is such a leaf.
  - `test_ratcheted_rows_do_not_restate_tiers`: a key in `crew_guards.RATCHETED_KEYS` has no `values` in its row, and `crew_keys.values_of(key)` returns the tiers object itself.
  - `test_tuple_backed_values_are_the_same_object`, parametrised:
    - `qa.provider` -> `("auto",) + QA_PROVIDERS` built once in crew_keys, with a test that its tail `is`-matches `QA_PROVIDERS`' items;
    - `dev.provider` -> `DEV_PROVIDERS`;
    - `pm.authority` -> `AUTHORITIES`;
    - `pm.ticketGranularity` -> `TICKET_GRANULARITIES`;
    - `scope.mode` -> `crew_ticket.MODES`;
    - `context.autoClear.method` -> the union of `crew_platform._AUTOCLEAR_METHODS` values, in first-seen order, with the per-OS table carried as `values_by_os`.
  - `test_every_row_has_a_summary_and_a_values_kind`: `kind` is one of `tuple`, `ratchet`, `type`, `open-table`, `prose` or `unvalidated`.
- [ ] Create `plugin/crew/hooks/scripts/crew_keys.py`. It imports `crew_state`, `crew_guards`, `crew_ticket` and `crew_platform`, and nothing imports it except `config_reference.py` and tests, so there is no cycle. Its parts:
  - A module docstring stating the one rule: a value tuple a validator reads is referenced, never copied.
  - `KEY_META`: an ordered dict, dotted key -> `{"summary", "kind", "values", "since", "layer_rule", "source"}`.
  - `layer_rule` is set only for what the code cannot derive: `machine-arms` (`resume.auto`, `context.autoClear.enabled`: only the global file can say `true`, and a repo may only veto) and `machine-only` (the `AUTOCLEAR_MACHINE_ONLY_KEYS`, referenced).
  - `source` is the file that reads the key, for `unvalidated` and `prose` rows.
- [ ] Fill all 119 rows. Take each summary from CONFIG.md's existing row or section for that key, so the text is not re-invented. Values: from the tuples above; `type` rows state a type (`positive int`, `bool`, `list of globs`, `string or null`); `prose` rows cite their source (`qa.codex.reasoningEffort`, `dev.codex.reasoningEffort` -> `plugin/crew/commands/review.md`); every other key with no reader-side check is `unvalidated`. Leave `since` as `None` for now.
- [ ] Add helpers `values_of(key)`, `layer_of(key)` and `problems()`. `layer_of` returns `repo` / `both` / `both, ratchet` / `both, widening warned` / the `layer_rule`, derived from `is_global_path`, `ratchet_spec` and `crew_config._RATCHETED`. `problems()` returns the list the tests assert empty: missing, orphan, restated tiers, and bad kind.
- [ ] Run the Test command. It must be green.

### Step 2: arrival versions, code-branch agreement, and COMING
Files: plugin/crew/hooks/scripts/crew_keys.py, plugin/crew/tests/test_crew_keys.py
Test: python3 -m pytest plugin/crew/tests/test_crew_keys.py -q -p no:cacheprovider
Risk: med. A wrong `since` looks measured. The backfill is a script whose output is recorded, not a set of guesses.
- [ ] Backfill `since` with a throwaway script in the session scratchpad (not committed). For each commit in `git log --reverse --format=%h -- plugin/crew/templates/config.template.json plugin/crew/templates/global.template.json`, parse the template's leaves and read `git show <c>:plugin/crew/.claude-plugin/plugin.json`'s version. A key's `since` is the version at its first appearance. For keys present in e9bf1438, the first template, write the string `"<=0.11.0"`. Paste the per-version counts into the Step 8 CHANGELOG entry (the probe on 1e0706ac gave 58 at 0.11.0, and 123 leaves ever declared).
- [ ] Tests:
  - `test_since_is_a_version_no_newer_than_the_plugin`: parses `plugin/crew/.claude-plugin/plugin.json`. Allows `None` and `<=0.11.0`.
  - `test_code_branch_values_agree_with_the_reader`, parametrised:
    - `autopilot.mode`: each declared value through `crew_autopilot.settings` on a temp repo, where only `plan` arms, plus `"Plan"`, which must not arm;
    - `autopilot.maxPhases`: `1` and `12` are kept, while `0` and `"12"` give 12 with a warning;
    - `resume.auto`: through `crew_resume.settings`, where repo `true` with the global absent is off, and global `true` is on;
    - `context.autoClear.enabled`: through `crew_autocycle.settings`, with the same four cases.
  - `test_prose_values_appear_in_their_source`: every value of a `prose` row appears backticked in `source`.
- [ ] Add `COMING`: a tuple of rows with the `KEY_META` shape plus `ticket`, `default` and `change` (`new key` or `changes <what>`). Fill it from each spec cited in the spec's Evidence, re-reading every spec now. T-0019/T-0012 are being amended, and T-0045 moved to spec. `coord.*` says "layer: set when T-0030 lands", and `resume.typeDelaySeconds` says "default: measured by T-0013".
- [ ] Tests:
  - `test_no_coming_key_is_in_code`: its failure message names the key and ticket and says "move this row to KEY_META and set since".
  - `test_coming_rows_name_a_ticket`: matches `^T-\d{4}$`.
  - `test_coming_changes_name_an_existing_key`: a `changes` row's key must be in `KEY_META`, as in T-0028's `qa.order`.
- [ ] Run the Test command. It must be green.

### Step 3: the generator, and CONFIG.md's generated block
Files: docs/guides/crew/src/config_reference.py, docs/guides/crew/src/configuration-reference.md, plugin/crew/CONFIG.md, scripts/_test/config-reference.py
Test: python3 docs/guides/crew/src/config_reference.py --check; python3 scripts/_test/config-reference.py; python3 -m pytest plugin/crew/tests/test_change_command.py plugin/crew/tests/test_promote_merge_gate.py -q -p no:cacheprovider
Risk: med. A generator that reads the user's config would make the committed file machine-dependent, and a `--check` that swallows an import error would pass as current.
- [ ] Write `scripts/_test/config-reference.py` first, in the `self-claims.py` style: throwaway temp copies, never the real tree.
  - Must-block:
    - the reference edited by one byte;
    - a changed default in a copied `crew_state.py`;
    - a hand edit inside CONFIG.md's block;
    - a missing end marker;
    - a generator whose import raises, which must exit non-zero with the error text, never 0.
  - Must-allow:
    - the unchanged copy;
    - an edit to CONFIG.md prose outside the block;
    - HOME pointed at a temp dir holding a `~/.claude/crew/config.json` that sets `qa.provider`, which must give the same output.
- [ ] Write `docs/guides/crew/src/config_reference.py`, stdlib only. It imports `crew_config`, `crew_guards` and `crew_keys` via `sys.path`, with `sys.dont_write_bytecode = True`, and never calls `read_global_config` or `load_config`.
  - `render_reference()` returns the full Markdown:
    - a header saying it is generated and naming the command;
    - one section per top-level block, with rows of key, layer, default (JSON), allowed values (or "not validated - read by <source>"), since, and summary;
    - a "Layers" preamble that explains `repo`, `both`, ratchet, widening-warned, `machine-arms` and `machine-only`;
    - "Coming (not in code yet)", grouped by ticket;
    - generated counts (keys, global-settable, repo-only).
  - `render_config_block()` returns the compact table for CONFIG.md: key, layer, default and values, plus a link to the repo copy of the full reference.
  - `--write` writes both files. Build each text in full before opening any file (root CLAUDE.md, the truncating-`open` landmine), and write with `newline="\n"`. `--check` exits 1 naming each stale file, and 2 on any exception, with the message.
- [ ] In `plugin/crew/CONFIG.md`, replace sections 10 and 11's tables with `<!-- generated:config-keys begin -->` / `<!-- generated:config-keys end -->` and the generated block. Keep one prose line per section that says the table is generated and how to regenerate it. Delete the stale counts at `:214`, `:636-639` and `:740`, since the generated block states them. Leave every other section byte-identical: `git diff` must touch only those regions.
- [ ] Run `config_reference.py --write` and commit the two outputs. Run the Test command. It must be all green.
- [ ] Sabotage by hand in a scratch copy: make `--check` return 0 unconditionally, and the must-block cases must go red. Revert. Make the block parser accept a missing end marker, and that case must go red. Revert.

### Step 4: the gate fails on a stale reference
Files: scripts/check-marketplace.py, scripts/_test/config-reference.py
Test: python3 scripts/check-marketplace.py; python3 scripts/_test/config-reference.py; python3 scripts/_test/self-claims.py
Risk: med. The gate runs in CI and on every `plugin/**` change. A failure to import must be a problem, never a silent pass.
- [ ] Add `check_config_reference(fail)` after `check_self_claims` in `main` (`scripts/check-marketplace.py:1660`). It loads `docs/guides/crew/src/config_reference.py` via `importlib` (as `self-claims.py` loads the checker), calls its check function, and `fail()`s once per stale file, with the regenerate command. Any exception is a `fail()` carrying the exception text.
- [ ] Extend `scripts/_test/config-reference.py`: each must-block case also runs through `check_config_reference` against the temp root, and each must-allow case stays silent.
- [ ] Run the Test command. The gate must pass on the tree. Then sabotage by hand: replace the reference with its Step 3 output plus one line. The gate must fail naming `configuration-reference.md`. Restore with `git checkout --`, then re-run and confirm it is green.

### Step 5: the full guide
Files: docs/guides/crew/src/guide.md, docs/guides/crew/src/README.md, scripts/_test/crew-guide.py
Test: python3 scripts/_test/crew-guide.py
Risk: med. A guide that states an unlanded feature as present is the failure the owner asked to prevent. The citation check catches a dead path or a dead command, and the ticket-id rule catches an uncited promise it can see.
- [ ] Write `scripts/_test/crew-guide.py` first. It runs against `guide.md` and against temp copies for its own must-block cases.
  - (a) Every backticked token that looks like a repo path (contains `/` and a known extension, or ends in `/`) exists at HEAD (`git ls-files`, or a directory).
  - (b) Every `/crew:<name>` has `plugin/crew/commands/<name>.md`, unless the same line carries `T-\d{4}`.
  - (c) Every `T-\d{4}` in the guide appears in `crew_keys.COMING` or in the guide's own "What is coming" table.
  - (d) No line of the guide matches `\b\d+ (keys|settings)\b`, so the guide states no key count.
  - Must-block cases: a missing path, `/crew:nosuch`, an orphan ticket id, and a key count. Must-allow cases: `/crew:help (T-0025)` and a path in a fenced example block marked `text`.
- [ ] Write `docs/guides/crew/src/guide.md`, H1 "crew 1.0 - the full guide". It has one H2 per Intent topic, in this order:
  - what crew is and the four roles;
  - install and update;
  - init and migrate;
  - the lifecycle;
  - review, ledger and acceptance;
  - refresh artifacts;
  - guards;
  - autopilot today;
  - trackers;
  - multi-session work;
  - Windows;
  - troubleshooting;
  - what is coming;
  - where the settings are.

  Each section:
  - opens with the command or file it describes, using the Evidence anchors in the spec, cited by path without line numbers (CONFIG.md's rule at `plugin/crew/CONFIG.md:14-22`: symbols and paths survive edits, and line numbers do not);
  - covers the behaviour the owner sees, from those files;
  - links to the task guide that goes deeper.

  Troubleshooting takes its entries from `CLAUDE.md`'s Landmines and today's `.work/HANDOFF.md`, each with symptom, cause and fix:
  - a content change with no version bump;
  - `pwsh` not on Git Bash's PATH;
  - no `python3` in Git Bash;
  - CRLF from `write_text`;
  - `MSYS_NO_PATHCONV`;
  - BUDGETS.md outside Touch (T-0046);
  - review bundles too large to read (T-0046);
  - the account session limit killing agents;
  - snap pwsh crashing on start;
  - running `--accept` from the wrong checkout ("tree has changed");
  - `/reload-plugins` after an update.

  "Where the settings are" links the reference and names the two files and `/crew:config`, with no key counts.
- [ ] Add rows for the guide and the configuration reference to `docs/guides/crew/src/README.md`'s guide table (`:9-16`) and its "Built artifacts" table.
- [ ] Run the Test command. It must be green.

### Step 6: build both documents, and the freshness check
Files: docs/guides/crew/src/build.py, docs/guides/crew/crew-1.0-guide.html, docs/guides/crew/crew-1.0-guide.docx, docs/guides/crew/crew-1.0-guide.pdf, docs/guides/crew/crew-1.0-configuration-reference.html, docs/guides/crew/crew-1.0-configuration-reference.docx, docs/guides/crew/crew-1.0-configuration-reference.pdf, docs/guides/crew/crew-1.0-troubleshooting.html, docs/guides/crew/crew-1.0-troubleshooting.docx, docs/guides/crew/crew-1.0-troubleshooting.pdf, scripts/_test/crew-guide.py
Test: python3 docs/guides/crew/src/build.py --check; python3 scripts/_test/crew-guide.py
Risk: low for the build, because the path is the existing one. It is med for the check: a `--check` that exits 0 when `markdown` is missing would report "current" having compared nothing.
- [ ] Add `"guide": ["guide.md"]` and `"configuration-reference": ["configuration-reference.md"]` to `GUIDES` (`build.py:68-74`). Update the `--guide` help text, which says "all five".
- [ ] Add `--check`. For every guide, build the HTML in memory exactly as `build_one` does, but write nothing. Compare it with the committed `crew-1.0-<name>.html`, print each stale name, and exit 1. `import markdown` moves inside a function, so a missing module exits 2 with "markdown not importable - the check DID NOT RUN". Build the text before opening, as in Step 3.
- [ ] Add to `scripts/_test/crew-guide.py`: `build.py --check` exits 0 on the tree; a temp copy with one character changed in `guide.md` exits 1; and a run with `markdown` hidden (a `sys.modules` stub raising `ImportError`, via `-c`) exits 2.
- [ ] Run `python3 docs/guides/crew/src/build.py --guide guide`, then `--guide configuration-reference`, then `--guide troubleshooting` (D5). Each writes HTML, DOCX and PDF through LibreOffice. Check each `fenced ... OK` line, open the PDFs, and confirm the tables are not clipped: the reference's six-column table is the risk, and `_NARROW_HEADERS` (`build.py`) is the known fix pattern. Commit.
- [ ] Run the Test command. It must be green.

### Step 7: sabotage mutations and the verify rule
Files: plugin/crew/tests/sabotage_keys.py, plugin/crew/tests/sabotage.py, .crew/verify.json
Test: python3 plugin/crew/tests/sabotage.py
Risk: med. A mutation whose `find` string is absent or not unique is a harness error, not a red. `sabotage.py` refuses to run on a stale `.bak`.
- [ ] Create `plugin/crew/tests/sabotage_keys.py` with `KEYS_MUTATIONS`, in the `(label, target, find, replace, test)` shape. One mutation per pytest check, each targeting the branch in `crew_keys.problems()` or the helper the test drives:
  - missing-row detection off -> `test_every_leaf_has_a_row`;
  - orphan detection off -> `test_no_orphan_rows`;
  - a copied tuple instead of the reference, for `pm.authority` -> `test_tuple_backed_values_are_the_same_object`;
  - `values_of` returns a row's own values for a ratcheted key -> `test_ratcheted_rows_do_not_restate_tiers`;
  - the version comparison inverted -> `test_since_is_a_version_no_newer_than_the_plugin`;
  - COMING-in-code detection off -> `test_no_coming_key_is_in_code`;
  - `layer_of` ignores `layer_rule` -> a new `test_machine_arms_keys_render_as_machine_arms`.
- [ ] Register it: add `from sabotage_keys import KEYS_MUTATIONS` beside `sabotage.py:77`, and `+ KEYS_MUTATIONS` in the `MUTATIONS +=` at `:3047-3049`. Update the comment at `:3044-3046`.
- [ ] Add a `.crew/verify.json` rule after `:281-288`. Paths: `plugin/crew/hooks/scripts/crew_keys.py`, `plugin/crew/hooks/scripts/crew_config.py`, `plugin/crew/hooks/scripts/crew_state.py`, `plugin/crew/hooks/scripts/crew_guards.py`, `plugin/crew/tests/test_crew_keys.py`, `plugin/crew/tests/sabotage_keys.py`, `docs/guides/crew/**`, `scripts/_test/config-reference.py` and `scripts/_test/crew-guide.py`. Run:
  - `python3 -m pytest plugin/crew/tests/test_crew_keys.py -q`;
  - `python3 docs/guides/crew/src/config_reference.py --check`;
  - `python3 scripts/_test/config-reference.py`;
  - `python3 docs/guides/crew/src/build.py --check`;
  - `python3 scripts/_test/crew-guide.py`.

  `reach: local`. The `why` says the HTML check is local-only (CI lacks `markdown`) and DOCX/PDF are not compared. Measure `seconds` by running it, and state the host and load.
- [ ] Run `python3 plugin/crew/tests/sabotage.py`. Every new mutation must report red on its named test, and no `.bak` may remain. Report the wall time, and quote any failure verbatim.

### Step 8: bookkeeping, refresh, review, then land with the version
Files: plugin/crew/BUDGETS.md, CHANGELOG.md, plugin/crew/.claude-plugin/plugin.json, .claude-plugin/marketplace.json, plugin/PLUGINS.md, .crew/verify.json, plugin/crew/hooks/scripts/crew_keys.py, docs/guides/crew/src/configuration-reference.md, plugin/crew/CONFIG.md, docs/guides/crew/crew-1.0-configuration-reference.html, docs/guides/crew/crew-1.0-configuration-reference.docx, docs/guides/crew/crew-1.0-configuration-reference.pdf
Test: python3 scripts/check-marketplace.py; python3 -m pytest plugin/crew/tests/test_crew_keys.py plugin/crew/tests/test_crew_config.py -q -p no:cacheprovider; python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket T-0048
Risk: med. Content with no version bump never reaches an installed copy, and a refresh written after review stales the receipt.
- [ ] Re-measure `plugin/crew/BUDGETS.md:11` (`git ls-files 'plugin/crew/*.md'` line total and file count) so `check_self_claims` passes. Skip this if T-0046 has landed and passes it.
- [ ] Under `CHANGELOG.md`'s `## [Unreleased]`, add "`crew` <version>: the full guide and a generated configuration reference (T-0048)". It names `crew_keys.py`, the COMING section and its tickets, the gate check, the CONFIG.md block, and the troubleshooting rebuild. It also carries the Step 2 backfill counts and the Step 7 mutation count.
- [ ] Re-time the `scripts/**` rule (`.crew/verify.json:80-92`) and the new rule, and update their `seconds` and `why` if they moved.
- [ ] Run the Test command and the new verify rule. Record pass counts with the commit sha. Then run `crew_refresh_check.py --root . --ticket T-0048` and each `refresh with` command it prints (`/crew:onboard --refresh <subsystem>`, `/crew:diagram refresh`, `graphify update .`, waiting for the background rebuild log to stop growing first), committing each, per `plugin/crew/commands/implement.md:92-97`. That comes before `/crew:review T-0048`.
- [ ] Commit, then run `/crew:review T-0048` and report its BLOCK and FIX lines verbatim. Accepting is the owner's.
- [ ] On the land branch:
  - Set crew one patch above `git show origin/main:plugin/crew/.claude-plugin/plugin.json`'s version in `plugin.json`, `marketplace.json` (crew entry) and `plugin/PLUGINS.md:14`, and in the CHANGELOG headline.
  - If any COMING key landed on main meanwhile, move its row (`test_no_coming_key_is_in_code` names it), set its `since`, and re-run `config_reference.py --write` and the Step 6 build of the reference.
  - Run `python3 scripts/check-marketplace.py`, then merge with `gh pr merge --merge`.
  - Tell the main session the two HTML paths for the shared-page publish.
