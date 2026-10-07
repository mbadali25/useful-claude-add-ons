# L-0518 direction - T-0085 follow-up: round-4 accepted findings

Status: approved 2026-10-05 for cloud hand-off (was: seed).

Owner accepted T-0085 review round 4 with a follow-up (2026-09-30, "Accept, follow-up"). T-0085 landed as #269 (merge df3cdf17, crew 1.0.75). The round-4 BLOCK was answered by the sabotage run (42 RED at 0c6f01e0, 43 on the land branch); the FIX and NIT lines below are this ticket, verbatim from .work/tickets/T-0085/round4-findings.txt:

```text
BLOCK|plugin/crew/tests/sabotage_standards.py:734|None of the new checks has a failing control this review could confirm: all 42 STANDARDS_MUTATIONS entries and the new must-block/must-allow tests in test_crew_standards.py and test_review_run_standards.py. This reviewer has Read/Grep/Glob only and could not run a single mutation. The bundle carries no tracked sabotage.py result, and the verify-gate receipts are MISSING at head 0c6f01e0, so every "goes red" claim is the author's word|With a shell, on a clean tree: `TMPDIR=/root/crew-tmp/t-0085 python3 plugin/crew/tests/sabotage.py`. Every STANDARDS_MUTATIONS label must report red on its named test, with no ANCHOR LOST and no .bak left
FIX|plugin/crew/hooks/scripts/crew_standards.py:715|`proposals` passes exit code 0 and no expected parts to `review_verdict.parse(text, 0)`. So a round that `finish` scored INCOMPLETE still gets a proposals file listing its partial findings as the round's complete set, and the exclusive create then locks that file in. INCOMPLETE rounds this misses: reviewer exited non-zero, timed out, skipped a bundle part (no READ line), bundle_problems, or webtest reasons. review.md:537 and SKILL.md say an INCOMPLETE round's out.txt is refused, which holds only when the text alone is INCOMPLETE|Write scratch/out.txt as `READ|part-001-of-003.patch` plus `BLOCK|a.py:1|x|y` (parts 2 and 3 unacknowledged), or take a real round whose review.json has verdict INCOMPLETE with exit_code 1. Run `crew_standards.py proposals --root R --ticket T-1 --scratch scratch --round 1`: it exits 0 and writes standards-proposals-r1.md with one finding
FIX|plugin/crew/hooks/scripts/review_run.py:422|The skip-the-gate decision uses `review_ledger.status`, read outside the lock, and the reserve at :429 re-reads the ledger without carrying that decision. The ledger is read twice for one authorizing fact (GEN-03 self-check 2). If a successor plan is approved in between, NEEDS_REPLAN becomes IN_REVIEW with rounds left, the gate stays skipped, and `reserve` spends a round with no self-check at all|Take a ticket in NEEDS_REPLAN with no selfcheck.md. Pause `run()` right after `review_ledger.status` returns (monkeypatch it to sleep, or set a breakpoint), then run `review_ledger.py --ticket T-1` successor approval. Resume: exit 0 and ROUND=3 with no `review-run: self-check` refusal
FIX|plugin/crew/hooks/scripts/crew_standards.py:86|`_STAMP_RE` accepts only a 40-hex `base=`, but `stamp` writes whatever `scope_base.resolve` returned. In a SHA-256 git repository (`git init --object-format=sha256`) every stamp line is 64 hex, `read_selfcheck` reports "the stamp line does not parse", and `review_gate` refuses every round in that repo forever. Nothing else in scope_base or review_patch is limited to 40 hex, so this producer/consumer mismatch is new (GEN-07)|`git init --object-format=sha256 r`, commit, `scope_base.py --record T-1`, change a file, write an approval receipt, `crew_standards.py init`, answer the rows, `stamp` (exit 0). Then `review_run.py --provider claude --reserve-only`: exit 2 with "line 2: the stamp line does not parse"
FIX|plugin/crew/skills/crew-plan/SKILL.md:72|The plan self-review tells the author "`crew_standards.py sets` lists them", but `sets` goes through `_scope`. At plan time no scope base is recorded yet (that is /crew:implement step 1), so it refuses with "no scope base recorded ... run scope_base.py --record". Even with a base, there is no diff at plan time, so stack sets whose applies-to globs match the files the plan will touch (T-0086's format) are never listed. The documented plan-time aid either refuses or under-reports|On an approved ticket before /crew:implement, run `crew_standards.py sets --root . --ticket T-1`: exit 1, "no scope base recorded for T-1"
NIT|CHANGELOG.md:51|"Rule 31 of `.crew/verify.json` also runs on the scripts..." is stale on the merged tree. After T-0010's rule 28, the standards rule is rule 32 (`.crew/verify.json:340-352`), which is how verification-harness.md now names it (GEN-09)|`python3 -c "import json;r=json.load(open('.crew/verify.json'))['rules'];print([i for i,x in enumerate(r) if 'crew_standards.py' in str(x['paths'])])"` prints [32]
NIT|plugin/crew/skills/crew-standards/SKILL.md:100|A leftover fragment makes the text read "...Self-check said and Proposal to fill. The An `out.txt` the verdict parser calls INCOMPLETE..."|`sed -n 99,102p plugin/crew/skills/crew-standards/SKILL.md`
NIT|.crew/codemap/INDEX.md:292|Every re-anchored history cell opens "(T-0010 landing lint fixes, crew 1.0.61" and never closes it before "; on T-0085's line ...". The parentheses are unbalanced in all eight updated rows, and one cell's history now reads as nested inside another's|`grep -c "crew 1.0.61; on T-0085's line" .crew/codemap/INDEX.md` returns 8
NIT|plugin/crew/hooks/scripts/review_run.py:391|On the gate path, an exception from `crew_incident.log_skip` (an unwritable `.crew/`) or `crew_state.load_config` is not caught; `main` catches only LedgerError. Python then exits 1, and review.md:441 maps exit 1 to FINDINGS, so a crashed gate reads as a review with findings instead of "not run"|`chmod 555 .crew` during an active incident with no selfcheck.md, then `review_run.py --provider claude --reserve-only`: Traceback and exit 1
NIT|plugin/crew/hooks/scripts/crew_standards.py:488|`note = f"(fallback) {why}"` prepends "(fallback)" to a reason that `scope_base.resolve` already ends with "(fallback)" (`_FALLBACK`). init, stamp and sets print it twice on one line|Run `test_stamp_scope_fallback_when_the_record_is_unusable[not-ancestor]` and print `lines`: "(fallback)" appears twice in the stamp line
```

