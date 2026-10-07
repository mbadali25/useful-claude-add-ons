# L-0518: T-0085 round-4 follow-up (feature half): proposals trusts the round's recorded verdict, SHA-256 stamps, plan-time `sets --touch`, four NITs          status: spec   risk: medium
T-0085 (#269, crew 1.0.75) review round 4, owner "Accept, follow-up" 2026-09-30. Written against origin/main
`a555ff37` (crew 1.1.0). The round-4 lines were at `0c6f01e0`; every one was re-found by content here (direction.md
table). Re-find again at implement time.

## Intent
Fix the five non-harness round-4 findings in `crew_standards.py` and its docs:
**F1** `proposals --round N` writes a proposals file only when the review ledger records round N as CLEAN or
FINDINGS; a round recorded INCOMPLETE (non-zero exit, timeout, unacknowledged bundle part, bundle problems, webtest
reasons), a round with no row, or an unreadable ledger is refused with nothing written, so the exclusive create stays
free. **F3** the stamp line's `base=` parses as exactly 40 or exactly 64 lowercase hex, so a SHA-256 repository can
stamp and pass the gate. **F4** `crew_standards.py sets --touch` lists the effective set from the spec's Touch list
(stack sets whose `applies-to` overlaps a Touch entry) with no scope base, and the plan self-review names it.
**N1/N2/N3/N5** fix the stale rule number in CHANGELOG, the "The An" fragment in the skill, the six codemap history
cells, and the doubled "(fallback)". The harness findings (F2, N4) and all sabotage entries are a separate
tooling-only follow-up, specified below in "Tooling half" for the coordinator to mint.

## Exclusions
- No harness path in this PR: `review_run.py`, `review_ledger.py`, `review_verdict.py`, `review_prompt.py`,
  `crew_ticket.py`, `commands/review.md`, `plugin/crew/tests/sabotage*.py` are read or imported, never edited
  (`scripts/check-tooling-pr.py` `HARNESS`). `commands/review.md:531` ("An INCOMPLETE round's `out.txt` is refused")
  stays true as a subset of the new behaviour; its wording update rides with the tooling half.
- The round-4 BLOCK (sabotage run) is answered (42 RED at `0c6f01e0`) and is not re-opened.
- No change to `proposals`' output format, the NIT filter, the exclusive create, or the `out.txt` parse (kept as a
  second check after the ledger check).
- No change to plain `sets` (scope base + diff), `init`, `stamp` semantics other than F3's regex, or the gate.
- No other base length: a 41-63 or 65+ hex `base=` still does not parse.
- No hook, no config key (`plugin/crew/CONFIG.md` unchanged). No version bump on the build branch (REPO-03).

## Evidence
origin/main `a555ff37`:
- F1: `plugin/crew/hooks/scripts/crew_standards.py:725` `proposals`, `:745` `review_verdict.parse(text, 0)` (exit 0,
  no `expected_parts`). Round verdicts are recorded by `review_run.finish` (`plugin/crew/hooks/scripts/review_run.py:534`)
  into the ledger via `review_ledger.record` (`plugin/crew/hooks/scripts/review_ledger.py:357`, row
  `"verdict": review["verdict"]` `:390`) before `review.json` (`review_run.py:595-600`); read back with
  `review_ledger.status` (`review_ledger.py:962`), rows under `"rounds"`. Tests: `plugin/crew/tests/test_crew_standards.py:601`,
  `:623`, `:1186`, `:1204`, `:1226` call `proposals` with no ledger; they gain a ledger fixture.
- F3: `crew_standards.py:87-88` `_STAMP_RE ... base=([0-9a-f]{40})`; read `:387`; written `:569` from
  `scope_base.resolve`, which has no 40-hex limit.
- F4: `plugin/crew/skills/crew-plan/SKILL.md:72` ("`crew_standards.py sets` lists them"); `_sets` `crew_standards.py:875`
  calls `_scope` `:461`, which refuses with "no scope base recorded ... run scope_base.py --record" before
  `/crew:implement` step 1. Touch reader `crew_ticket.parse_touch` (`plugin/crew/hooks/scripts/crew_ticket.py:315`);
  overlap matcher `recurring_findings.matches(path, glob, touch=True, root=root)` (`plugin/crew/hooks/scripts/recurring_findings.py:252`),
  as `implementer_block` `:366-388` uses it. `sets` documented at `plugin/crew/skills/crew-standards/SKILL.md:39-40`.
- N1: `CHANGELOG.md:4155` "Rule 31 of `.crew/verify.json` also runs on the scripts ..."; today
  `python3 -c "import json;r=json.load(open('.crew/verify.json'))['rules'];print([i for i,x in enumerate(r) if 'crew_standards.py' in str(x['paths'])])"`
  prints `[38, 41]` (41 is the crew-standards rule, `.crew/verify.json:483-496`).
