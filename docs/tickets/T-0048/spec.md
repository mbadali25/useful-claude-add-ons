# T-0048 full crew 1.0 guide and a generated configuration reference          status: spec   risk: med   priority: high
## Intent
Two new documents in `docs/guides/crew/`, built the way the existing five guides are built.

The first is a full crew 1.0 guide. It covers what crew 1.0 is and its four roles; install and update; `/crew:init` and `/crew:migrate`; the lifecycle (brainstorm, spec, plan, approve, implement, review, done), with the approval receipt and why an edit stales it; review rounds, the ledger, successor plans and owner acceptance; refresh artifacts; the scope, cloud and promote guards, with what each can and cannot see; `/crew:autopilot` as it is in 1.0.41 and what arrives with which ticket; trackers (files, Obsidian); multi-session work; Windows notes; and troubleshooting drawn from this repo's real failures. Each section cites the command or file it describes. Every statement about a feature that has not landed carries its ticket id.

The second is the configuration guide, a separate document (owner, 2026-09-26). It opens with short task-oriented prose: how the repo and global layers combine, how to read `crew_config.py` output, and the common setups (global defaults, self-approval, notify). Then comes the reference generated from code. It lists every key with its allowed values, its default, which layer may set it (repo, global or both, and whether it ratchets) and the version it arrived in. A separate "coming" section lists the keys of approved tickets that have not landed, each with its ticket id. The allowed values, summaries and arrival versions come from one new declarative table, `crew_keys.py`. Validators and the generator read the same value tuples wherever such a tuple exists. `scripts/check-marketplace.py` fails when the committed reference, or the generated block in `plugin/crew/CONFIG.md`, is stale. A test fails when a "coming" key is already in the code.
## Exclusions
- No config key is added, removed, renamed or re-defaulted. `default_config()` and `default_global_config()` return exactly what they return on origin/main. The leaf count stays 119 (`test_crew_config.py:275`).
- No validator or reader changes behaviour. `crew_autopilot.settings`, `crew_resume.settings`, `crew_autocycle.settings`, `crew_platform.concerns`, `crew_config.validate_providers` and the `normalise_*` functions are read, never edited (D3).
- No layer rule changes. Making `autopilot` settable globally is T-0050.
- CONFIG.md's prose sections (1-9, 12-20) keep their text. Only the key tables in sections 10 and 11, and the counts that describe them at `:214`, `:636-639` and `:740`, give way to the generated block (D2).
- No publish to a shared web page. The main session does that after landing, not this ticket's code.
- The five existing guide sources are not edited. The troubleshooting guide's built files are rebuilt from its unchanged source only if D5 is taken.
- No check that reads `.work/` (it is ignored, and CI has no copy). A COMING row's ticket id is checked for shape only.
- The HTML freshness check does not run in CI: `markdown` is not installed in CI's pylint job (`.pylintrc:59-64`). It runs from `.crew/verify.json`. DOCX and PDF are not compared, because LibreOffice output is not byte-stable. That is stated in the reference and the verify rule, not implied away.
## Evidence
All line numbers are from origin/main at `1e0706ac` (crew 1.0.41), read through a clean checkout of that commit on 2026-09-26.
- How the guides are built: `docs/guides/crew/src/build.py`. python-markdown (`import markdown`, `:52`) turns Markdown into HTML. `house_style.apply_to_html` from `skills/doc-builder/scripts` (`:57`) restyles it, and `render_engine.to_soffice` (LibreOffice) converts it to DOCX and PDF (`:240`). Usage: `build.py`, `build.py --guide <name>`, `build.py --html-only` (`:39-42`). The `GUIDES` table (`:68-74`) maps each output name to its sources, parent first. Output goes to `docs/guides/crew/crew-1.0-<name>.{html,docx,pdf}` (`:228`). The theme is `midnight` and the brand `neutral` (`docs/guides/crew/src/README.md:32`). The guide index table is `docs/guides/crew/src/README.md:9-16`.
- The HTML build is deterministic. On a `git archive` of origin/main, `build.py --html-only` reproduced `crew-1.0-quickstart.html` and `crew-1.0-daily-workflow.html` byte for byte. `crew-1.0-troubleshooting.html` differs from line 448: the committed file lacks the "Auto-Clear Did Nothing on Windows" section, which its source has. The last commit to its sources was ea697b95 (D5).
- CI cannot import `markdown`: `.pylintrc:59-64`.
- The claim rule: `CLAUDE.md:28` ("A number this repo states about itself gets a marker, or it is not checked"). The checker is `scripts/check-marketplace.py:673` (`check_self_claims`), with `CLAIM_RE` at `:554` and `BIND_WINDOW = 12` at `:561`. Unmarked numbers are deliberately unchecked, and `scripts/_test/self-claims.py` asserts that. So the hand-written guide states no key counts. The generated reference states counts, and the staleness check re-derives the whole file, which covers them.
- The gate runs every check in `main` (`scripts/check-marketplace.py:1639-1663`). A new `check_config_reference(fail)` goes in that list.
- The key set: `default_config` `plugin/crew/hooks/scripts/crew_config.py:239`, `default_global_config` `:378`, `leaf_paths` `:542` (a list or an empty dict is one leaf), `filter_global` `:653`, `is_global_path` `:676`. Run with `python3 -I -S` and a nonexistent HOME, the modules import with the standard library only, and `leaf_paths(default_config())` has 119 entries, 66 of them global-settable.
- The ratchet is declarative: `crew_guards.RATCHETED_KEYS` `plugin/crew/hooks/scripts/crew_guards.py:489-509` holds `(tiers, normalise, rank)` for `install.policy`, all ten `guards.*` (`ALL_GUARD_NAMES` `:194`, `GUARD_DEFAULTS` `:197`) and `change.requireForProduction`. `ratchet_spec` is at `:512`, and `resolve_ratcheted` at `crew_config.py:790`. `pm.authority` ratchets only for the widening warning (`crew_config._RATCHETED` `:2357`; comment `crew_guards.py:485-488`). The generator shows the difference.
- Value tuples that validators already read: `AUTHORITIES` `plugin/crew/hooks/scripts/crew_state.py:1058`, `TICKET_GRANULARITIES` `:1093`, `DEV_PROVIDERS`/`QA_PROVIDERS` `:1429-1430` (read by `validate_providers`, `crew_config.py:175-236`), `crew_ticket.MODES` `plugin/crew/hooks/scripts/crew_ticket.py:137`, and `_AUTOCLEAR_METHODS` `plugin/crew/hooks/scripts/crew_platform.py:373-378` (per OS).
- Values held only in code branches: `autopilot.mode` is armed only by `mode == "plan"` (`plugin/crew/hooks/scripts/crew_autopilot.py:602`, in `settings` `:592`). `autopilot.maxPhases` must be a positive int (`:606-609`). `resume.auto` is `crew_resume.settings` `plugin/crew/hooks/scripts/crew_resume.py:158`. `context.autoClear.enabled` is `crew_autocycle.settings` `plugin/crew/hooks/scripts/crew_autocycle.py:137`.
- Values held only in prose: `qa.codex.reasoningEffort` is listed at `plugin/crew/commands/review.md:443`. `grep -nE 'METHODS|_MODES|TRACKERS|PRESETS|THEMES' plugin/crew/hooks/scripts/*.py` finds only `crew_platform.py:373`. So `tracker`, `memory.mode`, `pm.mode`, `secondOpinion.*`, `notify.*`, `graph.mode`, `graph.tool`, `sdp.noteVisibility`, `bitbucket.mergeGate.preset` and `docs.*` have no declared tuple. The reference marks them "not validated".
- Layer rules the code states declaratively: `AUTOCLEAR_CONSENT_KEYS` `crew_state.py:705` and `AUTOCLEAR_MACHINE_ONLY_KEYS` `:717`. Rules held only in code: machine-armed, where a repo may only veto (`resume.auto`, `RESUME_DEFAULTS` `:692`, and `context.autoClear.enabled`, `AUTOCLEAR_DEFAULTS` `:654`, both commented at `:654-697`).
- Arrival versions: no declarative source exists. A read-only probe walked every commit touching `plugin/crew/templates/config.template.json` (21 commits, first e9bf1438, 2026-08-27) and `global.template.json`, reading `plugin/crew/.claude-plugin/plugin.json`'s version at each. It found 123 leaves ever declared (119 now, plus removed ones such as `graph.obsidian.*`). 58 first appear at 0.11.0, the first template's version, which means "0.11.0 or earlier". No commit had an unreadable version.
- CONFIG.md drift: `plugin/crew/CONFIG.md:214` says "44 global-settable keys". `:636-639` heads the table "66" and says it lists 63 (63 rows). `:740` says "all 41" (47 rows). Measured: 66 and 53. CONFIG.md's own precedent for a drifting copy is to stop hand-copying it (`:806-825`, section 12.1). Tests that read CONFIG.md read prose sections only: `plugin/crew/tests/test_change_command.py:366-374` (section 17) and `plugin/crew/tests/test_promote_merge_gate.py:314` (section 8).
- CONFIG.md ships with the plugin and `docs/` does not: `.claude-plugin/marketplace.json:216` (`"source": "./plugin/crew"`). `plugin/crew/README.md:1089` names CONFIG.md as the full key reference.
- `plugin/crew/*.md` line totals are claim-checked: `plugin/crew/BUDGETS.md:10-11` (`crew-markdown-lines`, 18,176). An edit to CONFIG.md moves that number. T-0024, T-0023 and T-0042 stopped on this with BUDGETS.md outside Touch (`.work/HANDOFF.md:50`, `:88`).
- Coming keys, from the specs (`.work/tickets/<id>/spec.md`):
  - T-0010 `:53`: `autopilot.approval` and `autopilot.questions`, values `human|self|risk`, default `risk`.
  - T-0011 `:50`: `autopilot.ship` `pr|merge` (default `merge`), `autopilot.knownFailures` (`[]`), `autopilot.ciTimeoutMinutes` (60).
  - T-0029 `:6`, `:11`, `:100`: `autopilot.maxLanes` (default the resolved `pm.maxDispatches`, lower only) and `autopilot.reviewPolicy` `stop|clean-only|fix-and-rereview` (default `stop`).
  - T-0045 `:109`: `autopilot.deploy` `none|nonprod` (default `none`).
  - T-0009 `:48`: `guards.deployWorkflow` (default `block`, ratcheted) and `environments.workflows` (`{}`, repo only).
  - T-0005 `:58` and plan `:39-40`: `environments.nonProd` (`[]`, repo only) and `environments.prodUnattended` (false, ratcheted, true only in both layers).
  - T-0023 `:9`, `:61`: `route.enabled` (false, both layers, only exactly `true`).
  - T-0012 `:66`: `autopilot.maxTicketsPerRun` (3) and `autopilot.maxTokensPerSession` (2,000,000).
  - T-0013 `:63`: `resume.typeDelaySeconds` (measured) and `resume.readyTimeoutSeconds` (15), machine-global.
  - T-0017 `:3`, `:136`: `context.autoClear.wrapUp` (default null, machine opt-in).
  - T-0028 `:7-8`, `:69`: `qa.kimi.model` and `dev.kimi.model` (null), plus changes to existing keys: `kimi` joins the provider values, and the `qa.order` default becomes `["codex", "kimi", "copilot", "claude"]`.
  - T-0030: `coord.ttlMinutes` (30, finite, 1-10080; plan `:47`, `:123`) and `coord.channel` (plan `:97`). The spec states no layer (`:18`).
  - Status of each: `.work/INDEX.md:5`, `:10-14`, `:18`, `:24`, `:27-29`, `:44`.
