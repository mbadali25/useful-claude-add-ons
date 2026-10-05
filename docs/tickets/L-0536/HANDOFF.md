# Cloud handoff: L-0536

**Terraform development standards (TERRAFORM), T-0086 slice: candidates now, a set when earned**

Handed to a cloud session on 2026-10-05 by owner instruction. Do not pick up locally.

- **Role:** slice of T-0086 (done, PR #282); the Terraform stack in the direction's order.
- **INDEX status:** spec (direction and spec approved for hand-off 2026-10-05; plan to be written by the implementing session)
- **Branch:** `L-0536-build`, new from origin/main `a555ff37`; docs only, no implementation yet
- **Files here:** `docs/tickets/L-0536/direction.md`, `docs/tickets/L-0536/spec.md`
- **Size:** 0 production lines. Expected about 10 lines in `stack-terraform/SKILL.md` and a new `stack-terraform/references/candidates.md` (about 50 lines; stack skills are capped at 120 lines), plus doc rows. If the review-thread check lifts a rule to three change sets, add a set file (about 60-120 lines) and about 40 test lines.
- **Harness:** no. Sabotage entries (only if a set ships) go in a tooling-only follow-up, or ride along if L-0539 has merged.

## The finding that shapes this ticket

The re-count for this spec found **no Terraform rule with three reviewed change sets**: most cited commits fix defects found by a plan, an apply or the author, and only eight cited commits record a review. TERRAFORM-11 and -12 have two each. So the expected deliverable is the nineteen rules as candidates in `stack-terraform`, with counts, and no gated set. The spec's Evidence has the per-rule counts.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0086 | done, merged (#282) | The pattern and the tests. |
| L-0539 | direction, not merged | Only matters if a set ships. |
| L-0532..L-0535, L-0537, L-0538 | direction / spec | Same doc lines; land one at a time. |

## Read before writing code

- The spec's evidence is at origin/main `a555ff37`. Re-find every line by content.
- The research is `.work/tickets/T-0086/research/terraform.md` on the owner's host (not in git). Ask the coordinator for a copy if the cloud session cannot read it.
- Check each cited PR's GitHub review thread (ANEW-Business-Solutions repos) before deciding that no set ships. If access fails, counts stay as in the spec.
- Never write an empty `references/terraform.md`: the loader refuses a set with no standard.
- If a set ships, re-fetch every HashiCorp/AWS quote raw with `curl` (the research's came through a summariser) and drop `[...]` elisions.

## Open questions for the owner (recommended option taken)

- Counting rule: unchanged; plan/apply failures are not reviewed change sets. The owner may choose otherwise in a new ticket.
- `for_each` in `import` blocks: floor 1.7 (the lane's position), confirmed from the raw 1.7 changelog or flagged as unverified.
- Log group CMK: "CMK always" (the lane's draft), flagged as Vault-only evidence.
- TERRAFORM-03: the stricter no-literal-ARN form for new code; `tsi@adcf5e5` is not reopened.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/L-0536/` in the final PR unless the owner wants it kept.