- N2: `plugin/crew/skills/crew-standards/SKILL.md:102-103` "Proposal to fill. The / An `out.txt` ...".
- N3: `.crew/codemap/INDEX.md:299-302`, `:305`, `:308` contain "(T-0010 landing lint fixes, crew 1.0.61; on T-0085's line"
  (`grep -c "crew 1.0.61; on T-0085's line" .crew/codemap/INDEX.md` is 6).
- N5: `crew_standards.py:490` `note = f"(fallback) {why}"`; `why` already ends with `scope_base.py:121` `_FALLBACK`
  "... (fallback)". Test `test_stamp_scope_fallback_when_the_record_is_unusable` `test_crew_standards.py:896`.
- Docs describing these: `plugin/crew/README.md:805` (proposals row), `docs/guides/crew/src/daily-workflow.md:87`,
  `.crew/codemap/crew.md:1879-1880` (proposals), `plugin/crew/skills/crew-standards/SKILL.md:39-40`, `:99-107`.

## Unknowns
- **F1, a ledger with the round but from another provider's retry** (a refunded round): proposals takes the row whose
  `round` equals `--round`; a refunded row reads as not CLEAN/FINDINGS and refuses. Confirmed against
  `review_ledger.summary` at implement.
- **F4 globs vs Touch globs.** A Touch entry can be a glob or a directory; `recurring_findings.matches(touch=True)`
  already over-includes on purpose (two wildcard segments overlap). Accepted: plan time over-lists, never under-lists.
  A spec with no Touch section, or one that cannot be read, prints `UNKNOWN:` and lists every stack set, exit 1.
- **F3 test repo.** `git init --object-format=sha256` needs git >= 2.29; a test skips with the reason printed only
  when git cannot create one (`git --version` checked), never silently.
- Next free crew patch version set at land.

## Size and split
About 45 production lines in `crew_standards.py` (F1 ~20, F3 1, F4 ~20, N5 2), about 120 test lines, doc lines.
Split: the harness half (F2, N4, sabotage entries for F1/F3/F4/N5, `commands/review.md:531` wording) is a separate
tooling-only ticket, below. No further split.

## Touch
- `plugin/crew/hooks/scripts/crew_standards.py`
- `plugin/crew/tests/test_crew_standards.py`
- `plugin/crew/skills/crew-standards/SKILL.md` - N2; `sets --touch`; the proposals refusal names the ledger
- `plugin/crew/skills/crew-plan/SKILL.md` - F4 (`:72`)
- `plugin/crew/commands/plan.md` - only if its Standards line names `sets` (`:36` today does not; check)
- `plugin/crew/README.md` - `:805` proposals row; the `sets --touch` mention
- `docs/guides/crew/src/daily-workflow.md` - `:87` proposals sentence
- `docs/guides/crew/**` - HTML, DOCX and PDF rebuilt by `docs/guides/crew/src/build.py`
- `.crew/codemap/crew.md` (`proposals`, `sets`, the stamp regex) and `.crew/codemap/INDEX.md` (N3, re-anchor)
- `.crew/codemap/**` re-anchor
- `CHANGELOG.md` - N1 and this ticket's entry
- `plugin/crew/BUDGETS.md`
- `plugin/crew/.claude-plugin/plugin.json` - version, at land only
- `plugin/PLUGINS.md` - version line, at land only
- `.claude-plugin/marketplace.json` - version, at land only
- `.claude/rules/**` regenerate only; `graphify-out/**` `graphify update .` only
- `docs/tickets/L-0518/` (removed in the final PR)

Not in Touch: every HARNESS path (above); `plugin/crew/CONFIG.md`; `.crew/verify.json` (the files are mapped by rule 41);
`docs/diagrams/**` (no box or edge changes; say so in the PR).

## Acceptance checks
Commands from the repo root. `T` is `plugin/crew/tests/test_crew_standards.py`; run as
`python3 plugin/crew/tests/pytest_rule.py T -q -k <name>`.
- [ ] F1 must-block: a ledger whose round 1 is INCOMPLETE (exit_code 1), with `out.txt` = `READ|part-001-of-003.patch`
  and `BLOCK|a.py:1|x|y`: `proposals --round 1` exits 1, names the round's recorded verdict, writes nothing; a second
  run after the ledger records a FINDINGS round 2 with `--round 2` succeeds. Also refused: no ledger, an unreadable
  ledger, no row for N. `-k "test_proposals_refuses_a_round_the_ledger_records_incomplete or test_proposals_refuses_without_a_ledger_row"`
- [ ] F1 must-allow: the existing proposals tests pass with a ledger fixture recording FINDINGS/CLEAN for the round.
  `-k proposals`
- [ ] F3: in a `git init --object-format=sha256` repo, `scope_base.py --record`, a change, an approval receipt, `init`,
  answered rows, `stamp` exit 0, and `review_gate` reports no problem; a 41-hex and a 63-hex `base=` still refuse.
  `-k "test_stamp_and_gate_in_a_sha256_repository or test_stamp_base_of_another_length_refuses"`
