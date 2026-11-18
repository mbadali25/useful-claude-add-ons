# Allow `verify_trust.py approve` to be automated through the approval route

Priority: D. Note: D = owner's priority label; mapping to the repo scale unconfirmed.
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's request.
Siblings: `automate-aws-iam-identity-script.md`, `automate-touch-and-tag-deployment.md` (same common requirement).

## Owner's words (verbatim, one request covering all three tickets)

> "create a few new tickets that should be priority D. * Need to run Python to verify trust items should have the ability to be automated, just like running an IAM script. * AWS IAM identity script should be allowed to be automated. * The ability to touch and tag deployment should be allowed to be automated, like having to, if I enable full automation, enable full product edited. These items should be run without me being there. Please add these to the future fixes where you are allowing the agents to run these commands. Now the agents could ask if they could run the commands if you want security, but for approval, that's fine. Don't make me run them. Have the guard set where they can run it based on approvals. Approval is where they actually send me a prompt, and I respond."

## Interpretation (INFERRED, not confirmed by the owner)

"Python to verify trust items" is read as `python3 plugin/crew/hooks/scripts/verify_trust.py approve|revoke|allow-owner|disallow-owner`,
the store writer for the Stop gate's repo trust. Basis: `plugin/crew/CONFIG.md` "Verify gate trust" (VERIFIED, lines 121-139) says it is
run "at a terminal", and `plugin/crew/hooks/scripts/scope_guard.py` (VERIFIED, `_TRUST_RE`, lines ~163-174) refuses a session's command that
names `verify_trust` with a growing or shrinking verb. That is the "have to run it myself" the owner describes. Another reading (a different
script that checks trust) is possible: see owner questions.

## Problem

To let the Stop gate run a repo's `.crew/verify.json` rules, the owner must open a terminal and run `verify_trust.py approve` himself. The
scope guard stops the agent from doing it. The owner wants to answer a prompt instead and have the agent run the command.

## Desired behaviour

When the agent needs a repo trusted, it asks the owner a question (the approval route: the agent sends the prompt, the owner responds). On a
yes, the guard lets the agent run that one `verify_trust.py` command; no terminal step by the owner. Without a yes, it is refused exactly as today.

## Common requirements (same in all three tickets)

1. An unapproved command is still stopped (must-block).
2. An approval binds to the exact command line AND the worktree, and expires. Existing precedent to follow (VERIFIED by reading):
   `cloud_guard.py` `_approval_is_live` with `crew_guards.GUARD_APPROVAL_TTL = 900` and marker `.crew/.approved-guard-*` keyed on the command
   text; `approval_hook.py` records a ticket plan approval from the user's own prompt (`UserPromptSubmit`) so a session cannot forge it, with
   `PENDING_TTL = 600` and a per-worktree pending file. The new route must be produced by something the session cannot write itself (the
   owner's reply), not by a file or command the agent can create.
3. A committed suite with must-block and must-allow cases, sabotage-tested (reintroduce a bug, confirm red), per CLAUDE.md "Adding a hook".
4. The guard change lands alone as a harness PR (CLAUDE.md, T-0087; `HARNESS` in `scripts/check-tooling-pr.py`); the feature wiring is a separate PR.
5. Defaults OFF; turning it on is an owner action in config.

## Acceptance criteria

- `verify_trust.py approve <repo>` run by the agent without a live approval: refused (scope_guard behaviour unchanged).
- With a live approval for the exact command line and worktree: allowed once; a changed argument, another repo, another worktree, or an expired approval: refused.
- `revoke`, `disallow-owner` stay available to the agent without a prompt only if the owner says so (question 3); default is the same route.
- The approval prompt shows the exact command and which repo it would trust.
- Suite with must-block and must-allow cases is committed and shown red after a deliberate regression.
- The trust store location rules in CONFIG.md (no repo-authored path) are unchanged.
- Docs updated in the same PR per CLAUDE.md (crew README, CONFIG.md "Verify gate trust", PLUGINS row, guide sources).

## Owner questions

1. Is "Python to verify trust items" `verify_trust.py`, or another script? Which exact commands?
2. Which verbs: `approve` only, or also `allow-owner` (trust every repo of an owner, a wide grant)?
3. Should `revoke`/`disallow-owner` (narrowing) need the prompt too?
4. Should one approval cover only the current repo, or a stated list?
5. TTL: reuse 15 minutes, or longer for unattended runs?

## Out of scope

Changing which repos are trusted by default; letting a repo file widen trust; any change to the Stop gate's decision; non-trust Python scripts.

## Related files

- `plugin/crew/hooks/scripts/verify_trust.py`, `plugin/crew/CONFIG.md` (VERIFIED)
- `plugin/crew/hooks/scripts/scope_guard.py` (VERIFIED: forgery check on trust verbs)
- `plugin/crew/hooks/scripts/approval_hook.py` (VERIFIED: UserPromptSubmit plan approval, not a command approval; the pattern, not a drop-in)
- `plugin/crew/hooks/scripts/cloud_guard.py`, `crew_guards.py` (VERIFIED: one-shot marker, 900 s TTL, `ask` becomes `deny` when unattended)
- `crew_gitallow.py` / `guards.git.allow` (#769) and `guards.enabled` (#775): INFERRED from the task brief, exist only on their open PR branches, not read here. `guards.mass`: not found in `plugin/crew` CONFIG.md or CHANGELOG.md on origin/main 127df0155, consistent with removal by #772; the 1.3.75 version was not checked.
