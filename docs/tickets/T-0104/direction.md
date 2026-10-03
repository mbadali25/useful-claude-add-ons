# T-0104 direction - crew webtest scaffold (plugin/crew/hooks/scripts/webtest_scaffold.py, /crew:init Phase 6, /crew:webtest)

Status: APPROVED 2026-09-29T10:02:35Z under the owner's standing approval authority (Matthew Badali,
2026-09-26 "no longer ask me for approvals. You can self-approve"; 2026-09-27 "You should have the
authority to approve these"; this run's go 2026-09-29 ~05:15 CDT, verbatim in ## Ask). Every open
question below takes its written recommendation, as that authority provides.

## Ask
Owner Matthew Badali, 2026-09-29 ~05:15 CDT, verbatim: "@aws-ops reporting gizmo duck plugin issues please take that, and address them at the same time as this , put them in a workflow brainstorm -> spec -> approve -> implement -> fix -> gate -> land"

## Report (verbatim, from the aws-managed-services "automation" session (crew 1.0.59, gizmoduck 0.5.3), found 2026-09-28/29, relayed cross-session 2026-09-29 ~05:10 CDT; its line numbers are the reporter's at crew 1.0.59 / gizmoduck 0.5.3 - re-verify against origin/main)
1. webtest_scaffold.py (hooks/scripts, detect() :138, plan() :239) only inspects --root, so a multi-module repo root reports "n/a - no playwright.config.*, angular.json, or Playwright in package.json" even though 3 modules have playwright.config.ts (fileshare-audit, terraform-workspace-management, security-ops-dashboard). /crew:init Phase 6 gives no way to point it at modules.
2. webtest_scaffold.py dry run exits 1 whenever an existing config is MISSING the setup/axe/visual projects (:368 `"MISSING" not in note`), but --apply never adds them (config is "kept") - so the gap it reports is one it can never close, and the dry run is always red on a repo with an existing config.
3. It writes tests/auth.setup.ts, tests/fixtures/axe.ts, tests/home.axe.spec.ts without reading the existing config's testDir - all three modules use testDir './e2e', so the files would never be collected. In security-ops-dashboard tests/ already holds a Terraform harness (tests/cognito-guards/main.tf).
4. It writes an auth setup project even when no credentials/.crew/secrets.md exist (federated-only Cognito apps) - the setup project fails and every dependent spec with it. A 'visual' project + snapshotPathTemplate {platform} orphans existing baselines named after the chromium project.
5. It writes .mcp.json / .codex/config.toml / .claude/agents into the --root dir; for a module subdir those are never loaded by a session started at the repo root.

## Verification against origin/main (2693d0fa, crew 1.0.59)

Every item reproduces. Line numbers are unchanged from the reporter's: `detect()` is
`plugin/crew/hooks/scripts/webtest_scaffold.py:138`, `plan()` `:239`, the exit gate `:368`.
Method: `git archive origin/main plugin/crew/hooks/scripts` into a scratch dir, a fixture of three
modules each with `playwright.config.ts` (`testDir: './e2e'`, one `chromium` project) and
`mod-c/tests/cognito-guards/main.tf`; `--apply` runs imported the module with
`run_agents.__defaults__` stubbed so no `npx` ran. Then a read-only dry run (default mode, writes
nothing; `git status --porcelain | wc -l` 4349 before and after, all pre-existing) on the reporter's
real repo `/repos/solomon/aws-managed-services`.

1. REPRODUCES. Fixture root: `webtest scaffold: n/a - no playwright.config.*, angular.json, or
   Playwright in package.json` / exit 0. Real repo root: the same line, exit 0. `detect()` reads
   `os.listdir(root)` only. `plugin/crew/commands/init.md:27` and `:33` pass `--root .` and nothing
   else; there is no module argument.