- [ ] F4: on an approved ticket with no scope base, `sets --root R --ticket T-1 --touch` exits 0 and lists GEN plus
  every stack set whose `applies-to` overlaps a Touch entry (a `plugin/x/*.py` Touch entry lists PYTHON; a
  `docs/**` one does not); a spec with no Touch section prints `UNKNOWN:`, lists every stack set, exits 1; plain `sets`
  without a base still refuses as today. `-k "test_sets_touch_needs_no_scope_base or test_sets_touch_unknown_lists_every_set or test_stamp_refuses_without_a_scope_base"`
- [ ] N5: `-k test_stamp_scope_fallback_when_the_record_is_unusable` asserts "(fallback)" appears exactly once in the
  stamp line, for every parametrised shape.
- [ ] N2: `grep -n "The$" plugin/crew/skills/crew-standards/SKILL.md` prints nothing inside the Proposals bullet, and
  `grep -c "The An" plugin/crew/skills/crew-standards/SKILL.md` is 0.
- [ ] N1: `grep -n "Rule 31 of" CHANGELOG.md` is empty.
- [ ] N3: `grep -c "crew 1.0.61; on T-0085's line" .crew/codemap/INDEX.md` is 0, and each of the six cells' parentheses
  balance (`python3 -c` over the six rows: `(` count equals `)` count before and after each `; on T-0085's line`).
- [ ] Whole suites: `python3 plugin/crew/tests/pytest_rule.py T plugin/crew/tests/test_review_run_standards.py plugin/crew/tests/test_recurring_findings.py -q`
- [ ] `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` (no harness path touched).
- [ ] Docs: crew-standards and crew-plan skills, README, the daily-workflow guide and the code map describe the new
  refusal and `sets --touch`; guides rebuilt; CHANGELOG entry; BUDGETS.md re-measured; crew bumped at land;
  `python3 scripts/check-marketplace.py` passes after the commit.

## Tooling half (separate tooling-only ticket, id minted by the coordinator; lands after this one)
Harness paths only, plus their tests and docs. Not built in this PR.
- **F2** `plugin/crew/hooks/scripts/review_run.py:854-863`: the skip decision (`NEEDS_REPLAN` or `rounds_left == 0`) is
  read by `review_ledger.status` outside the lock, and `review_ledger.reserve` (`plugin/crew/hooks/scripts/review_ledger.py:314`)
  re-reads under the lock without it. Fix: `reserve(..., gated=<bool>)`; under the lock, when `gated` is False and the
  locked state would require the gates (not NEEDS_REPLAN and rounds left), refuse with "the ledger changed since the
  gate decision; run again", nothing spent. Must-block test: monkeypatch `review_ledger.status` to return NEEDS_REPLAN
  while the ledger file holds IN_REVIEW with rounds left; `run` refuses, no round reserved. Must-allow: a real
  NEEDS_REPLAN and a real spent budget still answer as today (`test_run_reports_a_spent_budget_before_the_selfcheck`,
  `plugin/crew/tests/test_review_run_standards.py:306`).
- **N4** `review_run.py:712-714` (`crew_incident.read_state(..., crew_state.load_config(...))`, `crew_incident.log_skip`)
  inside `standards_gate` `:699`; `main` catches only `review_ledger.LedgerError` `:1000`. Fix: catch `OSError` and
  `ValueError` there (and in `prereview_gate`'s same pair `:762-764`), print `review-run: self-check gate could not run: <exc>`,
  return `EXIT_USAGE` (2, nothing spent). Test: `.crew/` read-only (or `log_skip` monkeypatched to raise) during an
  active incident with no selfcheck.md: exit 2, no traceback.
- `plugin/crew/commands/review.md:531`: "An INCOMPLETE round's `out.txt` is refused" -> "A round the ledger does not record
  as CLEAN or FINDINGS is refused" (F1's behaviour).
- Sabotage entries in `plugin/crew/tests/sabotage_standards.py` (`STANDARDS_MUTATIONS`): F1 ledger check removed (red:
  `test_proposals_refuses_a_round_the_ledger_records_incomplete`); `_STAMP_RE` back to `{40}` (red: the sha256 test);
  `sets --touch` falls back to `_scope` (red: `test_sets_touch_needs_no_scope_base`); `"(fallback) "` prefix restored
  unconditionally (red: the N5 test); F2's `gated` check removed; N4's catch removed.
- Its checks: `python3 scripts/check-tooling-pr.py` prints `tooling-pr: OK` for a harness-only change; the harness rule's
  suites (`scripts/_test/tooling-pr.py`, golden replay, seam contracts, canary review) per `.crew/verify.json`; every new
  mutation RED through `plugin/crew/tests/sabotage.py`.

## Dependencies
- T-0085 (#269): merged; the code these findings are in.
- L-0519 (sibling hand-off) edits `crew-standards/SKILL.md` near `:13-33`; L-0532..L-0538 edit `:18-22`. Different
  lines from N2 (`:102-103`) and `sets` (`:39-40`); whichever lands second merges main.
- The tooling half depends on this PR (its sabotage entries mutate this PR's code).

## Approval
Direction and spec approved for cloud hand-off by the orchestrator under the owner's standing self-approve
authority, 2026-10-05. Plan: to be written by the implementing session.
