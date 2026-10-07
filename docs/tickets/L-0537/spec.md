# L-0537: Node.js development standards set (NODE) and a new `stack-node` skill, T-0086 slice          status: spec   risk: medium
Slice of T-0086 (done, PR #282, crew 1.0.77). Written against origin/main `a555ff37` (crew 1.1.0). Research input:
`.work/tickets/T-0086/research/node.md` (local only).

## Intent
Add `plugin/crew/skills/stack-node/SKILL.md`, a stack skill in the existing layout (When this applies, Pitfalls,
Standards, Candidate standards (not gated), Verification, verify.json rule to propose, LSP), for server-side and
CLI Node.js and TypeScript (MCP servers, Lambdas, CLIs). Ship `plugin/crew/skills/crew-standards/references/node.md`,
set `NODE`, `applies-to: ["**/*.ts", "**/*.mts", "**/*.cts", "**/*.js", "**/*.mjs", "**/*.cjs"]`, holding the
research rules that findings from at least three distinct reviewed change sets earn (re-count: NODE-08), on
T-0085's loader unchanged. Every other research rule is a candidate in `stack-node` with its count. The crew
bundle's skill count moves from 31 to 32 at every marked site.

## Exclusions
- No loader, gate, stamp or checklist change (`crew_standards.py`, `review_run.py`, `review_prompt.py`).
- No edit to `plugin/crew/tests/sabotage*.py` (HARNESS, `scripts/check-tooling-pr.py:79`): the NODE sabotage entries
  are a tooling-only follow-up, or ride along if L-0539 has merged first.
- No change to `stack-web` or `stack-angular`. `stack-web/SKILL.md` keeps its `cmd /c npx` and `node_modules/.bin`
  lines; `stack-node` points to them instead of repeating them. The `stack-angular` pointer is L-0538's.
- No browser, Angular-template or Playwright rules (`research/node.md:19-21`).
- No change to `mcp-servers/` code. The `graphClient.ts` bearer-on-absolute-URL observation (`research/README.md`)
  is a defect for its own ticket.
- No candidate in the gated file; no machine-local citation in the shipped file (no `/repos/`, vault note,
  `wiki/concepts`, `.work/`, `Fnnn`). Reproductions ("Reproduced (Node v22.22.1)") are not change sets.
- No marketplace registration: `stack-node` is a skill bundled inside the `crew` plugin, so no
  `.claude-plugin/marketplace.json` entry, no catalog row and no install-script line (CLAUDE.md "Registering an
  entry" is for marketplace entries). The crew entry's description count is updated.
- No `.crew/verify.json` change: `plugin/crew/skills/crew-standards/**` is in the crew-standards rule
  (`.crew/verify.json:484`), and `plugin/crew/skills/**` already maps to check-marketplace (rule 0) and
  validate-prompts (rule 16). `test_stack_skills.py` runs in the full crew suite only; adding a stack-skill rule
  for it is not this ticket's (say so in the PR).
- No CONFIG.md, hook or guide change (the guides name no stack skill by count). No version bump on the build branch.

## Evidence
origin/main `a555ff37`:
- Bar: `plugin/crew/skills/crew-standards/SKILL.md:16-17`; stack sets `:18-22`. Counting rule as shipped:
  `plugin/crew/skills/crew-standards/references/python.md:8-20`.
- Loader: `plugin/crew/hooks/scripts/crew_standards.py:76` `PLUGIN_FIELDS`, `:83` `_ID_RE` (`NODE-08` valid), `:236`
  `_plugin_sets`, `:263` `effective_set`.
- Shipped-set tests: `plugin/crew/tests/test_crew_standards.py:260` `_ADMITTED_PYTHON`, `:261` `_STACK_SETS` (picks up
  `node.md` with no edit), `:264` parse test, `:292` change-set test, `:307` Why-count test, `:330` `_PYTHON_FINDINGS`,
  `:349` line-count test, `:359` elision test (Python only), `:372` applies-to test, `:381` machine-local test.
- Stack-skill tests: `plugin/crew/tests/test_stack_skills.py:62-71` `STACK_NAMES` (eight), `:73` `MAX_LINES = 120`,
  `:78-87` `_TRIGGER_TERMS`, `:128` all exist, `:133` `test_no_stray_stack_skill_directories` (a new `stack-node`
  fails it until listed), `:142` 120-line cap, `:175` a ```json rule is required, `:205` each `run` command needs
  an `exit 77` / `TOOL MISSING` branch.
- No `stack-node` today: `ls plugin/crew/skills | grep stack` gives angular, bash, dotnet, powershell, python, sql,
  terraform, web. Overlaps to point to, not repeat: `plugin/crew/skills/stack-web/SKILL.md` (`cmd /c npx`; probe
  `node_modules/.bin` only).
- Crew skill count 31, at the `plugin-skills:crew` claim sites: `README.md:168`, `README.md:399`,
  `INSTALLATION.md:253`, `plugin/PLUGINS.md:17`, `plugin/README.md:414`; unmarked in the crew entry's description
  `.claude-plugin/marketplace.json:223`; the codemap tables `.crew/codemap/crew.md:55` ("includes 8 `stack-*`
  skills"), `:58`, `:80` (stack list), `.crew/codemap/marketplace-registration.md:61`, `:68`. Checked by
  `check_self_claims` (`scripts/check-marketplace.py`, `plugin-skills:<name>`).
- Stack rows: `plugin/PLUGINS.md:217` (crew-standards, "Python so far"), `:218-225` (stack rows; `stack-node` row goes
  in name order). `plugin/crew/README.md:795` (names Node.js as to follow).
- Research rules: `research/node.md` NODE-01 `:69` ... NODE-18 `:873`; the lane's admission table `:923-951`
  (counted per package, vault included); proposed skill shape `:985-994`; raw-curl doc quotes, Node.js v26.10.0
  banner (`:62-66`).
- Re-count, 2026-10-05, `git log -1 --format=%B <sha>` in `/repos/solomon/aws-managed-services` (AMS) and this repo
  (UCA). Commits whose message records a review: AMS PR #219 (`e73f2e27` "resolve QA findings", `9bfe47fc`),
  `c252471a` ("Codex QA finding", ms-intune), `9f1b11ed` ("Codex QA findings", powerautomate), `bf70a36b` and
  `485cf395` (checkpoint, "Reviewed independently", "address review", same evening: one change set), PR #84
  `5d80e16f` ("Codex QA findings F1-F7"), PR #72 `3aceb77d` ("Reviewed independently before"), PR #167 `d3644792`
  ("Codex review of PR #165"; PR #165's `23dc5c63` is the same change set); UCA `c80c68c8` ("fix Codex QA
  findings"), `11c3725f` ("Two issues from review"), `4e2bfb78` ("Codex findings on PR #78"). All other cited
  commits record none. Per rule: **-08 4** (UCA `c80c68c8`, AMS `9f1b11ed`, AMS checkpoint `485cf395`, AMS PR #84);
  -06 2 (`c252471a`, `9f1b11ed`); -07 2 (PR #84, PR #72); -10 2 (`9f1b11ed`, PR #219); -01 1; -03 1 (PR #219; PR #309's
  "review-ux" is a feature name); -04 1 (checkpoint); -05 1 (UCA `c80c68c8`); -09 1 (PR #165/#167); -11 1 (PR #219);
  -12 1 (PR #219); -13 1 (UCA `4e2bfb78`); -14 1 (UCA `11c3725f`); -15 1 (UCA `c80c68c8`); -18 1 (PR #165/#167);
  -02, -16, -17 0.
- Version: `plugin/crew/.claude-plugin/plugin.json:3` is `1.1.0`.

## Unknowns
- **The final admitted list.** Resolved at implement: re-read every cited commit and each cited PR's review thread
  (`gh pr view <n> -R <owner/repo> --comments`; AMS is a Solomon repository, access may fail, and then the count
  stands). Record one line per change set in `.work/tickets/L-0537/changesets-node.txt`. Rules that reach three
  ship; if none does, ship `stack-node` with all eighteen as candidates and no `node.md` (direction Option 2), since
  the loader refuses an empty set (`test_refusal_branch_empty_set`).
- **Commits with no PR merge after them** (`c252471a`, `9f1b11ed`, `a1d19a35`, `fff787b5`, `3227278f`, all
  2026-08-28 on different modules). Counted per module here (ms-intune and powerautomate are different
  branches by their messages). If the session shows they are one PR, NODE-08 still has three.
- **Quotes.** The lane read Node docs raw with `curl` (v26.10.0); re-fetch at implement and string-match into
  `.work/tickets/L-0537/quote-check-node.txt`; no `[...]` elisions.
- **The 120-line cap.** `stack-node` must fit pitfalls, the standards pointer, eighteen candidates and a verify rule
  in 120 lines (`test_stack_skills.py:142`). If it does not, the candidate list moves to
  `plugin/crew/skills/stack-node/references/candidates.md` and SKILL.md links it.
- **Private repository evidence** (AMS is a client repository): accepted as risk, as for PYTHON's TheHomeDepot.
- Merge train with the other slices (shared doc lines and, here, the skill count). Next free crew patch at land.

## Size and split
About 110 lines of new `stack-node/SKILL.md`, about 60-100 lines of `node.md` (one rule), about 40 lines of tests,
count edits at about ten sites. No production code, no harness path. No further split.

## Touch
- `plugin/crew/skills/stack-node/SKILL.md` - new (and `references/candidates.md` only if the cap requires it)
- `plugin/crew/skills/crew-standards/references/node.md` - new, the NODE set (only if a rule passes)
- `plugin/crew/skills/crew-standards/SKILL.md` - stack-sets bullet names the NODE set
- `plugin/crew/tests/test_stack_skills.py` - `stack-node` in `STACK_NAMES` and `_TRIGGER_TERMS` (`("node",)`)
- `plugin/crew/tests/test_crew_standards.py` - `_ADMITTED_NODE`, `_NODE_FINDINGS`, parse / applies-to / finding-count
  tests; the elision test parametrized over `_STACK_SETS` (unless a sibling slice already did it)
- `plugin/crew/README.md` - `:795` and any stack-skill list
- `plugin/PLUGINS.md` - `:17` count, `crew-standards` row, new `stack-node` row; version
- `README.md` - `:168`, `:399` counts
- `INSTALLATION.md` - `:253` count
- `plugin/README.md` - `:414` count
- `.claude-plugin/marketplace.json` - `:223` crew description count; version at land
- `plugin/crew/.claude-plugin/plugin.json` - version, at land only
- `CHANGELOG.md`
- `plugin/crew/BUDGETS.md`
- `.crew/codemap/crew.md` (`:55`, `:58`, `:80`, effective-set bullet), `.crew/codemap/marketplace-registration.md`
  (`:61`, `:68`), `.crew/codemap/install-scripts.md` (`:237`) - counts and re-anchor
- `.crew/codemap/**`, `.claude/rules/**`, `graphify-out/**`, `docs/diagrams/**` - refresh only (standing rule)
- `docs/tickets/L-0537/` - removed in the final PR

Not in Touch: `plugin/crew/tests/sabotage*.py` (harness), `stack-web`, `stack-angular`, `mcp-servers/**`,
`scripts/install-prerequisites.{sh,ps1}` (no marketplace entry), `plugin/crew/CONFIG.md`, `docs/guides/crew/**`.

## Acceptance checks
Commands from the repo root; pytest through the heavy-run wrapper on a memory-bound host.
`S` is `plugin/crew/tests/test_crew_standards.py`, `K` is `plugin/crew/tests/test_stack_skills.py`.
- [ ] `stack-node` exists, is listed, is at most 120 lines, has a valid front matter with "node" in the description,
  and proposes a verify rule whose every `run` command has an `exit 77` / `TOOL MISSING` branch.
  `python3 plugin/crew/tests/pytest_rule.py K -q`
- [ ] `references/node.md` (if shipped) parses with no problems; set `NODE`; `applies-to` as in Intent; ids exactly
  `_ADMITTED_NODE`. `python3 plugin/crew/tests/pytest_rule.py S -q -k test_node_set_parses_with_every_field`
- [ ] Every NODE standard names and cites at least three change sets, its Why count matches, and its finding count
  equals `_NODE_FINDINGS`. `python3 plugin/crew/tests/pytest_rule.py S -q -k "node or stack_standard"`
- [ ] The NODE set applies to `src/index.mjs`, `packages/core/src/a.ts` and `lib/x.cjs`, and not to `README.md`,
  `package.json` or `x.py`. `-k test_node_set_applies_to_javascript_and_typescript_files_only`
- [ ] No Source quote in any stack set is elided; shipped sets cite nothing machine-local; line counts agree.
  `python3 plugin/crew/tests/pytest_rule.py S -q -k "elision or machine_local or local_only or line_count"`
- [ ] `stack-node` lists the admitted ids and every other NODE id as a candidate with `(<N>` count; none in both.
  `python3 -c "import re;t=open('plugin/crew/skills/stack-node/SKILL.md',encoding='utf-8').read();print(sorted(set(re.findall(r'NODE-\d\d',t)))==[f'NODE-{n:02d}' for n in range(1,19)])"` prints `True`
  (or the same over SKILL.md plus `references/candidates.md`).
- [ ] Each new test was hand-sabotaged red once (narrowed `applies-to`, a candidate heading in place of NODE-08, a
  wrong Why count, `stack-node` removed from `STACK_NAMES`); mutations and red test names in the PR body.
- [ ] `.work/tickets/L-0537/changesets-node.txt` and `quote-check-node.txt` exist and cover every shipped citation.
- [ ] Skill count: every `plugin-skills:crew` site reads 32 and `python3 scripts/check-marketplace.py` passes after
  the commit; `grep -rn "31 skills\|31 bundled skills" README.md INSTALLATION.md plugin/README.md plugin/PLUGINS.md .claude-plugin/marketplace.json` is empty.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK`.
- [ ] Existing suites: `python3 plugin/crew/tests/pytest_rule.py plugin/crew/tests/test_crew_standards.py plugin/crew/tests/test_stack_skills.py plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_lifecycle_commands.py -q`
- [ ] Docs: README `:795`, PLUGINS.md rows, `crew-standards/SKILL.md`, codemap name `stack-node` and the NODE set;
  CHANGELOG flags the behaviour change (a JS/TS change now answers NODE rows; in-flight stamps go stale); BUDGETS.md
  re-measured; crew bumped at land.
- [ ] Refresh: `python3 plugin/crew/hooks/scripts/crew_instructions.py rules --root . --check` and
  `python3 plugin/crew/hooks/scripts/crew_refresh_check.py --root . --ticket L-0537` pass.

## Dependencies
- T-0086 (PR #282): merged.
- L-0539: not merged; if it lands first the sabotage entries ride along.
- Siblings L-0532..L-0536, L-0538: shared doc lines; L-0533 (PHP) also adds a new stack skill, so whichever lands
  second re-counts the skills (32 or 33) and adds to `STACK_NAMES` after the other.
- Follow-up: a tooling-only ticket for the NODE sabotage entries (id minted by the coordinator).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
