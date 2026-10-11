# L-0753: /crew:done checks 4 and 5 are miscalibrated - every close needs a refresh PR

Filed 2026-10-09 by the L-0733 lane, on the lead's instruction (owner delegation). Citations are at
main `f91bb36a` (crew 1.2.12).

## What breaks

A ticket whose PR has merged cleanly still fails `/crew:done`. The only way through is a follow-up
"refresh" PR whose purpose is to satisfy the checks. That happened twice in a row:
- L-0713: #580, then refresh PR #590.
- L-0733: #587, then refresh PR #591.

### (a) Check 5 wants the CHANGELOG line under `[Unreleased]`, but the release process puts it under `## [x.y.z]`

`plugin/crew/hooks/scripts/crew_docs_check.py:261-293` (`_changelog_rows`) counts only lines added
inside the `## [Unreleased]` span (`unreleased_range`, `:203`; the filter at `:276-281`). A matching line
must name the plugin's version as it is on disk *now* (`_names_version`, `:255`). The repo's version
commit puts each ticket's entry under its own `## [x.y.z] - date` heading, as every crew version so far has.

So check 5 reads `CHANGELOG.md (crew <v>): MISSING - plugin/crew/ changed and no line added under
## [Unreleased] names `crew` <v>` on every close. Once another crew version merges, the "current version"
moves on, and even an `[Unreleased]` line goes stale: L-0713's second close attempt needed the line to
name a version that had not existed when it was written.

### (b) Check 5 counts security-relevant workflow changes that came in through main merges

`crew_docs_check.py:450` calls `completion_audit.changed_paths(top, base)` with no `merged` argument.
The changed set is therefore everything since the scope base, including whatever main merges brought
in. `_security_rows` (`:336-344`) then charges every `SECURITY_PATHS` hit (`:105`) to the ticket.

The completion audit itself already excludes paths that are identical to merged main
(`completion_audit.py:342-346`, `merged_main.resolve`, T-0100). Check 5 does not.

