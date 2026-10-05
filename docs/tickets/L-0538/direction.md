# L-0538 direction - Angular 2+ (AngularJS 1.x out of scope, owner 2026-09-28) development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/angular.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/angular.md` (and README.md, "Recommended next step").
Stack skill: extend stack-angular.
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Ship the Angular 2+ slice of T-0086: a per-stack standards file in `plugin/crew/skills/crew-standards/references/`
on T-0085's loader, holding only the Angular rules from `.work/tickets/T-0086/research/angular.md` (ANGULAR-01..18)
that clear the landed admission bar (findings from at least three distinct reviewed change sets), with the rest
listed as candidates in `stack-angular`. AngularJS 1.x is out of scope (owner 2026-09-28): `stack-angular`'s
AngularJS section is left as it is and no rule applies to 1.x code.

Facts found at brainstorm (origin/main `a555ff37`, 2026-10-05):
- **The name `ANGULAR` does not parse.** `crew_standards.py:82` `_SET_RE = ^[A-Z]{2,6}$` and `:83-84` `_ID_RE` and
  `_STANDARD_RE` allow 2-6 capital letters; `ANGULAR` is 7. `parse_set` (`:188-190`) also requires every id to carry
  the file's set prefix. A file with `set: ANGULAR` or a `## ANGULAR-07` heading is a parse problem, so the research
  ids cannot ship as written.
- **Few rules clear the bar.** The research did not count change sets (T-0086 direction `:25`). A first count here,
  grouping each owner commit by the merge that brought it in (a commit belonging to one PR counts once, as T-0086's
  python.md header does) and counting only commits whose message records a review finding, gives: ANGULAR-07 three
  (aws-shared-infrastructure "plans 3+4 frontend" `d1c39e6`/`a65df55`, PR #120 `36ffb7c`, aws-managed-services
  `14d24e8d` "QA blocked #480"); ANGULAR-05 and -06 two each; every other rule one or none. ANGULAR-01 to -04 all
  come from one PR (#430, six round commits). Vault notes and `CLAUDE.md` lines are not change sets.
- `L-0539` (the check-tooling-pr.py fix T-0086 needed a waiver for) has not landed, and `plugin/crew/tests/sabotage*.py`
  is a `HARNESS` path (`scripts/check-tooling-pr.py:79`), so sabotage entries cannot ride with this feature PR.

## Options
1. **Ship set `NG` with only the admitted rules, research numbering kept (`NG-07`, ...); candidates in
   `stack-angular` (recommended).** `NG` is Angular's own prefix (the `ng` CLI, `ng-` attributes) and fits the
   loader's 2-6 letters, so no loader change. Ships what the bar admits (expected: NG-07 alone), and every Angular
   change answers it. Cost: a small set, and ids that differ from the research file's `ANGULAR-` prefix (the spec
   maps them one-for-one).
2. **Widen `_SET_RE`/`_ID_RE`/`_STANDARD_RE` to 2-10 letters and ship set `ANGULAR`.** Keeps the research ids, and
   PowerShell (`POWERSHELL`, 10) and Terraform (`TERRAFORM`, 9) need the same change. Cost: a loader change in a
   slice whose pattern (T-0086 Exclusions) is "no loader change"; it alters the digest-relevant parser for every
   repo and belongs to whichever slice decides it for all stacks, with its own tests.
3. **Ship no set file yet; put all eighteen in `stack-angular` as candidates until three rules qualify.** Zero
   gating risk. Cost: the self-check never asks an Angular question, which is the point of the slice; NG-07 already
   clears the bar.

## Recommendation
Option 1. The set is `NG`, file `references/angular.md`, `applies-to: ["**/src/app/**/*.ts", "**/src/app/**/*.html"]`
(the Angular CLI's application source tree; Angular 20+ names components without the `.component` suffix, e.g.
`policy-changes.ts`, so a `*.component.ts` glob would miss them; `**/*.ts` would also draw this repo's TypeScript
`mcp-servers`, which is not Angular). If the implement-time re-count admits a build-configuration rule (NG-12 to
-16), `**/angular.json` joins the globs. If the re-count admits none, the slice falls back to Option 3 and says so.
Sabotage entries go to a follow-up tooling-only ticket.

## Open questions (default taken)
- Prefix: `NG` (Option 1), not a loader change. Default taken.
- What counts as a change set: T-0086's landed rule (`references/python.md` header), applied per PR/merge, and
  only a commit whose message records a review finding. Default taken; the spec's count is a starting point and is
  redone at implement from `git show`.
- ANGULAR-18 (naive timestamps) is JavaScript, not Angular: it stays a candidate here and is not moved to the
  Node.js slice (L-0537, not landed). Default taken.
- Sabotage entries: a separate tooling-only follow-up, because `sabotage*.py` is HARNESS and L-0539 has not landed.
  Default taken.
- AngularJS 1.x: no rule, no edit to the AngularJS section. Owner decision 2026-09-28.

## Approval
Direction approved 2026-10-05 for cloud hand-off, by the orchestrator under the owner's standing self-approve
authority (2026-09-26, reaffirmed 2026-09-27 and 2026-10-05).
