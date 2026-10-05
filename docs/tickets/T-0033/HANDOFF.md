# Cloud handoff: T-0033

**a version-only re-bump does not stale a review receipt (receipt hash normalises version tokens in release bookkeeping)**

Handed to a cloud session on 2026-10-05 by the orchestrator under the owner's standing self-approve authority.

**On HOLD. Do not build without checking L-0522 first.** The default taken on 2026-10-04 and kept on 2026-10-05 is to close T-0033 as superseded once L-0522's delta gate (part 2) is on main. The delta gate covers the real case, a catch-up merge followed by a bump. This spec is the fallback contract if the owner chooses to build the bump-only normaliser anyway.

- **Role:** standalone ticket, held fallback.
- **INDEX status:** ready (spec and plan written; this hand-off does not move it)
- **Branch:** `T-0033-build`, new from origin/main `a555ff37`; docs only, no implementation
- **Files here:** `docs/tickets/T-0033/direction.md`, `docs/tickets/T-0033/spec.md` (anchors refreshed 2026-10-05), `docs/tickets/T-0033/plan.md` (2026-09-26, marked stale)
- **Size (if built):** about 190 production lines (`review_patch.py` ~100, `review_ledger.py` ~65, `review_run.py` ~25) plus tests and sabotage entries.
- **Harness:** yes. Every production path is in `HARNESS` (`review_*.py`, `sabotage*.py`, `commands/review.md`), so if built it lands as two tooling-only PRs (normaliser, then dual-read). `commands/done.md` is in neither `HARNESS` nor `ALONGSIDE`, so its one-line wording change needs its own docs PR.

## Dependencies and work order

| Ticket | State | Why |
|---|---|---|
| L-0522 | in-progress; part 1 (#377) merged 2026-10-04, part 2 not on main | Its delta gate supersedes this ticket for the catch-up case and edits the same `check_receipt`. Check it first: if part 2 has landed, verify a catch-up plus re-bump keeps a receipt, then close T-0033 as superseded. |
| T-0100 | on main (crew 1.0.322) | Rebuilds the bundle against merged main, which is why a catch-up merge plus a bump still stales under this design. |
| T-0026 | merged | The dual-read precedent. |
| L-0510 | done | `auto_accept`, the third comparison site. |
| T-0087 | merged | The tooling-PRs-land-alone rule. |

Blocks L-0584 (direction), which cannot be settled until this ticket or L-0522 is chosen. Same files, no order forced: T-0068, L-0620, L-0596, T-0109.

## Read before writing code

- Start with `git grep -l review_delta origin/main -- plugin scripts`. If it prints anything, L-0522 part 2 has landed: stop and close T-0033 as superseded (with the check above) rather than building.
- The spec's evidence was re-verified at origin/main `a555ff37` on 2026-10-05. Most `review_ledger.py` anchors moved by one line. `sabotage.py` is 3381 of 3400 allowed lines and is still not touched.
- One design change beyond line numbers: CHANGELOG headings now come in five shapes (batch headings listing several plugins without backticks, and others), so the heading grammar was widened. It is still closed and full-line, and only semver tokens are replaced.
- plan.md is stale: anchors from `1e0706ac`, the old CHANGELOG bullet rules, and no `auto_accept` step. Re-plan from spec.md.
- The reviewer's input (patch, parts, `bundle_sha256`) must stay byte-identical. Only the receipt comparison reads the normalised hash.

## Open questions for the owner (recommended option taken)

- Build or close? The default taken is to hold and close as superseded when L-0522 part 2 lands. The other options were to build the bump-only normaliser now (it collides with L-0522 part 2 and covers a case the merge-then-bump workflow does not produce) or to close now (that leaves no ticket if part 2 is cut).
- The widened CHANGELOG grammar. The default is the closed grammar over the five shapes on main; the owner confirms it at approval if the ticket is built.
- From 2026-10-04, still open: `accept` stays strict after a catch-up merge in L-0522 too. The default taken is no new ticket, since lanes already accept first and then catch up.

## Before landing

Only if built: merge origin/main, take a crew version above main's from the coordinator, land as two tooling-only PRs per the spec, plus the separate `done.md` docs PR, follow the repo's CLAUDE.md, and remove `docs/tickets/T-0033/` in the final PR. If closed as superseded, close this draft PR with the L-0522 evidence.
