# Allow `aws sns subscribe` for alert recipients to be run through the approval route

Priority: D.
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 from the owner's request.
Siblings: `automate-verify-trust-approval.md`, `automate-aws-iam-identity-script.md`, `automate-touch-and-tag-deployment.md`. The common requirements and acceptance baseline are in the first sibling; they apply here unchanged.

## Source and owner's words (verbatim)

Source (VERIFIED from the owner's paste, as relayed to this ticket): the `thd-pro` session's report. That session declined to run the command and handed the item to the owner. The report line, as quoted:

> "One item is yours: the script says alert recipients must be subscribed by you. I won't subscribe anyone. The command is aws sns subscribe --topic-arn arn:aws:sns:us-east-1:718678532558:thd-refresh-alerts --protocol email --notification-endpoint <address>."

The owner's words:

> "also after all the changes you also stop doing this as well"

> "you should be able to run these"

Context: said right after the owner listed the priority-D automation tickets (the three siblings).

## Interpretation (INFERRED)

The owner wants agents and sessions such as `thd-pro` to stop handing commands like this back to him ("One item is yours") and instead run them through the same approval route as the sibling tickets: the agent sends him a prompt naming the exact command, he answers in his own message, and the agent (or a guarded runner) executes it. He does not run it himself. "These" is read as `aws sns subscribe` for alert recipients, and by extension similar hand-back items; that wider reading is not confirmed.

## Problem

Agents decline to run `aws sns subscribe` for alert recipients and hand it back to the owner, who then has to run it by hand. VERIFIED: the only facts known are the quoted report line and the command line in it. NOT known: which script said "alert recipients must be subscribed by you", which AWS profile it ran under, why the session declined (agent's own caution versus a guard block), or whether any hook actually blocks this command today (INFERRED: `cloud_guard.py` classifies `aws` commands and judges destructive verbs, so a subscribe may not be blocked by a guard at all; not tested, and no aws command was run for this ticket).

## Desired behaviour

The agent asks; the owner's reply approves that exact command. It then runs, once, for that worktree, for a limited time. No reply, no run. The approval shows the full command, including the topic ARN and the exact recipient address, before the owner answers.

Design reference (not a decision): Option A in the scratchpad design `approval-route-design.md` (agent request, owner types `/crew:allow-run <id>` in his own prompt, one-shot receipt bound to command hash and worktree). That file is in a session scratchpad, not in the repo, and may be gone.

## Acceptance criteria

All baseline criteria from `automate-verify-trust-approval.md` (unapproved is stopped; approval bound to exact command line and worktree; time-limited; must-block/must-allow suite sabotage-tested; guard change lands alone as a harness PR; default OFF; docs in the same PR), plus:

- An unapproved `aws sns subscribe` is still stopped (or, if no guard stops it today, the agent still must not run it without a prompt answered by the owner).
- Approval binds to the exact command line: topic ARN, protocol and notification endpoint. A different address, a different topic, a different protocol or region than the approved one is stopped.
- One approval covers one run. It does not cover a second recipient, and a replay of the same command after it ran is stopped.
- The must-block/must-allow suite includes at least: same command approved (allow), other address (block), other topic (block), replay (block), expired approval (block), `unsubscribe` / `delete-topic` with an `sns subscribe` approval (block). It is sabotage-tested: reintroduce the bug (match on topic only, or leave the receipt unspent) and confirm the suite goes red.
- The guard change lands alone as a harness PR, no feature work in it.
- Audit trail: each approval and each run records who approved (the owner's prompt), the exact command, the worktree, and the time. The recipient address is shown in the approval prompt and in the log.

## Owner questions

1. Which topics beyond `thd-refresh-alerts` (and which account and profile; the ARN above names account `718678532558`, region `us-east-1`)? Is production in scope?
2. Which script said recipients must be subscribed by the owner, so it can be pointed at the approval route?
3. Does the subscription need the recipient's confirmation click, so that the command only creates a pending subscription? (INFERRED from how SNS email subscriptions generally work; not verified for this topic.)
4. Does he want a bounded allowlist of topic ARNs plus one prompt per new recipient address, rather than a prompt per command shape?
5. Must `aws sns unsubscribe` and `delete-topic` stay human-only?
6. Is "these" only `aws sns subscribe`, or every command an agent currently hands back with "One item is yours"?

## Security note

Subscribing an external email address makes AWS send that third party a confirmation message. It is an outward-facing action, not only an internal config change. Approvals must therefore show the exact address, and a blanket or standing approval for "any address" is not acceptable.

## Out of scope

Changing AWS IAM policy; creating topics; any real subscription (no `aws` command is run as part of this ticket); editing the alert script; `unsubscribe` and topic deletion unless the owner answers question 5 otherwise.

## Related files

- `plugin/crew/hooks/scripts/cloud_guard.py` (VERIFIED by the sibling tickets: `ask`, the one-shot `.approved-guard-*` marker, unattended `ask` becomes `deny`, `aws` profile/region pins; whether it treats `sns subscribe` specially: not read for this ticket)
- `plugin/crew/hooks/scripts/scope_guard.py` (VERIFIED by the sibling tickets; not re-read)
- `plugin/crew/hooks/scripts/approval_hook.py` (VERIFIED by the sibling tickets: owner-prompt channel via `UserPromptSubmit`; pattern only)
- `automate-verify-trust-approval.md`, `automate-aws-iam-identity-script.md`, `automate-touch-and-tag-deployment.md` (same directory)
