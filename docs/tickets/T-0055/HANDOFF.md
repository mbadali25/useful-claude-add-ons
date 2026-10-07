# Cloud handoff: T-0055

**CI enforces crew doc updates: narrative docs touched, or `Docs: none - <reason>` declared**

Handed to a cloud session on 2026-10-04 by owner instruction. Do not pick up locally.

- **Role:** parent ticket, narrowed to part (a), docs-touched-or-declared. Child: L-0657 (part (b), built guides fresh in CI).
- **INDEX status:** ready (spec written and approved for hand-off 2026-10-04; plan to be written by the implementing session). Priority: med.
- **Branch:** `T-0055-build`, new from origin/main `ce235468`; docs only, no implementation yet
- **Files here:** `docs/tickets/T-0055/direction.md`, `docs/tickets/T-0055/spec.md`
- **Size:** about 190 production lines (`scripts/check-crew-docs.py` about 170 with its docstring, `scripts/gate-runner.py` about 6, `marketplace.yml` about 14). No harness path. Nothing under `plugin/crew/` changes, so no crew version moves. Risk is marked med in the spec.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| T-0087 | merged | Provides `scripts/check-tooling-pr.py`, the model for a branch-diff check with a commit trailer, and the tooling-PRs-land-alone rule this spec stays clear of. |

Nothing open blocks this ticket.

Not required for this slice: T-0048 (spec). The INDEX title says "depends on T-0048 for freshness"; the spec moves that dependency to the child, L-0657. The facts file lists T-0048 as a dependency of this ticket with the note "not required for this slice"; the spec wins, and T-0048 does not have to land first.

Related, no order forced: T-0046 (in-progress; BUDGETS.md claim numbers) and T-0054 (ready; the autopilot guide).

This ticket blocks:

- L-0657, which reuses this ticket's CI step position and `CLAUDE.md` paragraph.
- T-0011 (approved; autopilot ship policy), softly: it merges on green checks, so the doc rule is unenforced for autopilot merges until this lands. Not a hard block.

Family order:

1. T-0055 (this ticket): the docs-touched-or-declared check.
2. L-0657: guides fresh in CI. Blocked until both T-0048 and T-0055 have merged.

## Read before writing code

- The spec's `path:line` evidence was checked at origin/main `155fe6d8`. Main has moved since (the branch base is `ce235468`); re-check each anchor.
- No plan.md is published (none existed). The implementing session writes the plan.
- In spec.md, `children/1/` means L-0657.
- The doc-rule paragraph the check enforces was not in `CLAUDE.md` on origin/main at `155fe6d8`; it existed only as an uncommitted local edit. Check whether main has it now. If not, this ticket commits it from the text embedded in spec.md, plus one sentence naming the check and the trailer.
- Only narrative docs count as "docs touched". Version, changelog, budget, code map and diagram files neither trigger nor satisfy the check: counting them would have passed 31 of 31 measured crew PRs.
- Do not edit `scripts/check-tooling-pr.py`, `crew_ticket.py` or any `sabotage*.py` (harness). Import or copy the shared code. The suite carries its own mutation cases.
- "Could not tell" exits 77, never 0: a missing `origin/main` ref, a failed git call, or a PR body that should have been readable and was not.
- No Stop-gate rule runs the checker itself; the `.crew/verify.json` rule added here runs the suite only. No workflow trigger changes.
- A new CI step also needs an entry in `scripts/gate-runner.py`'s step table, or `--check-ci` fails.
- This is a blocking check, so the repo's guard rule applies: a committed suite with must-fail and must-pass cases, sabotage-tested.
- No suites or gates were run when the spec was written.
- direction.md holds two owner decisions from 2026-09-30 that still apply: catch up with main by merge, never rebase, force-push or squash; and the parallel-suite instructions. The heavy-run wrapper they name is a local tool of the original host; the cloud session uses its own equivalent.

## Open questions for the owner (recommended option taken)

1. Should a code map or diagram edit count as "docs touched"? Default taken: no, because re-anchoring changes them in nearly every crew PR; a PR whose only real doc change is code map prose declares `Docs: none` with that reason.
2. Should editing the PR body re-run the check? Default taken: leave the workflow triggers alone; a late declaration goes in a commit trailer. Alternative: add `edited` to `pull_request.types`, which re-runs the whole Marketplace workflow on each body edit.
3. Should the check also run at Stop through `.crew/verify.json`? Default taken: no, it would block every stop before the docs step; it runs in CI and in `gate-runner.py`.
4. Should prompt files (`commands/*.md`, `agents/*.md`, `SKILL.md`) trigger the check when changed alone? Default taken: no, they are themselves in the doc set.
5. Should the new checker's sabotage rows also be registered in `plugin/crew/tests/sabotage_tooling.py`? Default taken: no (that file is harness and would need its own tooling-only PR).
6. The `CLAUDE.md` doc-rule paragraph has sat uncommitted in a local checkout since 2026-09-26. The spec commits it through this ticket; owner to confirm that is wanted rather than a separate commit.

The child's question (pinning the `markdown` version in CI) is listed in L-0657.

## Before landing

Merge origin/main, take a crew version above main's from the coordinator, follow the repo's CLAUDE.md (scope discipline, doc updates for `plugin/crew` changes, tooling-PR rule), and remove `docs/tickets/T-0055/` in the final PR unless the owner wants it kept. Per the spec this ticket changes nothing under `plugin/crew/`, so no crew version is needed unless that changes.
