# L-0689: promote-gate matches a fragment of a declared deploy command and leaves a false in-flight marker
risk: med (a guard's match rule; today it fails closed, the fix must not open it)

## Ask
Owner decision 2026-10-04: file this ticket, write its direction and spec, and publish it as a docs-only draft PR for a cloud session.

## Problem
Reported on 2026-10-04 by a session working in another repository that uses crew.

`promote-gate.sh` decides "is this command a deploy" by text containment in BOTH directions: `d in cmd or cmd in d` (`plugin/crew/hooks/scripts/promote-gate.sh:213` for the working map, `:140` in `matches()` for the committed map, origin/main `baf193aa`). The `cmd in d` half is true for any command that is a fragment of a declared deploy command. With a map that declares, for example,

    gh workflow run deploy.yml -f environment=development -f ref=$(git rev-parse HEAD)

the commands `git rev-parse HEAD`, `HEAD`, `development` and `gh workflow run` are all fragments of it, so each is read as that environment's deploy. When the remaining checks pass (clean tree, rollback declared, no unmet `requires`), the hook writes `.crew/.deploy-in-flight` with the environment and the tree's HEAD (`promote-gate.sh:510-511`). `verify-gate.sh:206-211` then refuses every Stop with "DEPLOY NOT RECORDED" for a deploy that never ran.

Observed twice on 2026-10-04 in lane worktrees that routinely run `git rev-parse HEAD`. No deploy run existed for either sha.

**The trigger is an inference, not a reproduction.** The reporter read the code and matched it to the symptom; the reporter did NOT pipe a payload into the hook and watch the marker appear. The spec's first acceptance check is that reproduction, on the unfixed script.

`promote-gate.ps1` has the same two-way test at both of its sites (`:90` committed map, `:134` working map).

The comment at `promote-gate.sh:199-204` records an earlier bug of the same family: a string `deploy` was iterated by character, so `echo done` wrote a marker. That one was fixed; this is its neighbour.

## Severity
It fails closed: nothing is deployed and no check is skipped. The cost is wasted turns, and a habit worse than the bug: sessions learn to delete `.crew/.deploy-in-flight` by hand, which is the one file that makes an unrecorded real deploy visible.

## Recommendation
Drop the `cmd in d` half in both flavours, at all four sites. A command is a declared deploy when it CONTAINS the declared text; a fragment of the declared text is not a deploy. Pin it with must-allow cases that write no marker (`git rev-parse HEAD`, `echo development`, `gh workflow run --help`, `HEAD`, `gh workflow run`) and must-block cases showing the declared command, run verbatim or wrapped, is still gated.

## Options considered
1. (Taken) Drop the reverse test. Smallest change, same rule in both flavours, no tokenizer. Cost: a command that is a shortened form of the declared one (the declared command minus trailing arguments) is no longer matched. The docs say to declare the shortest text every real run contains.
2. Token rule, as the reporter suggested as a fallback: compare normalised tokens and accept a shortened command only when it carries the leading command and the environment argument. Rejected for this ticket: the map has no notion of "the environment argument", PowerShell has no shlex, and two tokenizers that must agree are a larger guard change than the bug. T-0062 and L-0648 already bring a real reader for the workflow-dispatch shape.
3. Keep the match, stop writing the marker for short commands. Rejected: it hides the symptom and keeps the wrong match, which also runs the wrong environment's checks.

## Reporter's suggested fix (recorded as received)
Drop `cmd in d`; if wrapped commands must still match, compare normalised tokens and require the leading command prefix plus the environment argument rather than any substring; regression tests that `git rev-parse HEAD`, `echo development` and `gh workflow run --help` write no marker.

## Approval
Owner go 2026-10-04 for the hand-off; open questions take the recommendation.
