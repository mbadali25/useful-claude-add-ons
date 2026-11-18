# Allow "touch and tag deployment" to be automated, including a full-automation mode

Priority: D. Note: D = owner's priority label; mapping to the repo scale unconfirmed.
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's request.
Siblings: `automate-verify-trust-approval.md`, `automate-aws-iam-identity-script.md`. The baseline acceptance criteria are in the first sibling and apply here.

## Owner's words (verbatim, one request covering all three tickets)

> "create a few new tickets that should be priority D. * Need to run Python to verify trust items should have the ability to be automated, just like running an IAM script. * AWS IAM identity script should be allowed to be automated. * The ability to touch and tag deployment should be allowed to be automated, like having to, if I enable full automation, enable full product edited. These items should be run without me being there. Please add these to the future fixes where you are allowing the agents to run these commands. Now the agents could ask if they could run the commands if you want security, but for approval, that's fine. Don't make me run them. Have the guard set where they can run it based on approvals. Approval is where they actually send me a prompt, and I respond."

## Interpretation (INFERRED, the least certain of the three)

- "touch and tag deployment": creating (touching) a deployment marker and tagging a release/deployment, in the sense of the promote path
  (`.crew/.approved-<env>-<sha>` markers used by `promote-gate.sh`, VERIFIED by comment in `crew_guards.py`) and a git tag. The exact commands are unknown.
- "if I enable full automation, enable full product edited": INFERRED to mean "full production" is meant (speech-to-text), i.e. when the owner
  turns on full automation, the production-edit/deploy path is enabled too and these commands run unattended. Original words kept above. Not confirmed.

## Problem

Touching the deployment marker and tagging a deployment are steps the owner has to run himself. Under a "full automation" setting he expects them
to run without him present, still gated by an approval he answers.

## Desired behaviour

The agent asks; on the owner's yes the guard permits that exact touch/tag command in that worktree for a limited time. A "full automation"
setting makes the agent request that approval itself as part of the flow instead of stopping for the owner to run it. It never removes the approval.

## Acceptance criteria

All baseline criteria from `automate-verify-trust-approval.md` (unapproved is stopped; approval bound to exact command line and worktree; time-limited; sabotage-tested must-block/must-allow suite; guard change lands alone as a harness PR; default OFF; docs in the same PR), plus:

- A tag/touch for environment A or commit X is not allowed by an approval for B or Y (the marker key includes the environment and sha, as `.approved-<env>-<sha>` does).
- "Full automation" on its own does not allow a production tag without an approval; production needs the approval (and any existing `environments.prodUnattended` rule, VERIFIED in `cloud_guard.py`, stays in force).
- A force-moved or deleted tag is refused (`guards.forcePush` unchanged).
- With nobody attending and no approval: `deny`, as `cloud_guard.py` does today when it would `ask`.

## Owner questions

1. What are the exact "touch" and "tag" commands (a file touch, `git tag`, a CI dispatch, `gh release`)?
2. Does "full product edited" mean full production? Is there an existing "full automation" setting, or is it a new one (name, where it lives: repo or machine layer)?
3. Does full automation cover production, or only non-production environments?
4. How does the owner answer the prompt when away (phone, notification)? An unanswered prompt must mean "no".
5. Is `guards.deployWorkflow` (gh workflow run) in scope?

## Out of scope

Running the deployment itself; bypassing `promote-gate`; changing branch protection or admin merge (`guards.adminMerge`).

## Related files

- `plugin/crew/hooks/scripts/cloud_guard.py` (VERIFIED: `guards.deployWorkflow`, `forcePush`, `adminMerge`, environments, one-shot marker)
- `plugin/crew/hooks/scripts/crew_guards.py` (VERIFIED: `.approved-guard-` prefix, 900 s TTL, `.approved-<env>-<sha>` mention)
- `plugin/crew/hooks/scripts/approval_hook.py` (VERIFIED: pattern only, it approves ticket plans)
- `plugin/crew/hooks/scripts/scope_guard.py` (VERIFIED)
- `crew_gitallow.py` (#769 `guards.git.allow`) and `guards.enabled` (#775): INFERRED, open PR branches only, not read. `guards.mass`: absent from CONFIG.md/CHANGELOG.md on origin/main 127df0155, consistent with removal by #772; version 1.3.75 not checked.
