# L-0648: promote-gate reads the github entry - the sha input must be the reviewed HEAD          status: direction   risk: high   priority: high

Split from T-0045 on 2026-10-04 (T-0045 direction.md, "Direction check 2026-10-04", option 1).

## Problem
promote-gate matches a deploy by substring against the declared `deploy` strings. For a `github` entry that is enough to fire the gate, but not enough to know what ships: the gate checks PASS rows for the tree's HEAD while the workflow deploys whatever the sha input says. Today it only refuses a literal sha that names a different commit. A dispatch with the sha input missing, given twice, or given as a branch name passes the gate and deploys something the gate never judged. A dispatch of the same workflow in a spelling that matches no declared prefix is not gated at all.

## Decision (kept from plan.md "Design", promote-gate section, minus what T-0505 and T-0062 took)
For an environment with `github` entries, both gate flavours add one rule after the environment matches: with `shaInput` configured, the command must carry that input exactly once, as 40 lowercase hex characters, equal to the full HEAD of the tree being deployed. A malformed `github` value is exit 4, like a malformed `deploy`. A `gh workflow run` naming a declared entry's workflow file that matches no declared prefix is blocked as could-not-tell.

## Options considered
1. **A small rule inside promote-gate, both flavours (recommended).** The check sits where the evidence is used.
2. Leave it to `prepare`. `prepare` prints the right command, but nothing forces the session to run that command.
3. Fold it into T-0062, which edits the same two files. Fewer merges; a larger guard change in one review.

## Depends on
T-0045 (the entry). Lands after T-0062 if T-0062 is in flight, because both edit promote-gate.sh and promote-gate.ps1. L-0564 (promote-gate review follow-ups) touches the same files.

## Open questions for the owner
- Fold into T-0062? Default: keep separate, land after it.
- The PowerShell half can only be run on native Windows. Default: verified on the Windows box before landing, reported as not run elsewhere.