2. REPRODUCES. Module dry run: `keep    playwright.config.ts: exists - kept, but MISSING 'setup'
   project; 'axe' project; 'visual' project; the visual project's gate on
   mcr.microsoft.com/playwright:v1.63.0-noble -- add them (the verify rules run these projects)`,
   exit 1. Two consecutive `--apply` runs on the fixture print the same MISSING line and leave the
   config byte-identical (`diff` empty) - the gap is never closed and never closable by the tool.
   (The same runs also exit 1 on `FAILED  init-agents left ... missing`; that is the stub writing no
   agent files, not a finding.) Real `security-ops-dashboard`: identical MISSING line, exit 1.
3. REPRODUCES. All three real configs carry `testDir: './e2e'`
   (`fileshare-audit/playwright.config.ts:71`, `security-ops-dashboard/playwright.config.ts:54`,
   `terraform-workspace-management/playwright.config.ts:24`). `plan()` hard-codes
   `tests/auth.setup.ts`, `tests/fixtures/axe.ts`, `tests/home.axe.spec.ts` (`:248-250`); the
   fixture apply wrote all three into `mod-c/tests/` beside `tests/cognito-guards/main.tf`. Real
   `security-ops-dashboard/tests/` holds `cognito-guards`.
4. REPRODUCES, both halves. (a) `AUTH_SETUP_TS` is written whenever absent; nothing reads
   `.crew/secrets.md` or any credential source (`git grep secrets.md origin/main -- plugin/crew`
   hits only docs: `README.md:611`, `commands/onboard.md:195`,
   `skills/crew-verification/credentials-and-playwright.md:13`). The real repo has no
   `.crew/secrets.md`. (b) Real baselines exist in Playwright's default layout named for the
   chromium project: `security-ops-dashboard/e2e/sign-in-gate.visual.spec.ts-snapshots/sign-in-gate-chromium-linux.png`,
   `sign-in-gate-narrow-chromium-linux.png`,
   `terraform-workspace-management/e2e/login.visual.spec.ts-snapshots/login-chromium-linux.png`.
   The scaffold's advice ("add a 'visual' project") plus `CONFIG_TS`'s
   `snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{platform}/...'` (`:69`) would
   look for them under `__screenshots__/visual/linux/...`, orphaning all three. The scaffold never
   writes into an existing config, so the orphaning happens through the advice it prints, not a
   write it makes - still a defect, since exit 1 pushes the user to follow it.
5. REPRODUCES as a write location. The fixture apply wrote `mod-c/.mcp.json` and
   `mod-c/.codex/config.toml`; `run_agents` runs `init-agents` with `cwd=root` (`:327`), so
   `.claude/agents/` lands in the module too. The real repo keeps its session config at the root
   (`/repos/solomon/aws-managed-services/.mcp.json` exists). NOT VERIFIED empirically: that a Claude
   Code or Codex session started at the repo root ignores a module's `.mcp.json` /
   `.codex/config.toml` / `.claude/agents/` - taken from the tools' documented project-root
   loading, not from a run.

Nearby, found while verifying (in scope because the fix changes them): `/crew:webtest`'s
precondition requires "A `playwright.config.*` at the root" and the seed `tests/seed.spec.ts`
(`plugin/crew/commands/webtest.md` section 0 and 1), so once agents live at the repo root and the
config in a module, `/crew:webtest` would refuse or point at the wrong seed. And
`plugin/crew/hooks/scripts/webtest_rules.py` emits rules that run `npx playwright test` and
`webtest_guard.py ... --root .` from the repo root, which for a module finds no config.

## Options

