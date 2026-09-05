# Runbook: roll back a bad merge to `main`

last verified: 2026-09-05

Nothing here is deployed. "Production" is a merged commit on `main` that the README's
install one-liner can reach. So rollback is not a redeploy — it is `git revert` plus
re-pinning, and the failure mode is that people forget the second half.

## When to use this

- `check-marketplace.py` fails on `main`.
- A plugin was published with a broken `version` — either not bumped, or bumped to a
  value its `plugin.json` disagrees with.
- An install-script change breaks a fresh machine.

## Blast radius, so you know what you are racing

Once `main` moves, anyone running the README one-liner gets it. Worse, anyone running
`claude plugin update` gets a plugin whose **declared version** changed — and if the
rollback does not also move the version, their machine keeps the broken copy forever,
because the CLI compares declared versions and not contents. **A revert without a
version bump is not a rollback.**

## Steps

1. **Confirm what actually broke, on `main`, not locally.**
   ```bash
   git fetch origin && git checkout main && git pull --ff-only
   bash _verify/smoke.sh
   gh run list --limit 3 --json conclusion,headSha,workflowName
   ```

2. **Revert the merge, do not force-push.**
   ```bash
   git revert -m 1 <merge-sha>        # -m 1 for a merge commit; omit for a plain commit
   bash _verify/smoke.sh              # must be green BEFORE you push
   git push origin main
   ```
   Never `push --force` here. Other machines have already fetched; rewriting history
   leaves them on a commit that no longer exists and `claude plugin update` reports
   nothing wrong.

3. **Bump the version of every plugin the revert touched — this is the step that
   actually reaches people.**
   Reverting restores the old files but leaves the *declared* version wherever it was.
   Go **forward**, never back: if the bad release was `0.15.3`, ship `0.15.4` carrying
   the reverted content. Bump it in `.claude-plugin/marketplace.json` **and** the
   plugin's own `.claude-plugin/plugin.json`, to the same value. `check-marketplace.py`
   enforces the agreement; nothing enforces that you remembered to do it at all.

4. **Re-pin the README install URLs — only if `scripts/install-prerequisites.{sh,ps1}`
   changed.**
   ```bash
   git rev-parse HEAD
   # then replace the SHA in BOTH raw.githubusercontent.com URLs in README.md
   ```
   Verify whether it is even needed, rather than assuming from the SHA looking old:
   ```bash
   git diff --stat <pinned-sha>..HEAD -- scripts/install-prerequisites.sh scripts/install-prerequisites.ps1
   ```
   Empty output means the pin is still correct no matter how many commits have passed.
   On 2026-09-05 the pin was 19 commits behind HEAD and that diff was empty — the pin
   was correct. Do not "fix" a pin that is not broken; a needless re-pin invalidates
   nothing but costs a commit and trains people to churn it.

5. **Prove it reached a real machine.**
   ```bash
   bash scripts/_test/drift-detection.sh
   ```
   This drives the real `claude` CLI against a throwaway marketplace. No CI runner can
   do it. It is the only check that distinguishes "the version was bumped" from "an
   installed machine actually picked the change up".

6. **Record it.** Append a row to `.work/PROMOTIONS.md`. `verify-gate.sh` will not let
   the turn end after a deploy that wrote no row, and the next promotion reads that log
   to decide whether its prerequisites passed.

## Verification record

Exercised on 2026-09-05, against this repo:

| Step | How it was verified | Result |
|---|---|---|
| 1 | `bash _verify/smoke.sh`; `gh run list --limit 2 --json conclusion,workflowName` | smoke 8/8; gh returned two `success` rows |
| 4 | `git diff --stat 963c51a0..HEAD -- scripts/install-prerequisites.*` | empty — pin correct at 19 commits behind |
| 5 | command located; `drift-detection.sh` present and executable | not executed — it installs plugins via the real CLI |
| 2, 3 | **NOT exercised.** | A real revert needs a bad merge on `main` to revert. Doing it to test would be the incident. |

Steps 2 and 3 are written from the mechanism (`git revert -m 1`, and the declared-version
comparison that `claude plugin update` performs), not from a rehearsal. Treat them as
reasoned, not proven. Re-verify this runbook after the first real rollback, and replace
this table with what actually happened.
