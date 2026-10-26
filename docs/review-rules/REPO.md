<!-- crew-standards-export digest=df6052ac0825389b086b6ca038d9f2c0e191ea1a5407dee8f55424f8dff3a8e6 crew=1.2.86 -->
# Review rules: set REPO

Applies to: always (`**`).
Generated from crew's standards by `crew_standards.py export --write`; do not edit by hand. Check a change against every standard here whose scope matches the files it touches.

## REPO-01 Identity is complete, canonical and proven

**Rule.** When code decides "same X" (repository, ticket, holder, session, lock owner, window), the key
includes every distinguishing component; equivalent spellings are canonicalised through the
authoritative resolver (`git remote get-url`, `realpath`, percent-decoding before parsing); different
things never collide (separators escaped, case kept where the source is case-sensitive); every
comparison calls one function; ownership is proven by a fact unique to this instance, never inferred
from process ancestry or proximity.

**Self-check.**
1. Table and test per row: two spellings of one thing give one key (case, percent-encoding, relative vs
   absolute, `insteadOf`, trailing `.git`, ssh vs https); two different things give two keys (separator
   in a name, case-sensitive names). Pass: all rows green.
2. Every comparison of the identity calls one function. Pass: yes.
3. For every "this is mine" decision (window, console, lock, claim): name the fact unique to this
   instance (pid plus start time, a session id visible in the target, a token this process wrote), and
   test two siblings under one shared parent (one `gnome-terminal-server`, one VS Code pty host). Pass:
   two different targets, or a refusal.

## REPO-02 A change detector sees every write channel

**Rule.** A fingerprint or tamper check covers every channel the watched state can change through
(untracked and ignored file contents, modes, symlink targets, nested repositories, index flags such as
skip-worktree, names colliding with the detector's metadata, blocking special files); it is taken
before anything that can write runs; every exemption is fixed before the watched process starts, from
a source it cannot write, and an exemption added for a known writer is itself a channel; a write by a
known other party is attributed to that party.

**Self-check.**
1. Per channel: a test that writes through it and sees the detector report it. Pass: yes.
2. Run the detector while a known concurrent writer (a post-commit rebuild, a hook) writes. Pass: the
   write is attributed to that writer, not the watched party.
3. Is every exemption fixed before the watched process starts, with a test that the watched party
   cannot widen it by writing config? Pass: yes.

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

**Self-check.**
On the build branch: `git diff origin/main -- plugin/crew/.claude-plugin/plugin.json
.claude-plugin/marketplace.json` shows no version line (no bump); a version-drift report from
`check-marketplace.py` is expected there, and `check-marketplace.py --pending-bump` exits 0 with it as a
`pending at land:` line. At land: `git fetch origin && git show origin/main:plugin/crew/.claude-plugin/plugin.json`
(branch is greater); `gh pr list --state open` plus each worktree's `plugin.json` (not already declared);
`git merge-base --is-ancestor origin/main HEAD` exits 0; `python3 scripts/check-marketplace.py` exits 0;
`git diff origin/main...HEAD -- CHANGELOG.md` shows no removed `###` heading.