A. **Module-aware scaffold, additive-only kept (RECOMMENDED).**
   - Detection: at a root that is not itself a web project, look for modules (bounded depth, never
     inside `node_modules`, `.git` or other vendored/ignored dirs) carrying the same three markers;
     print each with the exact command to scaffold it, instead of `n/a`. `n/a` only when none exist.
   - A module argument (`--module <dir>`, relative to `--root`): module-scoped files (test files,
     `.gitignore` lines, reading the config) go under the module; session-scoped files
     (`.mcp.json`, `.codex/config.toml`, `.claude/agents/`) go at `--root`, the directory a session
     starts in, and whatever they point at (seed test, MCP server config) points into the module.
   - testDir: read the existing config's `testDir` string literal with `webtest_guard.tokens` and
     write the three test files under it. No `testDir` = Playwright's default (the config's own
     directory), so `tests/` still collects. A `testDir` that is not a literal is "could not tell":
     the test files are not written, and the line says why - never a silent fallback to `tests/`.
   - Gaps: an existing config's missing projects become an advisory `gap` line with a paste-ready
     snippet for each, and stop driving exit 1. Exit 1 stays for what the tool itself refused or
     failed. `/crew:init` Phase 6 proposes only the rules whose projects exist (rule 2 needs `axe`,
     rule 5 needs `visual`) and names the others as waiting on the gap.
   - Credentials: the auth setup file, and a fresh config's `setup` project, `storageState` and
     `dependencies: ['setup']`, are written only when `.crew/secrets.md` exists at `--root`;
     otherwise a `skip` line says no credentials are recorded, and `setup` is not reported as a gap.
   - Baselines: when `*-snapshots/` baselines exist under testDir, the visual snippet preserves
     their paths (no `{projectName}` change that orphans them); the fresh-config template is
     unchanged for repos with no baselines.
   - `/crew:webtest` accepts a module's config and seed; `webtest_rules.py` can emit rules scoped
     to a module.
   Tradeoff: touches the scaffold, two commands, the rules emitter and their docs in one ticket;
   moderate size, but every change is on the path the report walked and each item is testable with
   stubs (no network, no npx).

B. **Patch the existing config in place.** Close item 2 literally by inserting the missing
   projects into the user's `playwright.config.*`. Rejected: it ends "NEVER OVERWRITES"
   (`:10`), and rewriting arbitrary TypeScript with a tolerant tokenizer is the fragile case -
   a wrong splice breaks the suite the user already has.

C. **Crew-owned sibling config.** Write `playwright.crew.config.ts` that imports the user's config
   and appends `setup`/`axe`/`visual`; rules run `--config playwright.crew.config.ts`. Additive
   and closes the gap automatically, but depends on the base config's export shape (a function
   export or non-array `projects` breaks it), doubles the configs a reader must reconcile, and
   still needs A's testDir, credential and baseline handling. Not recommended now; a follow-up if
   the advisory snippet proves not enough.

D. **Docs-only**: tell multi-module users to run `--root <module>` and hand-edit. Rejected: leaves
   items 2-5 live, including writing test files where they are never collected.

## Recommendation
A. It fixes all five reported items and the two nearby breakages the fix itself would otherwise
create, keeps the scaffold's additive-only contract (the property that makes `--apply` safe to
offer), and turns every "could not tell" into its own reported value rather than a default that
looks like a result (project CLAUDE.md, "The recurring bug is an unknown collapsing into the
safe-looking value").

Constraints the Spec carries: no hook is added (none is needed; a design that needs one stops
needs-owner). Tests stub `npx`/`init-agents` and never run a real browser or network. A crew
content change bumps crew one patch past origin/main at push time (`plugin/crew/.claude-plugin/plugin.json`
and `.claude-plugin/marketplace.json`, claim-marked lines). Docs in the same PR per the owner rule
of 2026-09-26: `plugin/crew/commands/init.md`, `plugin/crew/commands/webtest.md`,
`plugin/crew/skills/crew-setup/phases.md`, and whichever of `plugin/crew/README.md`,
`plugin/crew/CONFIG.md`, `plugin/PLUGINS.md`, `docs/guides/crew/src/*.md` (+ rebuilt HTML/DOCX/PDF),
`.crew/codemap/`, `docs/diagrams/` describe the scaffold - the Spec's Touch list names them after
reading each. `plugin/crew/tests/sabotage_webtest.py` gains mutations for the new branches.

## Open questions (settled by written recommendation under standing authority)
1. Module argument shape - repeatable `--module` vs one module per run? **One `--module` per run**;
   `/crew:init` loops over the detected modules, one confirmed step each (same "ask once" rule).
2. How deep to search for modules? **A bounded depth (Spec picks the number, >= 2 to cover
   `apps/<name>`), skipping `node_modules`, `.git` and dot-dirs**; report the depth used in the
   output so a miss is visible.
3. What counts as "credentials recorded"? **`.crew/secrets.md` exists at `--root`** (the file
   `commands/onboard.md:195` and `credentials-and-playwright.md:13` already name). A config that
   already declares `storageState` also counts. Nothing else is inferred.
4. Where does the Test Agents' seed/`specs/` output go for a module? **Into the module** (its
   testDir); the root-level agent files and MCP entries point at it. The Spec records how
   `init-agents` is made to do that (run in the module and relocate, or configure) as an Unknown
   to resolve by reading Playwright 1.63's `init-agents` behaviour, not by guessing.
