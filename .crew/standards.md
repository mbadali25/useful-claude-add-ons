---
set: REPO
applies-to: ["**"]
---

# useful-claude-add-ons standards overlay (REPO)

This repository's overlay on crew's plugin standards (`plugin/crew/skills/crew-standards/`). It adds
REPO-01 to REPO-03, classes crew's own reviews found in fewer than three change sets or that name this
repository's files, and supplements four plugin standards with this repository's literal commands.
Tracked, so it reaches every clone. It never removes or weakens a plugin standard. Mined by T-0085 from
this repository's review findings; a new standard or amendment is added here by hand, after the owner
approves the proposal `/crew:review` wrote for it.

## REPO-01 Identity is complete, canonical and proven

**Rule.** When code decides "same X" (repository, ticket, holder, session, lock owner, window), the key
includes every distinguishing component; equivalent spellings are canonicalised through the
authoritative resolver (`git remote get-url`, `realpath`, percent-decoding before parsing); different
things never collide (separators escaped, case kept where the source is case-sensitive); every
comparison calls one function; ownership is proven by a fact unique to this instance, never inferred
from process ancestry or proximity.

**Why.** 18 findings, 2 change sets (T-0030 14, T-0016 4); overlay until a third change set earns it.

**Self-check.**
1. Table and test per row: two spellings of one thing give one key (case, percent-encoding, relative vs
   absolute, `insteadOf`, trailing `.git`, ssh vs https); two different things give two keys (separator
   in a name, case-sensitive names). Pass: all rows green.
2. Every comparison of the identity calls one function. Pass: yes.
3. For every "this is mine" decision (window, console, lock, claim): name the fact unique to this
   instance (pid plus start time, a session id visible in the target, a token this process wrote), and
   test two siblings under one shared parent (one `gnome-terminal-server`, one VS Code pty host). Pass:
   two different targets, or a refusal.

**Earned by.** T-0030 r4 @4a50b3d3, FIX `plugin/crew/hooks/scripts/crew_coord.py:763`: "repo_key reads the raw
`remote.origin.url` config value, so git's `url.<base>.insteadOf` rewriting is never applied. [...]";
T-0030 r5 @81617867, FIX `plugin/crew/hooks/scripts/crew_coord.py:808`: "Joining segments with unescaped dots
conflates different repositories [...]"; T-0016 r1 @1275d2c4, FIX `plugin/crew/hooks/scripts/crew_autocycle.py:786`
(the line is `found = resolve_target(ancestors(owner["pid"]), windows, ...)`): "Proving the owner does not prove
the window is this session's when sibling sessions share one window-owning ancestor [...]"; its round-2
neighbour, T-0016 r2 @57656e34, FIX `plugin/crew/hooks/scripts/crew_autocycle.py:619`: "Round-1 finding 3 is
only partly fixed. [...]"

## REPO-02 A change detector sees every write channel

