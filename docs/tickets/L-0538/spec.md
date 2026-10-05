# L-0538: Angular 2+ development standards set (T-0086 slice; set `NG`, AngularJS 1.x out of scope)          status: spec   risk: medium
Slice 8 of T-0086 (Python landed as #282, crew 1.0.77). Written against origin/main `a555ff37` (crew 1.1.0).
Re-find every line by content at implement time; SQL, PHP, PowerShell, .NET, Terraform and Node.js slices
(L-0532..L-0537) touch the same SKILL.md, README paragraph, PLUGINS.md row and BUDGETS.md claim.

## Intent
Ship `plugin/crew/skills/crew-standards/references/angular.md`, set `NG`,
`applies-to: ["**/src/app/**/*.ts", "**/src/app/**/*.html"]`, holding the Angular 2+ standards from T-0086's
Angular research that clear the landed admission bar (findings from at least three distinct reviewed change
sets). The research numbering is kept with the prefix `NG` in place of `ANGULAR` (`ANGULAR-07` ships as
`NG-07`), because the loader accepts only 2-6 capital letters and `ANGULAR` is 7. The count taken for this spec
(`docs/tickets/L-0538/changesets-angular.txt`) admits one rule, **NG-07** ("A failed read renders as 'could not
verify' and disables every write it feeds"). The other seventeen are listed in `stack-angular` as candidates,
each with its change-set count and what would promote it. Every Angular change then answers NG-07 in its
pre-review self-check. Nothing applies to AngularJS 1.x.

## Exclusions
- No change to the loader, gate, stamp or checklist: `crew_standards.py`, `review_run.py`, `review_prompt.py`
  and `crew_ticket.py` are not touched. In particular `_SET_RE`/`_ID_RE`/`_STANDARD_RE` stay `[A-Z]{2,6}`
  (direction Option 2 rejected; widening them is for whichever slice needs a long prefix and decides it for all).
- No AngularJS 1.x rule, and no edit to `stack-angular`'s "AngularJS (1.x) additions" section (owner 2026-09-28).
- No candidate in the gated file: no NG id other than the admitted list appears as a `## ` heading in
  `angular.md`, and none goes into `.crew/standards.md`.
- No machine-local citation in the shipped set: no `/repos/`, vault (`claude-memories`, `wiki/concepts`),
  auto-memory, `.work/` or `Fnnn` text (`test_shipped_sets_cite_nothing_local_only`,
  `test_shipped_sets_cite_no_machine_local_note`). Vault notes and `CLAUDE.md` lines may corroborate in the
  research; they are not change sets and are not cited.
- No other stack, and ANGULAR-18 (naive timestamps, JavaScript) is not moved to the Node.js slice.
- No edit to `plugin/crew/tests/sabotage*.py`: a `HARNESS` path (`scripts/check-tooling-pr.py:79`), and L-0539
  (the checker fix that would let a slice carry its own entries) has not landed. The sabotage entries are a
  follow-up tooling-only ticket, id minted by the coordinator.
- No hook, no config key, no `.crew/verify.json` change (`plugin/crew/skills/crew-standards/**` is already in
  the crew-standards rule, `.crew/verify.json:483-484`). So `plugin/crew/CONFIG.md` is unchanged.
- No change to the crew guides: `docs/guides/crew/src/daily-workflow.md:71` and `working-with-codex.md:71` say
  "per-language set a changed file matches" and name no set. Docs: none there, for that reason; the PR says so.
- No change to `docs/adr/0004-build-time-development-standards.md` (`:38-39` already provides for per-language
  sets as further files). No `docs/diagrams/` change (no new box or edge).
- No version bump on the build branch (REPO-03 in `.crew/standards.md`): the version is set at land.

## Evidence
origin/main `a555ff37`:
- Loader limits: `plugin/crew/hooks/scripts/crew_standards.py:82` `_SET_RE = ^[A-Z]{2,6}$` (checked `:132`),
  `:83` `_ID_RE`, `:84` `_STANDARD_RE` (both `[A-Z]{2,6}-\d{2}`); `:188-190` an id must carry the file's set
  prefix. `NG` and `NG-07` parse; `ANGULAR` and `ANGULAR-07` do not.
- Loader shape: `:76` `PLUGIN_FIELDS` (Rule, Why, Applies when, Self-check, Earned by, Change sets; Source
  optional `:75`); `:229-233` `_applies` matches with `crew_ticket.glob_match`; `:236-260` `_plugin_sets` reads
  every `references/*.md`; `:263` `effective_set` includes a stack set only when a changed file matches.
- `crew_ticket.glob_match` (`plugin/crew/hooks/scripts/crew_ticket.py`, search `def glob_match`): `**` spans zero
  or more segments, so `**/src/app/**/*.ts` matches `drata-insights/frontend/src/app/features/x/x.ts` and
  `src/app/app.ts`. `git ls-files | grep -c /src/app/` is 0 in this repo, so the set never applies to this
  repo's own changes (its TypeScript is `mcp-servers/packages/*/src/`).
- The worked example: `plugin/crew/skills/crew-standards/references/python.md:1-20` (front matter, the header
  paragraph defining a change set, "a commit that belongs to a ticket counts as that ticket, once", candidates
  as id gaps); `plugin/crew/skills/stack-python/SKILL.md:46-86` (Standards and Candidate standards sections).
- Tests already parametrised over every stack set (`_STACK_SETS`, `plugin/crew/tests/test_crew_standards.py:261`):
  `test_every_stack_standard_names_and_cites_three_change_sets` `:292` (a `Change sets` line `N: a, b, c`, each
  name cited in Earned by as `- <name> ` or `` `<name>` ``), `test_every_stack_standard_why_states_its_change_set_count`
  `:307` (Why carries "N findings across M change sets"), `test_every_stack_set_line_count_is_the_same_by_newline_and_splitlines`
  `:349`; plus `test_shipped_sets_cite_nothing_local_only` `:247` and `test_shipped_sets_cite_no_machine_local_note`
  `:381`. Python-specific ones to mirror: `test_python_set_parses_with_every_field` `:264`,
  `test_python_why_finding_counts_match_their_enumerations` `:336`, `test_python_sources_quote_whole_spans_without_elision`
  `:359`, `test_python_set_applies_to_python_files_only` `:372`.
- Research: `docs/tickets/L-0538/research-angular.md` (copy of `.work/tickets/T-0086/research/angular.md`,
  947 lines). ANGULAR-07 is at `:355-396`: Rule, Why, Applies when, four self-check items, Earned by, Source ("No
  fetched Angular doc states it"; so NG-07 ships with no Source field, or with the route-guards "server-side"
  sentence for its second half only). The mapping to stack-angular's pitfalls is `:54-70`.
- Change-set count: `docs/tickets/L-0538/changesets-angular.txt`, taken 2026-10-05 from the private repos
  `solomon/aws-shared-infrastructure` (`17e4db3`) and `solomon/aws-managed-services` (`7848e99d`), grouping each
  commit by the merge that brought it in. NG-07: ASI "plans 3+4 frontend" (`d1c39e6` "Codex review, tasks 14-20,
  Critical + Important #2", `a65df55` "Fix round 2, F2"), ASI PR #120 (`36ffb7c` "Fix round 3 on task 8. Critical
  from the final whole-branch review"), ASI `feat/instance-scoped-roles` (`f774865` "(I2)"). A fourth, AMS PR #480
  (`14d24e8d` "QA blocked #480"), is a weak fit and not relied on. Every other rule has 0-2.
- Existing guidance: `plugin/crew/skills/stack-angular/SKILL.md:19-40` (Angular 2+ pitfalls), `:42-48` (AngularJS,
  untouched), `:50-56` (Verification).
- Docs that name the sets: `plugin/crew/skills/crew-standards/SKILL.md:18-22`; `plugin/crew/README.md:795`
  ("The other stacks (SQL, PHP, PowerShell, .NET, Terraform, Node.js, Angular) follow"); `plugin/PLUGINS.md:217`
  (crew-standards, "Python so far"), `:218` (stack-angular row, which still says "Angular and AngularJS");
  `.crew/codemap/crew.md:1830-1831` ("The first stack set is ... python.md"); `CHANGELOG.md:10` `[Unreleased]`;
  `plugin/crew/BUDGETS.md` `<!-- claim: crew-markdown-lines -->`.

## Unknowns
- **Change-set count is final only as far as these two repos' history goes.** The cloud session cannot open
  `/repos/solomon`; it takes `changesets-angular.txt` as the record and does not re-derive it. If the owner or a
  local session finds a third reviewed change set for another rule (most likely NG-05 or NG-06, at two each), it
  is promoted in the same PR with its row added to the txt. Default: ship NG-07 alone.
- **`f774865` "(I2)" as a review marker.** ASI's commits name review findings `C<n>`/`I<n>`/`F<n>`; "(I2)" is read
  as Important #2 of a review. If the reviewer rejects it, NG-07 has two change sets (three with AMS PR #480 if
  that is accepted instead); if neither holds, the slice falls back to direction Option 3: no `angular.md`, all
  eighteen as candidates, and the PR says so.
- **Change-set names in the set file** (they must appear in Earned by and contain no machine path). Default:
  `ec2-iam-plans-3-4`, `ec2-iam-PR-120`, `ec2-iam-instance-scoped-roles`, each cited as
  `aws-shared-infrastructure@<sha>` with the quoted message, the way python.md cites `THDDEV-1134`.
- **Doc quotes.** NG-07 has no Angular doc behind its first half. If a Source line is kept, its quote is re-fetched
  raw with `curl` from angular.dev and string-matched whole, recorded in `docs/tickets/L-0538/quote-check-angular.txt`
  (no `[...]` elision).
- **Globs.** `**/src/app/**` misses an Angular library's `projects/<lib>/src/lib/`. Accepted: libraries are not in
  the owner's history; add `**/src/lib/**` only with a reviewed reason.
- **Self-check length.** An Angular change answers 12 GEN + 1 NG (+ REPO rows in a repo with an overlay). Accepted.
- Next free crew patch version set at land (main is 1.1.0 at `a555ff37`).

## Size and split
About 60 lines of Markdown in `angular.md`, about 45 in `stack-angular/SKILL.md`, about 30 test lines, and doc
rows. 0 production code lines. No harness path (sabotage entries split out). No further split.

## Touch
- `plugin/crew/skills/crew-standards/references/angular.md` - new, set `NG`
- `plugin/crew/skills/crew-standards/SKILL.md` - the stack-sets paragraph names the NG set
- `plugin/crew/skills/stack-angular/SKILL.md` - "Standards" and "Candidate standards (not gated)" sections;
  description narrowed to say AngularJS gets pitfalls only, no standards
- `plugin/crew/tests/test_crew_standards.py`
- `plugin/crew/README.md`
- `plugin/PLUGINS.md` - rows `crew-standards` and `stack-angular`; version line at land
- `plugin/crew/BUDGETS.md`
- `CHANGELOG.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, at land only
- `.claude-plugin/marketplace.json` - version, at land only
- `.crew/codemap/crew.md` (the stack-sets sentence) and `.crew/codemap/**` re-anchor
- `.claude/rules/**` - regenerate only; `graphify-out/**` - `graphify update .` only
- `docs/tickets/L-0538/` (removed in the final PR)

Not in Touch: `crew_standards.py` (no loader change), `plugin/crew/tests/sabotage_standards.py` (HARNESS,
follow-up), `.crew/verify.json`, `plugin/crew/CONFIG.md`, `docs/guides/crew/**`, `docs/adr/**`, `docs/diagrams/**`
(reasons in Exclusions).

## Acceptance checks
Commands from the repo root. `T` is `plugin/crew/tests/test_crew_standards.py`.
- [ ] `angular.md` parses with no problems; set `NG`, `applies-to` exactly `["**/src/app/**/*.ts", "**/src/app/**/*.html"]`,
  ids exactly the admitted list (`["NG-07"]` unless a promotion is recorded in `changesets-angular.txt`). New test
  `test_angular_set_parses_with_every_field`. `python3 plugin/crew/tests/pytest_rule.py T -q -k test_angular_set_parses_with_every_field`
- [ ] The parametrised stack-set tests pass for `angular.md`:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k "angular.md"`
  (names-and-cites-three, why-states-count, line-count-by-newline).
- [ ] NG-07's Why finding count matches what it enumerates, pinned by hand in a new table:
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_angular_why_finding_counts_match_their_enumerations`
- [ ] The set applies to Angular application sources only: `effective_set` on
  `["drata-insights/frontend/src/app/features/p/p.ts"]` and `["src/app/app.html"]` includes `NG`; on
  `["mcp-servers/packages/core/src/graphClient.ts"]`, `["README.md"]` and `["angular.json"]` it does not (unless
  a build-config rule was promoted). New test `test_angular_set_applies_to_angular_app_sources_only`.
  `python3 plugin/crew/tests/pytest_rule.py T -q -k test_angular_set_applies_to_angular_app_sources_only`
- [ ] No machine-local citation: `python3 plugin/crew/tests/pytest_rule.py T -q -k "cite_nothing_local_only or cite_no_machine_local_note"`
- [ ] No research-prefix leftovers: `grep -n "ANGULAR-" plugin/crew/skills/crew-standards/references/angular.md` is empty.
- [ ] If any Source quote ships: `docs/tickets/L-0538/quote-check-angular.txt` shows it found whole in the raw page,
  and a new `test_angular_sources_quote_whole_spans_without_elision` passes.
- [ ] `stack-angular/SKILL.md` names `crew-standards/references/angular.md`, points its "failed read" guidance at
  NG-07, and lists the seventeen candidates `NG-01`..`NG-18` minus `NG-07`, each with its change-set count from
  `changesets-angular.txt` and its research title; the AngularJS section is byte-identical to main
  (`git diff origin/main -- plugin/crew/skills/stack-angular/SKILL.md` shows no hunk inside it).
- [ ] Whole file passes: `python3 plugin/crew/tests/pytest_rule.py T plugin/crew/tests/test_review_run_standards.py -q`
- [ ] Docs in the same PR: crew-standards SKILL.md, README `:795` paragraph, PLUGINS.md rows, CHANGELOG
  `[Unreleased]` entry flagging the behaviour change (Angular app changes now answer NG-07; in-flight stamps on such
  changes go stale), BUDGETS.md re-measured; `python3 scripts/check-marketplace.py` passes after the commit.
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path touched).
- [ ] The ticket's own self-check stamps: `crew_standards.py init` then `stamp` exit 0 (the NG set does not apply to
  this repo's changes, so the rows are GEN and REPO).

## Dependencies
- T-0086 (Python slice, #282): merged; sets the pattern, the parametrised tests and the change-set definition.
- T-0085 (#269): merged; the loader.
- L-0532..L-0537 (other slices): independent content, shared doc lines; land through the merge train one at a time.
- Follow-up (not minted here): the NG sabotage entries in `sabotage_standards.py` (applies-to narrowed, NG-07's
  Change sets cut to two, a candidate heading shipped), a tooling-only PR after this one; needs no L-0539 if it
  lands alone.

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