Evidence:
- L-0733 changes no workflow. Its `SECURITY.md: MISSING` came from `marketplace.yml` and
  `plugin-evals.yml` (merged in from #580, L-0713) and `verify-gate.yml` (from #583, L-0710).
- L-0713's own close was charged for `verify-gate.yml` from L-0710 in the same way; its `docs.json`
  says so.

### (c) Check 4 flags artifacts made stale by other merged PRs

`plugin/crew/hooks/scripts/crew_refresh_check.py:1603` also calls `changed_paths(top, base)` without
`merged`. Every diagram, code map and graph that cites a path any merged-in PR changed is then judged
against this ticket. Each one reads `stale - <path> changed since its anchor` (`:471`), and its
verdict comes from `_diagram_verdict` (`:1026`).

Evidence:
- L-0713's first close was refused on `process-crew-lifecycle` and `process-crew-lifecycle-done`.
  They went stale because of `commands/done.md`, which changed in #583 (L-0710), not in L-0713.
- In L-0733's close, the `graphify-out` stale list included paths from other merged PRs alongside
  L-0733's own.
- Honest caveat: L-0733's `data-flow-crew-config` WAS made stale by L-0733's own CONFIG.md edit. That
  part of the refusal was correct.

### (d) Check 2 can never pass on a merged main HEAD: verify-gate.yml never runs on main

Added 2026-10-09 (coordinator, from L-0739's close). Every close after a merge fails check 2 by
construction; L-0711, L-0712, L-0713 and L-0739 all parked on it.

- `.github/workflows/verify-gate.yml:28-31`: `on: push: branches: ['L-*', 'T-*', 'W-*']` plus
  `workflow_dispatch`. There is no `main` trigger.
- `plugin/crew/commands/done.md:18-32` (Check 2) passes only on `CI_RECEIPT VERIFIED` for exactly HEAD,
  `NO_GATE`, or a local `GATE VERIFIED` marker for HEAD.
- `plugin/crew/hooks/scripts/ci_receipt.py:409-414` looks runs up by `head_sha == HEAD`, and `:443` binds
  the receipt to it. At a merge commit on main no run has that sha, so the result is `CI_RECEIPT UNVERIFIED
  ... no verify-gate.yml run for HEAD`.
- L-0739, measured: main `a7fb104b0` (the #592 merge) has tree `784becc1cc`. The PR head `221ffe9b9`, whose
  verify-gate run 37934636285 passed, has the same tree. So the bytes were gated, and only the sha differs.

Fix options:
- **(b), recommended.** Check 2 accepts the PR head's passing run when that head's tree equals HEAD's tree.
  Optionally it also accepts the case where HEAD is a merge whose first parent is main and whose second
  parent is that head, as long as the trees are equal. Bind on the tree, the gate_impl and verify.json
  blob, as the receipt already does. Never bind on the sha prefix. This costs no CI per merge.
- **(a)** Run verify-gate on push to main. This is about 20 minutes of self-hosted CI per merge, and a close
  waits on it.

Acceptance (d):
- Must-allow: a merged main whose tree equals a PR head with a passing run reads VERIFIED.
- Must-block: a main tree that differs by any byte from every passing run's tree reads UNVERIFIED.
- Must-block: could-not-tell (the run lookup fails, or the tree cannot be read) is never VERIFIED.
- Sabotage: match on the sha only, or skip the tree comparison. Each must go red.

## Direction

Use one changed set for checks 3, 4 and 5: the ticket's own diff, with paths identical to merged main
left out. That is the set `completion_audit` already builds. Pass `merged_main.resolve(top, base)` to
`changed_paths` at `crew_docs_check.py:450` and `crew_refresh_check.py:1603`. Keep could-not-tell:
when `merged_main.resolve` cannot tell, nothing is left out, as `completion_audit` already does.

For the CHANGELOG, accept either of these:
- a line added under `[Unreleased]`, or
- an added `## [x.y.z]` section, where `x.y.z` is the version the ticket's version commit set,
  together with a line in that section that names the plugin.

That version must be the one in force at the ticket's merge. A close after later versions have merged
reads the ticket's own entry, not "the current version". One possible rule: the entry added by the
ticket's own commits, read from the merged diff, wherever it sits.

## Acceptance checks

- A ticket whose own diff adds `## [1.2.11]` with a line naming `crew` passes check 5's CHANGELOG
  row, both before and after a later crew version (1.2.12) merges to main.
- A ticket whose own diff adds no CHANGELOG line still fails check 5 (must-block).
- A ticket that changes no `SECURITY_PATHS` path, but has merged main bringing in a
  `.github/workflows/*.yml` change, reads `SECURITY.md: not needed`. A ticket that changes a workflow
  itself still needs an edit or a `docs.json` reason (must-block).
- A diagram whose anchor paths changed only through merged main reads fresh, or "not this ticket's".
  One whose anchor path this ticket changed reads stale (must-block).
- When `merged_main` cannot tell, checks 4 and 5 judge the full changed set, so unknown never
  becomes "not needed".
- Re-run `/crew:done` against L-0713's and L-0733's merged trees, using the fixtures, not the live
  repo: checks 4 and 5 pass with no refresh PR, apart from the artifacts the ticket made stale itself.
- Each new branch has a sabotage entry (drop the `merged` argument; restrict the CHANGELOG match to
  `[Unreleased]`) that goes red.

## Addendum (2026-10-09, L-0733 close at main HEAD f3ccccc3)

After its refresh PR #591 merged, `/crew:done L-0733` was re-run from a worktree at main HEAD. It
refused on three more checks:
- **Check 2.** `CI_RECEIPT UNVERIFIED head=f3ccccc3 ... no verify-gate.yml run for HEAD`. The
  verify-gate workflow runs only on L-/T-/W- branch pushes, so main's HEAD never has a run (part d).
- **Check 3.** `COMPLETION AUDIT: 115 changed path(s) outside L-0733's spec ## Touch`. At main
  HEAD, every PR merged since the scope base is in the diff.
- **Check 4.** Stale code map and diagrams, made stale by L-0710, L-0712 and L-0739.

So the ticket can be closed neither on its branch (other PRs' merged-in changes) nor at main
(everything since the scope base). The fix should define one closing tree and changed set for a
merged ticket: the ticket's own merge commit, diffed against its first parent. Every check would
then judge that tree.
