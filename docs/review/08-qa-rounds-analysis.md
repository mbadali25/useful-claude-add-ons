---
title: Fewer QA rounds - why tickets take ~6 review rounds and how to land in 2-3
date: 2026-10-03
status: analysis, input to a follow-up implementation session (not yet accepted)
---

# Fewer QA rounds

Two independent read-only analyses of crew's merge / QA gate / review / smoke pipeline, merged here.

| Analysis | Model | Corpus |
|---|---|---|
| A | Claude Opus 5.5, high effort | 67 ledgers, 213 completed rounds, 387 deduplicated findings (41 golden outputs + lane outputs + self-checks) |
| B | Codex gpt-6-astra, high effort (gpt-6.1-sol was refused at capacity; the owner chose astra) | 68 ledgers, 217 reserved attempts, 75 classified finding observations on T-0009, L-0510, T-0049, L-0590 |

Both read tracked code at `origin/main` **f808e5f0** (crew 1.0.154). Neither ran a test suite, gate or
review; every behaviour claim is from reading code and recorded outputs. Savings are projections.
The full analyses are kept outside the repo at `/root/crew-tmp/qa-rounds/{opus,codex}.md`.

## 1. What the numbers say

**Six rounds is the tail, not the typical ticket.**

| Measure | A (Opus) | B (Codex) |
|---|---|---|
| Median rounds per ticket | 2 | 2 |
| Mean | 3.18 | 3.19 |
| p90 | 6 | 7 |
| Tail | 24 tickets past 2 rounds used 61% of all rounds | 13 tickets with 6-10 attempts used 42% |
| Accepted within 3 | 72% (48 of 67) | 69% of accepted tickets |
| CLEAN outcomes | 1 ticket CLEAN in round 1; 52 of 67 never CLEAN | 11 clean receipts, 42 owner-accepted, 1 auto-accepted |

Further measurements (A):

- **Rounds do not converge.** FIX per round stays at 2.1-2.9 from round 2 on; BLOCK per round rises
  again from round 5. Fix code is new surface: L-0574's `review_checks.py` grew from 541 to 1298 lines
  across 10 rounds.
- **41 of the 82 rounds beyond 2 followed a round that already had 0 BLOCK.** L-0510's auto-accept
  (crew 1.0.142) now closes most of that gap. The tail that remains is BLOCKs in round 2 and later.
- **Size predicts rounds:** under 150 added production lines, 2.19 rounds; 150-600, 3.48; 600-1500, 4.85.
  Every ticket with 6+ rounds added 224-1046 production lines and contains a parser, guard or
  fail-closed state machine.
- **A round costs 1.5-6 hours of wall time.** The reviewer itself takes 6.8 min (median); the gap to the
  next reservation is 93 min median, 639 min p90 (fixes, a 17-20 min local gate, owner decisions).
- **The standards self-check (ADR 0004) did not lower first-round findings:** BLOCK+FIX 4.44 before
  2026-09-30, 4.13 after (confounded by ticket mix and a reviewer-model change).

B adds two cautions: *accepted in two rounds is not clean in two rounds*, and `.crew/metrics.md` is an
incomplete denominator (only 10 of 217 ledger rounds keep finding text). Optimise for fewer rounds
**with** complete evidence, not for a lower ledger count.

## 2. Where the rounds go

Classes from A's 387-finding corpus (keyword match plus manual reading, about ±5 points):

| Class | Share | Notes |
|---|---|---|
| Known classes already written in GEN/PYTHON/REPO standards or the recurring-findings list | 55-60% | Unknown collapsing to a safe value, unquoted paths, newline/U+2028 in line protocols, duplicate-key JSON, bare executables, symlink/FIFO opens, races keyed on resource not holder, tests with no failing control |
| Genuinely new design or edge defects | ~20% | T-0009 shell-grammar bypasses, T-0075 data-loss races. These deserve rounds, or a design change |
| Process, receipt and bookkeeping | 14% | 16 of 98 BLOCKs were "verify receipt missing" |
| Spec or acceptance gaps | ~6% | Acceptance checks the author knew were unmet when the round was reserved (L-0590, T-0049, T-0016) |
| "The round-N fix is one step short" | 5% explicit | L-0574 by hand: ~13 of 41 later findings were neighbours of earlier fixes |

B's four-ticket sample agrees on the shape: 63 of 75 observations were implementation or contract
defects, 6 missing receipts, 6 acceptance-evidence gaps. Both conclude that **most findings are real**;
the waste is in *when* they are found (serially, one neighbour per round) and in process BLOCKs.