- Guide anchors:
  - Roles: `plugin/crew/README.md:1919-1935`. Install and update: `README.md:225` (`claude plugin marketplace update`), `docs/guides/crew/src/troubleshooting.md:20-47` (`claude plugin update`, restart), `plugin/crew/README.md:276` (`/reload-plugins`).
  - Init and migrate: `plugin/crew/commands/init.md`, `plugin/crew/commands/migrate.md:1-12`.
  - Approval receipt: `plugin/crew/hooks/scripts/crew_ticket.py:30-50`, `plugin/crew/commands/approve.md:20-22`. A status edit keeps the receipt (`plugin/crew/commands/implement.md:108`, `STATUS_VALUES` `crew_ticket.py:143`).
  - Refresh: `implement.md:92-97`. Review budget and successor plans: `plugin/crew/hooks/scripts/review_ledger.py:17-21`, `:57-63`, `:80`. Owner acceptance: `plugin/crew/commands/review.md:507-509`.
  - Guards: scope, `plugin/crew/hooks/scripts/scope_guard.py:1-12`, `:48-57`; the completion audit's blind spots, `completion_audit.py:29-31`; cloud, `cloud_guard.py:14`, `:49-56`; promote, `promote-gate.sh:1-20`.
  - Autopilot: `plugin/crew/commands/autopilot.md:13`, `:84-88`, and `plugin/crew/CONFIG.md:2044-2069`.
  - Trackers: `crew_config.py:265`, `plugin/crew/commands/obsidian-sync.md`. Multi-session: `crew_state.py:2817`, `:2847`, `README.md:1929-1935`, `CLAUDE.md:306`.
  - Windows and troubleshooting: `CLAUDE.md:157-214` (landmines), `.work/HANDOFF.md:47`, `:53`, `:82-89`.
