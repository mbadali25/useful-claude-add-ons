# L-0537 direction - Node.js development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/node.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/node.md` (and README.md, "Recommended next step").
Stack skill: new stack-node skill.
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Ship the Node.js / TypeScript slice of T-0086: a new `stack-node` skill, and the research rules
(`.work/tickets/T-0086/research/node.md`, NODE-01 to -18) that pass the landed admission bar in
`crew-standards/references/node.md`, set `NODE`. The rest are candidates in `stack-node`.

## What the re-count found (2026-10-05, before options)
The research lane counted "distinct server/package with a defect" and included vault notes
(`research/node.md:923-951`, ten rules "meet"). Re-read under T-0086's counting rule (a commit counts only when its
own message records a review round or finding; one PR counts once; vault notes, docs and reproductions are not
change sets), **one rule reaches three: NODE-08 (4)**. NODE-06, -07 and -10 have two; the rest one or none. Many
cited aws-managed-services commits are author fixes whose message records no review.

## Options
1. **New `stack-node` (guidance, verify rule, candidates) plus a NODE set with what passes, today NODE-08
   (recommended).** Follows the Python and .NET slices; the skill is useful on its own; the set grows when a third
   reviewed change set earns a candidate. Sabotage entries go in a tooling-only follow-up (HARNESS path), or ride
   along if L-0539 has merged. Cost: a one-rule set adds NODE rows to every JS/TS change for one rule.
2. **`stack-node` with all eighteen as candidates, no set file.** No gated rows. Cost: drops a rule that did earn
   its place, and is inconsistent with how the bar is applied to the other slices.
3. **Count the research's per-package defects (or doc MUSTs) as change sets.** Ten or more rules ship. Cost:
   changes the owner-approved bar; T-0086 settled that a doc is Source, not a change set.

## Recommendation
Option 1. The implementing session re-counts first (including each cited PR's review thread); the set ships
whatever passes, and if nothing passes it falls back to Option 2 without a new decision.

## Open questions (default taken)
- **`applies-to`.** Default taken: `["**/*.ts", "**/*.mts", "**/*.cts", "**/*.js", "**/*.mjs", "**/*.cjs"]`. A glob
  cannot exclude a browser app, so an Angular `.ts` change also draws NODE; accepted, because NODE-08 (a partial
  result says it is partial) holds for any paging client. `package.json`/lockfiles do not draw it (no admitted rule
  is about them).
- **Doc MUST as a third change set (NODE-01, MCP spec).** Default taken: no, per T-0086's settled answer. NODE-01
  stays a candidate.
- **`stack-angular` pointer to NODE-03/-18.** Default taken: not in this ticket; both are candidates, and
  `stack-angular` belongs to L-0538.
- **UCA `graphClient.ts` bearer-on-nextLink observation** (`research/README.md`, "Things the lanes noticed").
  Default taken: out of scope here; it is a defect report, not a standard, and needs its own ticket (not minted
  here).
- **Counting rule.** Default taken: T-0086's, unchanged.

## Approval
Approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority.