5. Advisory gaps: exit 0 or a distinct non-1 code? **Exit 0**, with the `gap` lines; the doc's
   exit-code table says so. A distinct code would make `/crew:init` treat a normal state as an
   error again.
6. `webtest_rules.py` for modules: **a module argument that prefixes each rule's `paths` with the
   module and runs its commands from the module**; the Spec checks that `verify-gate.sh` and
   `verify-gate.ps1` can both run a module-relative command before choosing the mechanism, and if
   one cannot, that becomes an Exclusion with a follow-up ticket rather than a bash-only rule.
7. Existing fresh-config template (`CONFIG_TS`) for repos with no config: **unchanged** except the
   credential condition in item 4a - no reason found to change its `snapshotPathTemplate` where no
   baselines exist.

## Exclusions
- Option C's sibling config; patching user configs (Option B).
- Any change to gizmoduck (T-0105..T-0108 own the other report items).
- Adding a hook.

## Notes
- Siblings from the same report: T-0104 (items 1-5), T-0105 (6), T-0106 (7), T-0107 (8, 12), T-0108 (9-11).
- The reporter's repo was read only; the dry run there wrote nothing.

## Owner decision 2026-09-30 - catch up with main by MERGE, never rebase
Owner Matthew Badali, 2026-09-30, verbatim choice "Merge main in (Recommended)", after "rebase alot fo these before merge we did 4-5 prs outside of here that merged to main". origin/main has moved (it was a61a6f38 when this note was written: T-0088 #262, the QA fixes #263-#267, crew 1.0.69).
- Before your NEXT Review round and again right before Land: `git fetch origin && git merge origin/main` (a merge commit; mechanical conflicts only - a behavioural conflict is a STOP to the owner). Never `git rebase`, never force-push, never squash.
- After each merge: version one patch past origin/main's, refresh the artifacts until fresh and committed, re-run the suites serially under heavy-run, and state the merged origin/main sha in the phase evidence.
- A review receipt that went stale ONLY because of such a merge follows the existing merge-only rule; anything else needs a new round.

## Owner decision 2026-09-30 - run the suites in parallel (pytest-xdist installed, capped at 4)
Owner Matthew Badali, 2026-09-30, verbatim choice "Install + cap at -n 4 (Recommended)". pytest-xdist 3.8.0 is now installed (apt python3-pytest-xdist); /root/crew-tmp/heavy-run exports PYTEST_XDIST_AUTO_NUM_WORKERS=4, so `-n auto` means 4 workers inside the wrapper.
- Full crew suite, always through heavy-run: `python3 -m pytest plugin/crew/tests/ -q -n 4 -m "not wallclock"`, then `python3 -m pytest plugin/crew/tests/ -q -m wallclock` serially (both must pass). This is main's own .crew/verify.json rule with the worker count pinned. Other pytest suites: same shape.
- pylint as CI runs it: `python3 -m pylint -j 4 $(git ls-files "*.py")`.
- Quote the new timing in the evidence (the serial full suite took ~700-900s here; #263 measured ~230s at -n 4).
- A test that passes serially and fails only under -n 4 is a real finding (shared-state race, as #267's d3cf73c3), not something to paper over: report it, never skip it.
