# Allow the AWS IAM identity script to be automated through the approval route

Priority: D. Note: D = owner's priority label; mapping to the repo scale unconfirmed.
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's request.
Siblings: `automate-verify-trust-approval.md`, `automate-touch-and-tag-deployment.md`. The common requirements and acceptance baseline are in the first sibling; they apply here unchanged.

## Owner's words (verbatim, one request covering all three tickets)

> "create a few new tickets that should be priority D. * Need to run Python to verify trust items should have the ability to be automated, just like running an IAM script. * AWS IAM identity script should be allowed to be automated. * The ability to touch and tag deployment should be allowed to be automated, like having to, if I enable full automation, enable full product edited. These items should be run without me being there. Please add these to the future fixes where you are allowing the agents to run these commands. Now the agents could ask if they could run the commands if you want security, but for approval, that's fine. Don't make me run them. Have the guard set where they can run it based on approvals. Approval is where they actually send me a prompt, and I respond."

## Interpretation (INFERRED)

"AWS IAM identity script" is read as a script that reports which AWS identity (caller, profile, account) a command would act as, i.e. the
identity check the cloud guard and QA tooling rely on (e.g. an `aws sts get-caller-identity` wrapper or the deployed-identity helper). The repo
script was NOT identified: crew docs mention "deployed-identity helpers" (`pending-tickets.md` row 5) and `cloud.*` AWS profile pins in
`cloud_guard.py` (VERIFIED: it pins the AWS profile/region an `aws` command will act as), but which file the owner means is a question.

## Problem

The owner has to run the IAM identity script himself. He wants the agent to run it after he answers a prompt.

## Desired behaviour

The agent asks; on the owner's yes, the guard lets that exact script invocation run for that worktree, for a limited time. No yes, no run.

## Acceptance criteria

All baseline criteria from `automate-verify-trust-approval.md` (unapproved is stopped; approval bound to exact command line and worktree; time-limited; must-block/must-allow suite sabotage-tested; guard change lands alone as a harness PR; default OFF; docs in the same PR), plus:

- The approved invocation is read-only against AWS (identity lookup only); a variant that mutates IAM (create/attach/put policy, access keys) is refused even with an approval for the identity call.
- The pinned `cloud.*` profile/region still applies; an approval for profile A does not cover profile B.
- Credentials and the printed account id are not written to guard.log beyond what the log already records.

## Owner questions

1. Which script or command is "the AWS IAM identity script" (path, arguments)?
2. Which profile(s) and accounts, including production?
3. Is read-only identity lookup the whole scope, or must it also run IAM changes (that would be a much larger ticket)?
4. Should a standing approval for a time window be allowed, given nobody is present?

## Out of scope

Any IAM mutation; changing `cloud.*` pins; `guards.cloudDestructive` behaviour for `aws delete-*`; editing the script itself.

## Related files

- `plugin/crew/hooks/scripts/cloud_guard.py` (VERIFIED: `ask` and the one-shot `.approved-guard-*` marker; unattended `ask` becomes `deny`; `unattended()` treats `CI`/`bypassPermissions`/`dontAsk` as unattended)
- `plugin/crew/hooks/scripts/crew_guards.py` (VERIFIED: `GUARD_APPROVAL_TTL = 900`)
- `plugin/crew/hooks/scripts/approval_hook.py` (VERIFIED: plan approval via `UserPromptSubmit`; pattern only)
- `plugin/crew/hooks/scripts/scope_guard.py` (VERIFIED)
- `crew_gitallow.py` (#769) and `guards.enabled` (#775): INFERRED, only on open PR branches, not read.