Line numbers are at T-0085 round-4 head 0c6f01e0; re-locate them on main before fixing.

## Ask
Close the T-0085 review round-4 FIX and NIT lines the owner accepted with a follow-up. The BLOCK line is not this
ticket's work: it was answered by the sabotage run (42 RED at `0c6f01e0`, 43 on the land branch) before T-0085
landed.

Re-located on origin/main `a555ff37` (2026-10-05); every finding is still present:

| # | Finding | Now at | Harness? |
|---|---|---|---|
| F1 | `proposals` scores `out.txt` with exit 0 and no parts, so an INCOMPLETE round gets a proposals file | `plugin/crew/hooks/scripts/crew_standards.py:725`, `:745` | no |
| F2 | the gate-skip decision reads `review_ledger.status` outside the lock; `reserve` re-reads without it | `plugin/crew/hooks/scripts/review_run.py:854-863` | **yes** (`review_*.py`) |
| F3 | `_STAMP_RE` accepts only a 40-hex `base=`; a SHA-256 repo can never pass the gate | `crew_standards.py:87-88` (written `:569`) | no |
| F4 | the plan self-review sends the author to `crew_standards.py sets`, which refuses before a scope base exists | `plugin/crew/skills/crew-plan/SKILL.md:72`; `_sets` `crew_standards.py:875`, `_scope` `:461` | no |
| N1 | CHANGELOG says "Rule 31" for the standards rule; it is index 41 now (38 also lists `review_run.py`) | `CHANGELOG.md:4155` | no |
| N2 | "The An `out.txt` ..." fragment | `plugin/crew/skills/crew-standards/SKILL.md:102-103` | no |
| N3 | history cells open "(T-0010 landing lint fixes, crew 1.0.61" and read as nested | `.crew/codemap/INDEX.md:299-302`, `:305`, `:308` (6 rows now, was 8) | no |
| N4 | an exception from `crew_incident.log_skip` / `load_config` on the gate path exits 1 (reads as FINDINGS) | `review_run.py:712-714`; `main` catches only `LedgerError` `:1000` | **yes** |
| N5 | "(fallback)" printed twice on one line | `crew_standards.py:490` + `scope_base.py:121` `_FALLBACK` | no |

