# L-0536 direction - Terraform development standards set (T-0086 slice)

Status: approved direction, inherited from T-0086. Owner 2026-09-30 ~11:20: "File 7 tickets now" - the remaining T-0086 language slices each get their own ticket, spec, review budget and PR. T-0086 closes as the Python slice.

Carry over unchanged from `.work/tickets/T-0086/direction.md`: the one-set-per-stack format on T-0085's wiring (`plugin/crew/skills/crew-standards/references/terraform.md`, `applies-to` globs), the admission bar (findings from at least three distinct reviewed change sets; an official doc is the Source, not a change set; rules below the bar are listed as candidates in the stack skill, not shipped), Earned-by citations re-read from the raw sources, a change-set count for every rule, and the self-check wiring. Follow T-0086's Python slice as the worked example: its spec, plan, tests (test_crew_standards.py count and quote checks) and sabotage_standards.py entries.

Research: `.work/tickets/T-0086/research/terraform.md` (and README.md, "Recommended next step").
Stack skill: extend stack-terraform; settle the three Terraform questions per research.
Order in T-0086's direction: Python (T-0086), SQL (L-0532), PHP (L-0533), PowerShell (L-0534), .NET (L-0535), Terraform (L-0536), Node.js (L-0537), Angular 2+ (L-0538). The slices are independent files, but each touches crew-standards/SKILL.md and BUDGETS.md, so they land through the merge train one at a time.
Depends on: T-0086 (Python) landing first, which sets the pattern and the test and sabotage scaffolding. Also L-0539 (the check-tooling-pr.py fix), else each slice needs the same rule-36 waiver T-0086 got.

## Ask
Ship the Terraform slice of T-0086: the research rules (`.work/tickets/T-0086/research/terraform.md`,
TERRAFORM-01 to -19) that pass the landed admission bar go into `crew-standards/references/terraform.md`, set
`TERRAFORM`; the rest are candidates in `stack-terraform`, and the three Terraform questions are settled there.

## What the re-count found (2026-10-05, before options)
Every cited commit in terraform-aws-shared-infrastructure, Vault, ANEW-Warehouse and TheHomeDepot was re-read
with `git log -1 --format=%B`. Under T-0086's counting rule (a change set is a crew review, or a fix commit whose
own message records that a review found the defect; one PR counts once), **no TERRAFORM rule reaches three**. The
best are TERRAFORM-11 and -12 with two each (Vault PRs #19, #34; #19, #10). Most cited commits are fixes found by
`terraform plan`, a failed apply or the author, not by a review. The research lane did not assess the bar
(`research/README.md`, "Gaps and failures" 3), so this is new.

## Options
1. **Candidates now, set later (recommended).** `stack-terraform` gets a `## Standards` section saying no gated
   TERRAFORM set ships yet and why, and a `## Candidate standards (not gated)` section with all nineteen, each with
   its change-set count and what would promote it. Before writing it, the implementing session checks each
   cited PR's GitHub review thread: a rule that reaches three reviewed change sets that way ships in
   `references/terraform.md` on T-0085's format, as the Python and .NET slices do. Cost: probably no gated
   Terraform rows yet; the guidance still reaches every Terraform change through the skill.
2. **Count plan/apply failures as change sets for infrastructure.** Most rules would pass. Cost: changes the
   owner-approved bar (`crew-standards/SKILL.md:16-17`) for one stack, against T-0086's settled "Each slice must
   count change sets"; a decision the owner did not delegate.
3. **Defer the slice** until Terraform reviews accrue. Cost: the research's nineteen rules and its three settled
   questions sit unused, and nothing records why.

## Recommendation
Option 1. It follows the bar as landed, ships the guidance, and leaves the set file to arrive when evidence
earns it (or with a set of one or more rules now, if the PR review threads show it).

## Open questions (default taken)
The T-0086 direction says the slice spec "takes the lane's draft position and flags any it cannot cite":
- **`for_each` in `import` blocks needs 1.7.** Default taken: the lane's position (floor 1.7), flagged: no
  HashiCorp page the lane fetched states it; the implementing session confirms it in the Terraform 1.7 changelog
  raw, or the candidate line says "1.5+ for `import`; `for_each` in `import` unverified".
- **CMK for log groups.** Default taken: the lane's draft, "CMK always", flagged: only Vault's evidence supports
  it, and the shared-infrastructure repo does not state it. Recorded on the TERRAFORM-12 candidate line.
- **TERRAFORM-03 vs the literal-ARN fix in `tsi@adcf5e5`.** Default taken: the stricter form for new code (no
  literal ARNs); the existing fix is not reopened.
- **Counting rule.** Default taken: T-0086's, unchanged (Option 2 rejected).

## Approval
Approved 2026-10-05 for cloud hand-off by the orchestrator under the owner's standing self-approve authority.