**Rule.** A fingerprint or tamper check covers every channel the watched state can change through
(untracked and ignored file contents, modes, symlink targets, nested repositories, index flags such as
skip-worktree, names colliding with the detector's metadata, blocking special files); it is taken
before anything that can write runs; every exemption is fixed before the watched process starts, from
a source it cannot write, and an exemption added for a known writer is itself a channel; a write by a
known other party is attributed to that party.

**Why.** 14 findings, all T-0028 (`review_run.py`, `kimi_probe.py`); overlay (one change set).

**Self-check.**
1. Per channel: a test that writes through it and sees the detector report it. Pass: yes.
2. Run the detector while a known concurrent writer (a post-commit rebuild, a hook) writes. Pass: the
   write is attributed to that writer, not the watched party.
3. Is every exemption fixed before the watched process starts, with a test that the watched party
   cannot widen it by writing config? Pass: yes.

**Earned by.** The fix-and-neighbour pair: T-0028 r1 @6f005fa2, FIX `plugin/crew/hooks/scripts/review_run.py:464`:
"The fingerprint blames the reviewer for any write made during the run [...] the post-commit and
post-checkout hooks rebuild the tracked graphify-out/graph.json and GRAPH_REPORT.md in the background
[...]", and its round-2 fix walked around one rung over, T-0028 r2 @0aab3a8f, FIX
`plugin/crew/hooks/scripts/review_run.py:301` (`graph = graph_out(root)`, read after the run): "reviewer_changes
decides which directory to set aside as `graph.out` only after the review has run, by reading the tree
the reviewer could write to. [...]". Also T-0028 r3 @44eed691, FIX `plugin/crew/hooks/scripts/review_run.py:246`:
"tree_fingerprint cannot see an edit to a tracked file that has been flagged skip-worktree or
assume-unchanged. [...]"

## REPO-03 Release bookkeeping for this marketplace

**Rule.** The version bump lands on the land branch at push time, after the review receipt, one patch
above `origin/main`'s version then (T-0043 `spec.md:29`: "The number is set on the land branch: one patch
above origin/main's crew version at land time"; `spec.md:34`: "The version bump on the land branch comes
after the review receipt"), and the build branch carries none: it declares the version of the
`origin/main` it last merged, whatever its plugin content. So `scripts/check-marketplace.py`'s
version-drift check reports `<plugin>: <source>/ has changed since version <X> was set` on a build branch
that changes plugin content; that is expected until landing and is not a finding. `--pending-bump`
(L-0511) says so mechanically: it prints that drift as `pending at land: ...` and exits 0 for that check
alone, every other check unchanged; verify rule 0 and CI's Marketplace job on a DRAFT pull request pass it,
and it is ignored on branch `main`. A ready pull request (the `ready_for_review` event re-runs the job) and
every push to `main` run the full check. The stale-copy bug
CLAUDE.md's first stop-and-ask names is closed at land, where the bump is made and the same check must
exit 0. At implement, check only that plugin content changed, that the build branch declares main's
version (no bump), and that the land-time bump is planned. At land: greater than `origin/main`'s version,
declared by no open PR branch and no other worktree's `plugin.json`, the branch rebased on current main,
CHANGELOG edits add sections and never rename a heading, `python3 scripts/check-marketplace.py` exits 0.

**Why.** `claude plugin update` compares declared versions, not contents (CLAUDE.md "Stop and ask").
6 findings, 5 change sets, but every check names this repository's files, so it is overlay by nature.

**Self-check.** On the build branch: `git diff origin/main -- plugin/crew/.claude-plugin/plugin.json
.claude-plugin/marketplace.json` shows no version line (no bump); a version-drift report from
`check-marketplace.py` is expected there, and `check-marketplace.py --pending-bump` exits 0 with it as a
`pending at land:` line. At land: `git fetch origin && git show origin/main:plugin/crew/.claude-plugin/plugin.json`
(branch is greater); `gh pr list --state open` plus each worktree's `plugin.json` (not already declared);
`git merge-base --is-ancestor origin/main HEAD` exits 0; `python3 scripts/check-marketplace.py` exits 0;
`git diff origin/main...HEAD -- CHANGELOG.md` shows no removed `###` heading.

**Earned by.** T-0072 r5 @a0978df6, BLOCK `plugin/crew/.claude-plugin/plugin.json:3`: "The declared 1.0.50 no
longer sits one patch above current main [...]"; T-0001 r2 @eb7866f2, BLOCK `.claude-plugin/marketplace.json:218`:
"Acceptance check 3 fails at HEAD eb7866f2: `python3 scripts/check-marketplace.py` exits 1 [...]"; T-0003 r1
@cf3bc0d8, FIX `CHANGELOG.md:7`: "The hunk replaces the existing `### Changed` heading [...]". T-0016 r1
@1275d2c4, FIX `plugin/crew/.claude-plugin/plugin.json:3` is kept with a note: its premise, "the plan
assigned this ticket 1.0.40", is the plan-assigned version scheme that T-0043's land-time rule
superseded. Amendment, owner-approved 2026-09-28 from T-0085 review round 1's proposal 4: T-0085 r1
@8ab20e16, FIX `plugin/crew/.claude-plugin/plugin.json:3`: "The build branch sets crew to 1.0.55, as do
marketplace.json:218, PLUGINS.md:14 and a versioned CHANGELOG heading. It went through 1.0.52, then 1.0.53,
then 1.0.55. This contradicts the spec Exclusion ("Version bump is not set at implement") [...]"; the
provisional build-branch bump the rule used to ask for is withdrawn.

## Supplements GEN-08

`CLAUDE_PLUGIN_ROOT` in shell text is quoted (GEN-06), and `pwsh` is named absolutely (CLAUDE.md
"Landmines"). `pathlib.write_text` on a `.sh` passes `newline="\n"` (CLAUDE.md "Landmines").

## Supplements GEN-09

Doc set to search for the old description: `plugin/crew docs README.md CHANGELOG.md plugin/PLUGINS.md
CLAUDE.md .crew/codemap`; a `plugin/crew/` change updates every document CLAUDE.md "Scope discipline"
lists, or says `Docs: none - <why>` in its PR body or a `Docs:` commit trailer. Parsed files: spec
templates through `crew_ticket.validate` (not `sections()` alone); `.crew/codemap/*.md` through `graphify update .` with
node and link counts compared; a number this repository states about itself carries a
`<!-- claim: ... -->` marker so `scripts/check-marketplace.py` checks it.

## Supplements GEN-11

Sibling search root: `plugin/crew`. A new marketplace entry is registered in every place CLAUDE.md
"Scope discipline" lists, in the same commit.

## Supplements GEN-12

Receipts: `.crew/.verify-verified-at` equals `git rev-parse HEAD` on a clean tree and
`.crew/.verify-gate.record.json`'s `rules` is empty or explained, the same comparison as
`review_prompt.py`'s `_receipts_block` (`verified == head and not manifest.get("dirty")`); no
`.crew/.scope-base` left in the bundle; lint = `.crew/verify.json`'s ruff and pylint rule. Heavy suites
run one at a time on a shared host.