## Options
1. **Split by the tooling-PR rule: this ticket is the feature half (F1, F3, F4, N1, N2, N3, N5); F2, N4 and every
   sabotage entry go to one tooling-only follow-up (recommended).** Follows CLAUDE.md ("a change to the review/gate
   harness lands alone") and the standing owner rule "Tooling-PR rule: split, do not ask - feature PR then tooling PR
   (next L-)". Cost: two PRs; F2 (the only correctness FIX in the harness) waits for the second.
2. **One tooling-only PR for everything.** Puts all fixes together. Cost: `crew_standards.py`, `crew-plan/SKILL.md`
   and `crew-standards/SKILL.md` are not harness, so `check-tooling-pr.py` refuses the mix; it is the rule-36 failure
   T-0086 needed a waiver for.
3. **Feature half only; drop F2 and N4 as not worth a PR.** Cost: F2 is a real GEN-03 hole (a round spent with no
   self-check) that the owner accepted as a follow-up, not as a waiver.

## Recommendation
Option 1. This spec covers the feature half and specifies the tooling half in full (its own section) so the
coordinator can mint its id and lift it unchanged.

## Open questions (default taken)
- F1: where the round's real verdict comes from. Default: the review ledger row for `--round N`
  (`review_ledger.status(root, ticket)["rounds"]`), which `review_run.finish` records before `review.json`; proposals
  runs only when that row's verdict is CLEAN or FINDINGS. No row, another verdict, or an unreadable ledger refuses
  (could-not-tell), writes nothing and leaves the exclusive create free. The `out.txt` text parse stays as a second
  check.
- F3: accept `base=` of exactly 40 or exactly 64 lowercase hex; any other length still refuses. Default taken.
- F4: add `sets --touch`, which reads the spec's Touch list (`crew_ticket.parse_touch`) and matches stack-set
  `applies-to` globs by overlap (`recurring_findings.matches(..., touch=True)`, the matcher `/crew:implement` step 2
  already uses), needing no scope base; plain `sets` is unchanged. `crew-plan/SKILL.md:72` names `sets --touch`.
  Default taken.
- N1: name the rule by what it covers ("the crew-standards rule of `.crew/verify.json`"), not by an index that moves.
  Editing a released CHANGELOG entry's wording is allowed because the line is false at every commit since it merged.
  Default taken.
- N3: re-balance the six cells so each "(T-0010 landing lint fixes, crew 1.0.61" closes before "; on T-0085's line";
  codemap history wording only, under the refresh-artifact standing rule. Default taken.
- N5: `_scope` stops prepending "(fallback)" when `why` already contains it. Default taken.
- Tooling half F2: `reserve` takes the gate decision with it (`gated: bool`) and, under the ledger lock, refuses when
  the gate was skipped but the locked state no longer justifies skipping it (not NEEDS_REPLAN and rounds left), so
  the caller re-runs. N4: the gate path catches `OSError`/`ValueError` from the incident read and skip log and exits 2
  "self-check gate could not run: ...", never 1. Default taken.

## Approval
Direction approved 2026-10-05 for cloud hand-off, by the orchestrator under the owner's standing self-approve
authority (2026-09-26, reaffirmed 2026-09-27 and 2026-10-05).