**Process-only BLOCK rounds** (every BLOCK was process): L-0510 r1-r2, L-0521 r1, T-0001 r2, T-0009 r6,
T-0072 in 4 of 5 rounds, T-0085 r4. Ten of 70 rounds with surviving text. None is a code defect.

**Round 1 is not exhaustive.** In L-0574 about half of the round 2-10 findings were in code already
present at the round-1 head (five verified at `be6ab465`). L-0510 raised the malformed-round-number
problem in rounds 2, 3 and 6, and U+2028 in rounds 2 and 4 (B).

**The self-check's `n/a` answers were wrong in exactly the classes later rounds hit.** L-0510 marked
PYTHON-13 and GEN-06 `n/a`; rounds 3, 6, 7 found symlink, FIFO and unquoted `CLAUDE_PLUGIN_ROOT`.
L-0574 marked PYTHON-03 `n/a`; round 7 found newline-split filenames.

### The same pattern in SRL and TSS

The SRL and TSS sessions answered a questionnaire on 2026-10-03 (ticket L-0618). Their numbers are
self-reported and not re-measured here.

- **SRL:** 60 PRs merged 09-25 to 10-03 averaged 4.4-4.5 rounds, median 4; only 20 of 60 landed in 3 or
  fewer. PRs over 2,500 lines averaged 5.9. In 85 round-forcing findings, about 20% each were late finds
  in code an earlier round had approved, incomplete or fix-caused findings, and genuine first-pass defects.
  The top cause across all 60 PRs was missing or vacuous failing controls, at 24% of tags. SRL epic
  SRL-1678 independently ranks the same fixes: one verdict source, a round-1 brief with spec, rulings and
  threat model, severity with reachability, the findings chain stored off-machine, class-level fixes,
  and a deterministic pre-gate script.
- **TSS:** usually 1-3 rounds, 4-9 for security, money and migrations. Drivers: a guard placed after the
  write, fixing 1 of N callers, TOCTOU, and checks blind to their target. TSS-575 records a verdict gate
  that read CLEAN past a BLOCK.
- **A failure mode both hit:** Codex or Copilot exit 0 on a usage-limit or budget refusal. A harness that
  checks only the exit code reads that as BLOCK=0 FIX=0. Both repos now require a substantive final
  message, a header naming model and effort, and no usage-limit text, each with a failing control.

## 3. Defects in the pipeline itself

Both analyses found these by reading code. Items 1, 2 and 5 were found by both independently.

1. **CI receipt accepted by the gate but not shown to the reviewer.** `review_run.py:683` uses
   `review_gate.accepted_state`, which accepts a verified CI receipt (crew 1.0.153). But
   `review_prompt._receipts_block` (`review_prompt.py:159-186`) reads only `.crew/.verify-verified-at`,
   so a CI-gated round is told `MISSING`, the sentence 16 earlier BLOCKs quote. Not reproduced.
2. **The recurring-findings reviewer block is never called.** `recurring_findings.review_block`
   (`recurring_findings.py:353`) has no caller in `review_prompt.build` or `review.md`.