- Tests and gate plumbing: sabotage siblings register at `plugin/crew/tests/sabotage.py:67-77` and `:3044-3049`, with tuple shape `(label, target, find, replace, test)` (`plugin/crew/tests/sabotage_autopilot.py:1-5`). The docs verify rule is `.crew/verify.json:69-78`. The crew_config rule is `:117-127`, and the gate rule `:53-59`.
- Version: crew 1.0.41 at `plugin/crew/.claude-plugin/plugin.json:3`, `.claude-plugin/marketplace.json:218` and `plugin/PLUGINS.md:14`. `CHANGELOG.md:5` is `## [Unreleased]`.
## Unknowns
- D1-D7 are the owner's, in `direction.md`, each with a recommendation. This spec and plan assume every recommendation is taken. If D5 is declined, the three troubleshooting bullets leave Touch and Step 6 skips the rebuild. If D6 is declined, the `.docx` and `.pdf` bullets leave Touch.
- The version is set on the land branch: one patch above origin/main's crew version at land time. T-0011-build and T-0018 already carry 1.0.42 on their branches.
- COMING rows follow the specs as they read today. A spec amended before T-0048 lands (T-0019/T-0012 are being amended, per `.work/HANDOFF.md`) is re-read at Step 2. T-0030 states no layer for `coord.*`, so the row says "layer: set when T-0030 lands", never a guess.
- T-0050 will change layers. The generated layer column follows the code, and T-0050's own land regenerates the reference.
- `resume.typeDelaySeconds` has no default until T-0013 measures it. Its COMING row says "measured by T-0013".
- Whether the whole `scripts/**` verify rule (81 s) stays within the Stop budget with the two new scripts: re-timed at Step 8.
## Touch
- `plugin/crew/hooks/scripts/crew_keys.py`
- `plugin/crew/tests/test_crew_keys.py`
- `plugin/crew/tests/sabotage_keys.py`
- `plugin/crew/tests/sabotage.py`
- `plugin/crew/CONFIG.md`
- `plugin/crew/BUDGETS.md`
- `docs/guides/crew/src/config_reference.py`
- `docs/guides/crew/src/configuration-reference.md`
- `docs/guides/crew/src/guide.md`
- `docs/guides/crew/src/build.py`
- `docs/guides/crew/src/README.md`
- `docs/guides/crew/crew-1.0-guide.html`
- `docs/guides/crew/crew-1.0-guide.docx`
- `docs/guides/crew/crew-1.0-guide.pdf`
- `docs/guides/crew/crew-1.0-configuration-reference.html`
- `docs/guides/crew/crew-1.0-configuration-reference.docx`
- `docs/guides/crew/crew-1.0-configuration-reference.pdf`
- `docs/guides/crew/crew-1.0-troubleshooting.html`
- `docs/guides/crew/crew-1.0-troubleshooting.docx`
- `docs/guides/crew/crew-1.0-troubleshooting.pdf`
- `scripts/check-marketplace.py`
- `scripts/_test/config-reference.py`
- `scripts/_test/crew-guide.py`
- `.crew/verify.json`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
## Acceptance checks
- [ ] `crew_keys.py` has one row per leaf of `default_config()` and `default_global_config()`, and none for anything else. `test_every_leaf_has_a_row` and `test_no_orphan_rows` are green, and each goes red when one row is deleted or one extra row is added.
- [ ] A row for a ratcheted key does not restate its tiers. The reference shows `RATCHETED_KEYS`' tiers and marks the key "ratchet: narrower layer wins" (`change.requireForProduction`: "a repo may turn it on, never off"). `pm.authority` is marked "widening warned, precedence". Tested.
- [ ] Every value tuple a validator reads is the same object in the row (`is`, not `==`): providers, authorities, granularities, scope modes, auto-clear methods. For `autopilot.mode`, `autopilot.maxPhases`, `resume.auto` and `context.autoClear.enabled`, every declared value and one undeclared value go through the real reader, and the reader's answer matches the row. For a value taken from prose, every declared value appears backticked in the named source file (`review.md` for `reasoningEffort`). Keys with no validator read "not validated" in the reference.
- [ ] Every row's `since` is a version no newer than `plugin.json`'s, or `None`, which renders as "unreleased". Keys in the first template read "0.11.0 or earlier". The backfill command and its output summary are recorded in the CHANGELOG entry.
- [ ] `test_no_coming_key_is_in_code` is green. With one COMING key added to `AUTOPILOT_DEFAULTS` in a scratch copy, it fails and names the key and its ticket. Every COMING row names a ticket id matching `T-\d{4}`.
- [ ] The crew guide's autopilot section is a short summary (what autopilot is, `mode: plan`, what always stops for a person) that links to the separate autopilot guide, T-0054; the worked examples live there, not here (owner, 2026-09-26: "a full crew autopilot guide and also a configuration guide. Those should be separate documents").
- [ ] `python3 docs/guides/crew/src/config_reference.py --check` exits 0 on the committed tree. It exits 1 naming the file when `configuration-reference.md` or CONFIG.md's generated block differs by one byte, and when a key's default changes. Its output is the same with HOME pointed at a directory holding a global config.
- [ ] `python3 scripts/check-marketplace.py` passes, and fails through `check_config_reference` in each must-block case of `python3 scripts/_test/config-reference.py`: stale reference, hand edit inside CONFIG.md's block, missing markers, and generator import error (reported as a failure, never a skip). The must-allow cases pass: unchanged tree, and an edit to CONFIG.md prose outside the block. Each check was sabotaged by hand and went red.
- [ ] `docs/guides/crew/src/guide.md` has the sections listed in the Intent, each citing a command or file. `python3 scripts/_test/crew-guide.py` passes. It fails on a backticked repo path that does not exist, on a `/crew:<name>` with no `plugin/crew/commands/<name>.md` whose line carries no ticket id, and on any `T-\d{4}` id missing from the reference's COMING section or the guide's "What is coming" table. The guide states no key count.
- [ ] `python3 docs/guides/crew/src/build.py --check` rebuilds every guide's HTML in memory and exits 0. It exits 1 naming the guide when a committed HTML differs, and 2 when `markdown` cannot be imported, never 0. `crew-1.0-guide.*` and `crew-1.0-configuration-reference.*` are committed as HTML, DOCX and PDF. The troubleshooting HTML is rebuilt (D5). `docs/guides/crew/src/README.md` lists both new documents in its guide and built-artifact tables.
- [ ] CONFIG.md's sections 10 and 11 are the generated block. `:214`'s "44" and the "66"/"all 41" headings are gone. The prose sections are unchanged, and `test_change_command.py` and `test_promote_merge_gate.py` pass.
- [ ] `.crew/verify.json` has a rule mapping `crew_keys.py`, `crew_config.py`, `crew_state.py`, `crew_guards.py`, the new tests and `docs/guides/crew/**` to the pytest file, `config_reference.py --check`, `build.py --check` and the two `scripts/_test` suites, with a measured `seconds`.
- [ ] `sabotage_keys.py` holds one mutation per pytest check above, registered in `sabotage.py`. `python3 plugin/crew/tests/sabotage.py` reports each red on its named test.
- [ ] The land branch sets crew one patch above origin/main in `plugin.json`, `marketplace.json` and `PLUGINS.md`, with a CHANGELOG entry, and re-measures `BUDGETS.md`. `python3 scripts/check-marketplace.py` passes after that.
