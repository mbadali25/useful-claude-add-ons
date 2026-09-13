# Change requests — design

**Status: shipped 2026-09-13** — crew 0.19.31 (#145: `/crew:change`, the `change` block, schema 7, the ten-question gate). The decisions below bind.
reproduced verbatim below; decisions after it are the builder's contract.

## The ask (verbatim)

> Another feature to add to the crew is change request, we will file change
> request tickets in either system. The process will be the same via Jira, SDP,
> or local tickets.
>
> SDP we have a Change Management Request template.
>
> We will need to specify the following:
> - Priority
> - Impact
> - Urgency
> - Impact Details
> - Requester name
> - Implementor of Change
> - Scheduled Start Time
> - Scheduled End Time
> - Subject
> - Category
> - Description (below must be answered)
>
> ALL THE BELOW QUESTIONS MUST BE ANSWERED. ANY PERTINENT MISSING INFORMATION
> WILL RESULT IN THE REQUEST BEING DENIED.
>
> 1. What specifically is the change?
> 2. Who will be implementing the change (added to Requestor Details also)?
> 3. What is the scheduled time for the change — list downtime duration and
>    day/time (added to Requestor Details also)?
> 4. Who will this change affect? (how many are affected, what areas, or how
>    many users)
> 5. What is the worst-case scenario of impact to end users?
> 6. What systems/applications are affected? (IP address, URL and/or hostname)
> 7. List the system/applications/services impact, and whether each impacted
>    system/application/service is hosted locally or in the cloud
> 8. What is your rollback plan?
> 9. Has there been a notification sent to those affected?
> 10. Attach results of post-change validation

## Decisions

- **One process, three backends**, selected by crew's existing `tracker`
  (`jira` / `sdp` / `local`). SDP files against the "Change Management Request"
  template through the existing SDP tooling (`infra-work-ticketing` /
  `sdp-sync`); Jira files an issue of the configured change type; `local`
  writes `.work/changes/<id>.md`. The *content* is identical in all three.
- **The ten questions are a gate, not a template.** `/crew:change new` refuses
  to file while any of questions 1–9 is unanswered or answered with a
  placeholder, and says which — mirroring the template's own "will be denied".
  Question 10 (post-change validation) is answered by `/crew:change close`,
  which attaches the validation results and will not close without them.
- **Requester and implementor default from global config** (`change.requester`,
  `change.implementor` — facts about the person and machine); everything else
  is per-request. Both keys also carry answers 2 and 3 into Requestor Details
  as the template requires.
- **Production promotion may require an approved change** —
  `change.requireForProduction` (global, default `false` so the upgrade changes
  nobody's behaviour). When `true`, `/crew:promote production` gate 1 needs a
  change in *approved* state for this sha, read from the backend, never from
  memory; "could not read the state" is a stop, not a pass.
- **Schedule times are the change window**: promote refuses outside
  `scheduledStart`..`scheduledEnd` when the requirement is on.
- Same ratchet family as the other global keys where a value is a permission
  (`requireForProduction`: a repo may turn it on, never off).

## Invariants

- Never file a change with unanswered questions; never close without
  validation results attached.
- The backend's own state is the truth; the local cache is a cache.
- Missing tooling for the chosen backend is a stop that names the install, not
  a silent fall-through to `local`.
