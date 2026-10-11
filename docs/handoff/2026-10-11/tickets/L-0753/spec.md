# L-0753: /crew:done judges the ticket's own diff, finds its CHANGELOG entry wherever it sits, and accepts a same-tree PR-head CI receipt          status: spec   risk: high
Written against origin/main `a7fb104b0` (crew 1.2.16, 2026-10-09). Direction: `direction.md` (parts a-d).

## Intent
A merged ticket closes with `/crew:done` without a refresh PR, while everything the ticket itself owes is
still refused.

One changed set for checks 4 and 5, `crew_refresh_check.own_changes(top, base, ticket)`:
- Before the ticket lands, it is `completion_audit.changed_paths(top, base, merged_main.resolve(top, base))`,
  the completion audit's own set (paths identical to merged main are left out).
- After the ticket lands (HEAD is already inside the integration ref, so `merged_main` would drop every
  committed path, its documented corner), it is the paths the ticket's landing merge brought to main:
  the first commit M on the ref's first-parent line that contains the review receipt's head
  (`.work/tickets/<id>/review.json` `head`), when M is a merge. The set is
  `since-base ∩ (diff(M^1, M) ∪ working-state changes vs HEAD)`. Paths identical to main before the
  landing are main's, the same rule as `merged_main.keep`.
- Could not tell (`merged_main` cannot tell; no readable receipt head; the head is not in this history;
  M is not a merge; any git failure) means the FULL since-base set, with the reason on the check's top line.
  An unknown never narrows the set.

