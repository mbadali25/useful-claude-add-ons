# L-0522 direction - Delta gate: a catch-up merge that adds none of the ticket's own code keeps the review receipt; version bump and refresh run BEFORE the gate so L-0512's tree cache can hit

Status: approved 2026-10-05 for cloud hand-off (orchestrator, under the owner's standing self-approve
authority). Re-brainstormed against origin/main `a555ff37`; the original spec and plan were lost with a
removed lane worktree and are reconstructed here from the code on `L-0522-tooling` and the history.

## Seed (verbatim, 2026-10-01)

Owner decision 2026-10-01 (relayed by crew-chat from the owner's AskUserQuestion answer in that session):
file now. Evidence today: L-0520, L-0558, T-0505, L-0557 and L-0516 all landed or stalled on receipts
staled only by main merges, version bumps and refresh artifacts, which needed hand waivers
(done-waiver.md). Related: T-0033 (version-only re-bump does not stale a receipt), T-0100 (scope base
after merges), L-0512 (gate cached by tree).

## Where the ticket stands

- **PR 1 (merged, #377, crew 1.0.326, 2026-10-04):** "one landing order on check-land's catch-up
  refusals". `crew_train.LANDING_ORDER` (`plugin/crew/hooks/scripts/crew_train.py:1235` at `a555ff37`)
  now says: bump one past the base, refresh, commit, gate the merged head, review again if the receipt
  reads stale, then `check-land` again. That is the "version bump and refresh run BEFORE the gate" half
  of the title. Done.
- **PR 2 (built, never reviewed, never pushed until this hand-off):** the delta gate, on
  `L-0522-tooling` (6 own commits, about 2120 lines over 14 files): `review_delta.py` (new, 711 lines),
  `review_ledger.check_receipt(root, ticket, base_sha=None)` consults it after the fast path fails,
  `review_run.preflight`, `crew_autopilot` routing, 1065 lines of `test_review_delta.py`, sabotage
  entries, docs and code maps. Owner decision 2026-10-03: it ships **fail-closed** - the gate binds its
  integration base to the ticket's merge-train entry, so in a clone whose train is not armed it keeps
  nothing (`no train entry binds the integration ref`).
- **PR 3 (not started):** `/crew:done` check 1 text and the README receipt text (feature/docs, not
  harness, so its own PR after PR 2).

## Ask

Finish L-0522: land the delta gate as a tooling-only PR that main can take today (fail-closed), then a
small feature/docs PR that tells `/crew:done` and the README what a delta-gate keep means.

## What main already does since PR 1 (checked at `a555ff37`)

1. **T-0100 (#371) is on main and NOT on `L-0522-tooling`.** `review_patch._ticket_base_tree`
   (`plugin/crew/hooks/scripts/review_patch.py:271`) diffs the bundle from a synthetic base tree: every
   path byte-identical to the merged integration commit drops out, and a path both sides changed is
   diffed from the merged commit's version. `bundle_sha256` hashes only the patch parts (`:366`). So a
   catch-up merge that touches none of the ticket's paths and moves no ticket byte already keeps the
   receipt on the **fast path**. The delta gate's remaining value is exactly what the fast path still
   stales on: (a) the ticket's own version bump after review (manifests, CHANGELOG, PLUGINS.md,
   BUDGETS.md), (b) a refresh after review that moves only anchor shas (code maps, rules, diagrams),
   (c) a catch-up where main also edited a ticket file, so the context lines move (L-0620's case, see
   below).
2. **L-0512 was DROPPED (owner, 2026-10-02):** over 77 attributed gate runs a by-tree cache would have
   hit 0 times. The tree-pass cache that did land (crew 1.0.139, `verify-gate.sh:1372`) keys on HEAD
   and every ref and credits only at Stop, so a new head never hits it. The title's "so L-0512's tree
   cache can hit" no longer motivates anything; the landing-order half stands on its own (gate the tree
   that lands).
3. **The merge train exists and is not armed in this clone** (`crew_train.py status` -> `armed: no`,
   2026-10-05). `check_land` calls `review_ledger.check_receipt(top, ticket)` with no `base_sha`
   (`crew_train.py:1279`), though PR 2's docstrings say `check_land` passes the sha it fetched.
4. **Main's README still says "a delta gate - until one exists"** (`plugin/crew/README.md:791`).

## Does PR 2's design still fit main?

Mostly, with one defect a main merge will expose and one wiring gap:

- **Rebuild check (judge step 2) is pre-T-0100.** `review_delta.tree_bundle_sha256` re-implements the
  bundle as a plain `git diff <receipt base> <tree>` (`review_delta.py:187` on the branch). Main's
  `review_patch.compute` diffs from the synthetic merged-main base, so any receipt written on main after a
  catch-up has a hash the plain diff cannot reproduce: step 2 would read stale every time. Fail-closed,
  so not unsafe, but the gate would never keep anything. After merging main, step 2 must rebuild through
  `review_patch`'s own tree logic (the synthetic base resolved as it was at the reviewed head), not a
  copy of the pre-T-0100 diff.
- **`base_sha` is never passed by `check_land`.** Wiring it is a `crew_train.py` edit: production code
  outside `HARNESS`, `SEAM` and `ALONGSIDE` (`scripts/check-tooling-pr.py:58`, `:89`, `:99`), so it
  cannot ride in a tooling-only PR. PR 2 keeps its train-entry fallback and its docs stop claiming
  `check_land` pins the sha; PR 3 does the wiring.
- `crew_autopilot.py` is a `SEAM` path; commit `44641776` already carries its
  `Tooling-seam: plugin/crew/hooks/scripts/crew_autopilot.py` trailer. Main moved that file by +1720
  lines since the branch point, so expect conflicts there.

## Options

- **A. Ship PR 2 as built, adapted to main, fail-closed (recommended).** Merge origin/main, re-derive
  step 2 on T-0100's bundle, narrow the "check_land passes the sha" claims, review (two rounds),
  land as tooling-only. Keeps the reviewed-by-nobody-yet but fully tested design (33 sabotage
  entries), and gives L-0511 PR 2 the version/anchor exemptions it needs. Cost: a large merge
  (about 1594 commits behind), heavy conflicts in `crew_autopilot.py`, `README.md`, code maps.
- **B. Narrow PR 2 to the allowlist only** (version tokens and anchor shas), dropping the catch-up
  interdiff since T-0100 covers the no-overlap catch-up. Smaller review, but the interdiff is the
  mechanism the allowlist rides on, so it is a rewrite of reviewed-ready code, and it does not help
  the overlap case either.
- **C. Close PR 2 as superseded by T-0100 + T-0033 + L-0620.** No merge cost, but T-0033 covers only
  versions, nothing covers anchor-only refreshes, and L-0511 PR 2 loses its precondition.

## Recommendation

A. Two PRs remain: PR 2 (`L-0522-tooling`, tooling-only, fail-closed) then PR 3 (`L-0522-docs`, new
branch from main after PR 2 merges: `/crew:done` check 1, README receipt text, `check_land` passes its
fetched sha). L-0620 stays the follow-up for a catch-up resolved back to the reviewed bytes over main's
edit to a ticket file. T-0033 closes as superseded once PR 2 lands (its version-only case is the
manifest allowlist).

## Open questions (default taken)

1. Fail-closed until the train is armed, or fall back to a scope-base guess? **Default: fail-closed**
   (owner decision 2026-10-03; `scope_base._default_ref` is a guess, not the landing target).
2. Wire `check_land`'s fetched sha in PR 2 or PR 3? **Default: PR 3** (production code cannot ride in a
   tooling-only PR).
3. Re-derive step 2 on T-0100's bundle, or drop step 2? **Default: re-derive** (step 2 is what proves the
   reviewed bytes were a commit's tree; dropping it would let a dirty-tree review be "kept").
4. Review budget: the L-0522 ledger is `ACCEPTED` with 0 rounds left, and that receipt is PR 1's
   (round 2 head `f691c54c`, an ancestor of #377's head). **Default:** the implementing session approves
   the published spec and plan through `crew_ticket.py approve` (owner's standing authority) and checks
   that it registered a successor with a fresh budget, as T-0100's successor did. If it did not (that
   path was seen after a reject, not on an `ACCEPTED` ledger), stop and ask the owner for a budget; do
   not review on a spent ledger.
5. Keep `docs/tickets/L-0522/` in the final PR? **Default: remove it** before landing PR 2, unless the
   owner says keep.
