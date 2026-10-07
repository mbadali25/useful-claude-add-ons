# L-0522 PR 2 - plan (rush/h3-review, ported onto main)

1. Re-apply PR 2's own diff (`git diff 71e32af7^2 ddd9b2a7`, not the history) onto main with a
   3-way apply; resolve: verify.json (main's extra rule line kept), troubleshooting.md (both
   texts; the gate keeps nothing until `crew_train.py arm`), review.md (main's exit-9 / L-0514 /
   L-0518 text plus PR 2's receipt clauses), review_ledger.py (main's `merged_main` note on the
   stale line, then the judge).
2. Step 2 on T-0100: `reviewed_bundle` rebuilds the reviewed head's bundle through
   `review_patch._ticket_base_tree(..., head=H_r)` (merged_main.resolve takes `head`), and D_r
   diffs from that bundle's base tree. Test: a round reviewed after a catch-up keeps its receipt
   across a bump and an anchor-only re-anchor, and stales on one ticket byte. Sabotage: the plain
   diff from the start again.
3. Drop the two "check_land passes its fetched sha" claims.
4. crew_autopilot.py (SEAM, `Tooling-seam:` trailer) sits at exactly max-module-lines (3400) on
   main: the two answers' words move to `review_delta.beyond_anchor_stop` /
   `after_review_refresh`, reached as `review_ledger.review_delta`, so the module stays at 3400.
   main's other two `check_receipt` callers (ship, pre-merge) are left as they are: a delta-kept
   receipt there still ships through CI and the pre-merge checks.
5. Docs: CHANGELOG, code map paragraph re-found by content, troubleshooting guide HTML rebuilt.