Check 5's CHANGELOG row reads the lines added in the ticket's own range: merged main (or the base) to
the working tree before landing, M^1 to M after. The version it wants is the entry's version at the
range's end (disk before landing, M's `marketplace.json` after), so a later release never moves it.
A matching line sits under `## [Unreleased]` or under `## [<that version>]`, and names the plugin with
that version. A name counts in backticks anywhere on the line (today's form) or as the bare word
directly before the version (`crew 1.2.16`, the form every entry in this repo uses).

Check 2: when no `verify-gate.yml` run exists for HEAD's sha, `ci_receipt.check` tries HEAD's parents
whose tree equals HEAD's tree (second and later parents first, then the first). It judges the newest
run for that parent exactly as it judges a run for HEAD (status, conclusion, one artifact, receipt
fields). The receipt's `tree`, `verify_json` and `gate_impl` must equal HEAD's. When HEAD is a merge
whose first parent to HEAD changes a receipt-producer path, the merged branch's run vouched for its
own producer, so the answer is UNVERIFIED. A run for HEAD itself, when one exists, is still the only
run judged.

Addendum (2026-10-09, L-0733's close at main `f3ccccc3`): the unifying rule is that a merged ticket is
judged by its own landing merge against that merge's first parent. This ticket applies the rule to
checks 4 and 5 through `own_changes`, and to check 2 through the same-tree parent. A merged ticket closes
from a branch at `origin/main`. On `main` itself or a detached HEAD, `merged_main` is not applicable or
cannot tell, so checks 3-5 judge everything since the scope base. That is the 115-path refusal L-0733 saw,
and `done.md` says to use a branch. Check 3 is `completion_audit.py`, which is HARNESS. From a branch at
`origin/main` it already passes, through `merged_main`'s documented corner: it drops every committed path.
That pass is vacuous for the ticket's own out-of-Touch paths. Applying the landing-merge rule to check 3
is a harness change, so it goes to the tooling ticket L-0756 together with the sabotage entries, under
the standing split rule.

## Exclusions
- Check 3's landing-merge rule (completion_audit.py is HARNESS): L-0756.
- `merged_main.py`, `completion_audit.py`, `review_gate.py` and every other HARNESS path are not
  edited. Check 3 is unchanged.
- No `main` trigger is added to `verify-gate.yml` (direction option a).
- TODO.md and README rows keep their base-to-disk reading. Only the changed set they are given narrows.
- No ticket-subject or branch-name heuristic: the ticket's landing is found only through its review
  receipt.
- The sabotage entries go in `plugin/crew/tests/sabotage_*.py`, which is HARNESS. Under the standing
  split rule they ship in a follow-up tooling PR (next free L-). This PR proves each one red by hand
  and records the exact mutation in `notes.md`.
- No new setting, so there is no CONFIG.md row.

## Evidence
- `plugin/crew/hooks/scripts/crew_docs_check.py:450`: `changed_paths(top, base)` is called with no
  `merged`. `:261-293` `_changelog_rows`; `:203` `unreleased_range`; `:255` `_names_version` wants
  `` `crew` `` in backticks plus the current disk version.
- `plugin/crew/hooks/scripts/crew_refresh_check.py:1603`: the same call, with no `merged`.
- `plugin/crew/hooks/scripts/completion_audit.py:191-209` `changed_paths(top, base, merged)`;
  `:342-346` the audit passes `merged_main.resolve(top, base)`.
- `plugin/crew/hooks/scripts/merged_main.py` docstring: "A branch already merged into main drops
  everything committed". So on a post-merge close, passing `merged` alone would empty the set and pass
  the ticket's own stale artifacts. That is why the landing-merge branch exists.
- `CHANGELOG.md:12` `### Fixed — crew 1.2.16: ...` (L-0739). That line has no backticked `crew`, so
  today's predicate misses it.
- `plugin/crew/hooks/scripts/ci_receipt.py:409-414` `_newest_run(head_sha=HEAD)`; `:443` mismatch
  binds `head`; `:426-432` producer check `origin/main...HEAD`.
- `.github/workflows/verify-gate.yml:28-31`: no `main` push trigger.
- Live: main `a7fb104b0` tree == PR head `221ffe9b9` tree (`784becc1cc`), verify-gate run 37934636285
  passed (attempt 2). The L-0739 receipt head is `6acbf13af`.

## Unknowns
- U1: a ticket landed by two PRs (feature half and refresh). Answer: only the merge that first
  contains the receipt head is the ticket's. A refresh PR's changes count as another PR's. That is
  safe, because a refresh only re-anchors.
- U2: closing from a later main HEAD (others merged after M). Check 4/5's own set is still
  diff(M^1, M). Check 2 then has no same-tree parent and stays UNVERIFIED (bytes not gated), as
  direction (d) requires.
- U3: closing on `main` itself. `merged_main` says it is not applicable there, so the full set is used:
  today's behaviour, and it refuses. done.md says to close from a branch at origin/main.

## Touch
- `plugin/crew/hooks/scripts/crew_refresh_check.py`
- `plugin/crew/hooks/scripts/crew_docs_check.py`
- `plugin/crew/hooks/scripts/ci_receipt.py`
- `plugin/crew/tests/test_done_own_changes.py`
- `plugin/crew/tests/test_ci_receipt.py`
- `plugin/crew/tests/test_docs_check.py`
- `plugin/crew/tests/test_refresh_check.py`
- `plugin/crew/commands/done.md`
- `plugin/crew/commands/docs.md`
- `plugin/crew/README.md`
- `docs/guides/crew/src/troubleshooting.md`
- `docs/guides/crew/src/daily-workflow.md`
- `docs/guides/crew/crew-troubleshooting.html`
- `docs/guides/crew/crew-troubleshooting.docx`
- `docs/guides/crew/crew-troubleshooting.pdf`
- `docs/guides/crew/crew-daily-workflow.html`
- `docs/guides/crew/crew-daily-workflow.docx`
- `docs/guides/crew/crew-daily-workflow.pdf`
- `docs/diagrams/process-crew-lifecycle-done.mmd`
- `docs/diagrams/README.md`
- `docs/diagrams/index.html`
- `.crew/codemap/crew.md`
- `.crew/codemap/verification-harness.md`
- `.claude/rules/crew.md`
- `CHANGELOG.md`
- `README.md`
- `plugin/crew/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `plugin/PLUGINS.md`
- `plugin/crew/BUDGETS.md`

## Acceptance checks
1. must-allow (a): a ticket whose own diff adds `## [1.2.11]` with a line naming `crew` 1.2.11 reads
   CHANGELOG `updated` before landing, after landing, and after a later 1.2.12 merges to main.
   `### Fixed — crew 1.2.16: ...` under `[Unreleased]` also reads `updated`.
2. must-block (a): own diff adds no CHANGELOG line, so MISSING. A line naming another version, or one
   added only by merged main, is also MISSING.
3. must-allow (b): the ticket changes no SECURITY_PATHS path while merged main brings in a workflow
   change, so `SECURITY.md: not needed`, both before and after landing.
4. must-block (b): the ticket changes a workflow itself, so MISSING unless it is edited or has a reason.
5. must-allow (c): a diagram/codemap whose cited path changed only through merged main does not refresh
   stale (fresh or not reached).
6. must-block (c): an artifact citing a path the ticket changed reads stale, before and after landing.
7. must-block (could not tell): a detached HEAD (merged_main cannot tell), a post-merge close with no
   receipt, or a receipt head outside the history judges the full set, so the merged-in workflow and the
   other PR's stale artifact still refuse.
8. must-allow (d): a merge HEAD with no run of its own, whose second parent has the same tree and a
   passing run, reads VERIFIED and names both shas.
9. must-block (d): a merge HEAD whose tree differs from every parent with a passing run is UNVERIFIED.
   A failing run lookup for the parent is UNKNOWN, as is a parent tree git cannot read. A receipt whose
   tree differs from HEAD's is UNVERIFIED. A merge that changes a producer path is UNVERIFIED. A HEAD
   with its own failed run never falls back.
10. Sabotage (by hand here; entries filed for the tooling PR): (i) drop the `merged` argument in
    own_changes, which turns 3 and 5 red; (ii) restrict the CHANGELOG match to `[Unreleased]`, which turns
    1 red; (iii) return the merged-main set post-merge (no landing branch), which turns 6-after-landing
    red; (iv) skip the parent tree comparison, which turns 9 red; (v) bind the parent run without the
    receipt tree check, which turns 9 red; (vi) treat could-not-tell as the narrowed set, which turns 7 red.
11. `python3 scripts/check-marketplace.py`, `scripts/check-tooling-pr.py` and
    `scripts/check-crew-docs.py` pass. The affected suites are green.
12. Dry run: `/crew:done` checks 2-5 for L-0739 and for L-0733, each run from a branch at origin/main with
    this code. Each check passes, or the report says exactly why not.