3. **REPO-03 contradicts the gate.** `.crew/standards.md:73` says a build branch carries main's version
   and bumps after the receipt; `check-marketplace.py:518` fails on that drift, so no receipt is written,
   the lane passes `--allow-unverified`, and the reviewer BLOCKs on "MISSING". Lanes that bump early then
   collide when main moves (T-0072 r5; today's whole-fleet re-version after #328-#330).
4. **The tooling-PR rule contradicts GEN-04.** `check-tooling-pr.py:58/76` classes every
   `sabotage*.py` as harness, so a feature PR cannot carry the mutations its own acceptance check needs
   (T-0049 got the same finding in both rounds). The rule has no machine-readable waiver, so an owner
   waiver leaves the gate red (T-0009 r6).
5. **Receipts go stale on clean merges.** `check_receipt` rebuilds `diff <base> <tree>`
   (`review_patch.py:229`, `review_ledger.py:833`), so merging main, a version re-bump or a codemap
   re-anchor stales an accepted receipt. The owner's standing staleness waiver is a prose patch.
6. **Auto-accept follow-up is not enforced at closure (B).** `review_ledger.check_follow_up`
   (`:756`) is not called by `check_receipt`, `/crew:done` check 1, or `crew_train.py:1269`.
7. **A matching local marker may hide outstanding obligations (B).** `review_gate._gate_state`
   (`review_gate.py:130`) returns VERIFIED on a matching marker without consulting over-budget rules
   the Stop hook left recorded (`verify-gate.sh:2040`). Needs a targeted test.
8. **The reviewer cannot see sabotage results (A).** Codex runs read-only and cannot re-run mutations;
   `reviewer.md:69-71` says to BLOCK when it cannot confirm a failing control; nothing hands it the
   sabotage receipt (T-0085 r4).
9. **No severity rubric or threat model in the prompt (A).** `review.md:408-415` names BLOCK/FIX/NIT
   without defining them. About 8-16 of 98 BLOCKs assume an attacker who can already write the checkout,
   `.crew/` or `PATH`, which `README.md:846` puts out of scope. B cautions that many late BLOCKs (T-0009)
   are real and must not be downgraded by policy.

## 4. Ranked changes

Ranked by expected rounds saved against risk. Savings overlap; do not add them. Items marked
**harness** touch review/gate code and must land alone (CLAUDE.md, T-0087 rule).

| # | Change | Saves | Risk | Source |
|---|---|---|---|---|
| 1 | **Readiness report before reservation; process BLOCKs removed at source.** Build the prompt's receipt block from `accepted_state` (fixes defect 1). Classify each unpassed rule as CODE-FAIL, ENV-SKIP (rc 77, OOM 143) or POLICY-PENDING (REPO-03 drift, an owner waiver). `--allow-unverified` proceeds only when nothing is CODE-FAIL. Tag receipt-only BLOCKs `PROCESS` so they do not block auto-accept. Land still requires a fully verified gate. **harness** | 0.3-0.5 per ticket; 2-4 on tails | Low | A C-1, B #2 |
| 2 | **Continuity and an exhaustive round 1.** Wire `review_block` (defect 2). Add a prior-findings block: each earlier finding verbatim with a stable ID and a disposition (fixed @sha + test, class-swept, deferred L-NNNN, disputed). Round 1: "report every instance of every class in one pass". Later rounds: verify fixes and their neighbours, tag new findings `[pre-existing]` or `[introduced]`. Must not bound the review. **harness** | 0.3-0.6; 1-2 on serial-discovery tickets | Medium (anchoring) | A C-4, B #3 |
| 3 | **Boundary-case sweep and an independent pre-review pass that is not a round.** A fresh-context Claude pass audits every self-check `n/a` and "addressed" answer and runs shared hostile-input fixtures (missing, unreadable, directory, FIFO, symlink, empty, bad UTF-8, wrong JSON type, duplicate keys, U+2028/U+202E, spaces in paths). Plus no-new-findings lints: unquoted `${CLAUDE_PLUGIN_ROOT}`, `splitlines()` on protocol data, `json.load` without the strict loader, bare executables, codemap citations. Record its time and findings so rounds are not moved into an invisible loop. | 0.3-0.5; 1-3 on complex tickets | Low | A C-5, B #1 |
| 4 | **Receipts survive a clean main merge.** Add `own_patch_id` (`git patch-id --stable` over merge-base..HEAD, excluding version files and refresh artifacts); `check_receipt` passes on either hash. Retires the staleness waiver. **harness** | Removes waiver stops | Low-medium | A C-2 |
| 5 | **Reconcile REPO-03 with the gate** (defect 3): report build-branch version drift as POLICY-PENDING and bump at land, or have `crew_train.py` write the bump after the receipt. | Removes version collisions and re-bumps | Low-medium | A C-1, B #5 |
| 6 | **Tooling-PR rule:** treat a feature's own `sabotage_<area>.py` table as a test, keep the runner and the harness's own tables as harness, and add `--waive --by <owner> --reason` so a waiver reads WAIVED, never "all passed". **harness** | Removes T-0049 / T-0009 r6 repeats | Low-medium | A C-7, B #4 |
| 7 | **Acceptance-evidence precheck.** Self-check carries one row per acceptance check with the command/artifact and result at HEAD, or DEFERRED with an owner reference and a spec amendment. Otherwise no round is reserved. Spec review asks whether each check is feasible inside the lane. | 0.1-0.2; kills L-0590/T-0049 repeats | Low | A C-6, B #2 |
| 8 | **Mechanical stop rule (needs a fresh owner go: `review.md:25-29` fixes the budget at 2).** Budget 3; round 3 auto-granted on a round-2 BLOCK; any cross-family 0-BLOCK round auto-accepts with a follow-up; enforce `--check-follow-up` at `/crew:done` and check-land first (defect 6). | Stops owner-stop tails | Low-medium | A C-2, B #6 |
| 9 | **Severity rubric, threat model and sabotage receipt in the prompt.** BLOCK = unmet acceptance check, wrong verdict / data loss / boundary crossed in normal operation or a realistic concurrent session or crash, or a new guard with no failing control and no sabotage receipt. Out-of-model findings become FIX `[out-of-model]`; a spec may declare `threat: local-adversary` to raise them back. **harness** | 0.2-0.4 | Medium | A C-3; B urges caution |
| 10 | **Smaller slices and convergent designs.** Plan size guard near 300 production lines or more than one new parser/guard. Guards and parsers name one strict schema boundary and an allowlist of recognised shapes (GEN-05), not a growing deny-list (T-0009). | 0.5+ on large tickets | Low | A C-8, B #4 |
| 11 | **CI receipt as the default gate; stabilise the landing candidate under the merge train.** Run mapped rules locally, push, use the CI receipt instead of a per-round 17-20 min local `--all`. Take the train before final catch-up, version allocation, refresh and gate. | Wall time, 0-1 indirect round | Medium | A C-9, B #5, #7 |
| 12 | **Round 3 as a delta review** (only with 2 and 3 in place; full review stays for `risk: high`). | Final round converges | Medium | A C-10 |

What none of these may weaken: `/crew:done` and check-land still require a verified gate on exactly
HEAD; CODE-FAIL still refuses a round; UNKNOWN, SKIP, failure, waiver and verified stay distinct
answers; only a cross-family round can auto-accept; BLOCKs, INCOMPLETE rounds and stale bundles are
never auto-accepted; every deferred finding is carried verbatim into a follow-up.

## 5. Target process

```
spec      acceptance checks feasible in-lane; size guard / slices; allowlist design for guards
plan      names standards, hostile-input fixture rows, sabotage entries
implement TDD; mapped verify rules locally; push; CI receipt
pre-review (no round spent)
          linters + class lints + citation check (no new findings)
          self-check stamp + acceptance-evidence table
          independent Claude pass audits n/a answers, runs fixtures; author fixes or dispositions
          readiness report: receipts from accepted_state, rules classed CODE / ENV / POLICY
round 1   cross-family, exhaustive, rubric + threat model + sabotage receipt
fix       by class: every instance and neighbour; dispositions recorded
round 2   prior findings + dispositions; verify fixes and neighbours; 0 BLOCK -> auto-accept + follow-up
round 3   only on a round-2 BLOCK; delta focus; 0 BLOCK -> auto-accept; BLOCK -> owner
land      train catch-up; receipt stands on unchanged own_patch_id; bump at land; done 1-4; check-land
```

## 6. How to measure it

Pilot on the next 20 comparable tickets, split by kind (ordinary feature, guard/state machine, harness,
performance/CI). Compare by era and size; keep ADR 0004's floor of 10 tickets per side.

| Metric | Baseline | Target |
|---|---|---|
| Rounds per ticket, median / p75 / p90 | 2 / 4 / 6-7 | 2 / 3 / 3-4 |
| Tickets landing within 3 attempts | ~70% | 80-90% |
| Process-only BLOCK rounds | 10 of 70 textual rounds | 0 |
| Round-2+ rounds with a BLOCK | 48% | 30% or less |
| `[pre-existing]` share of round-2+ findings | ~50% (L-0574) | 25% or less |
| INCOMPLETE rounds | 8% | 3% or less |
| Gap between rounds | median 93 min, p90 639 | median 45 min |
| Clean / auto / owner-accepted closure mix | 11 / 1 / 42 | more clean and auto; no rise in escaped defects |
| Author pre-review time and findings | not tracked | recorded, so rounds are not hidden |
| Deferred-finding age, escaped defects, rollbacks | not tracked | no increase |

## 7. Not verified

- No suite, gate, review or CI-only lane was run. Defects 1, 6 and 7 come from reading code.
- Class shares are keyword matching plus reading, about ±5 points. The L-0574 split is mostly
  judgement (5 claims checked at `be6ab465`).
- Finding text before L-0510 survives only in golden outputs and lane folders; the corpus leans to tails.
- Size bins may include merged main changes where a ledger base was never re-based.
- Analysis B ran on gpt-6-astra, not the requested gpt-6.1-sol, which was at capacity.
