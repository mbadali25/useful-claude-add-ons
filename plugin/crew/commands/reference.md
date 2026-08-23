---
description: Generate the API and feature reference from the code, with anchors
argument-hint: [--api | --features | --audit | <area>]
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

Build the reference for: $ARGUMENTS (whole repo if no area given).

A code map answers "where does this live". A reference answers "what can this
system do, and how do I call it". They are different documents and the second
one does not fall out of the first.

Follow the `crew-docs` skill, section on references. Delegate the reading to
`crew:explorer` per area and the writing to `crew:docs-writer`; only summaries
should reach this conversation.

## The rule that makes this worth doing

**Every entry names the file and line it came from.** An endpoint listed with no
anchor cannot be re-verified, so it silently rots and you keep trusting it - the
same failure the codemap's anchors exist to prevent. If you cannot find the
handler, write `undocumented - needs a human`; never infer a shape from a name.

Enumerate from the code, not from existing docs. Existing docs are the thing you
are checking, not the source.

## `--api` (or no argument, if the repo exposes one)

Write `docs/reference/api.md`. Find the routes by whatever the stack actually
uses - do not assume a framework:

| Stack | Where routes are declared |
|---|---|
| .NET | `[Route]`/`[HttpGet]` attributes, `MapGet`/`MapPost`, controllers |
| PHP | router config, `$app->get(...)`, framework route files, front controller |
| Python | `@app.route`, `@router.get`, `urls.py` |
| Node | `app.get(...)`, `router.*`, route directories |
| Terraform/AWS | API Gateway resources, Lambda function URLs, `aws_api_gateway_*` |

One row per endpoint:

```
### POST /api/orders/{id}/ship
`src/Controllers/OrderController.cs:142`

Auth: bearer token, role `fulfilment`  (`Attributes/RequireRole.cs:20`)
Body: `{ carrier: string, tracking: string }`  (`Models/ShipRequest.cs`)
Returns: 200 `{ shipmentId }` | 404 unknown order | 409 already shipped
Side effects: writes `shipments`, emits `order.shipped`, calls ShipStation
Notes: not idempotent - a retry creates a second shipment
```

**Side effects and error responses are the valuable half.** The happy path is
guessable from the name; what it writes, what it calls, and how it fails are
not. Where a generator exists (OpenAPI, `terraform-docs`), generate rather than
transcribe and say which tool produced it.

## `--features`

Write `docs/reference/features.md`. A feature is a thing a user or operator can
do, which is not the same as a module. Group by what someone would come looking
for, and include the things that have no UI:

- Scheduled jobs and cron entries - what they do, when they run, what happens if
  one is missed
- Queue consumers and event handlers - which event, what it does
- CLI commands and admin scripts
- Feature flags and the config keys that switch behaviour
- Integrations, with the direction of the call

```
### Nightly inventory sync
`jobs/InventorySync.cs:30` - cron `0 2 * * *` (`terraform/events.tf:12`)

Pulls the vendor feed, upserts `inventory`, writes a run row to `sync_log`.
A missed run is not retried; the next night's run is a full reconcile.
Fails loudly to the SES error mailbox; silent success is a known gap.
```

## `--audit`

Do not rewrite. Report drift only:

1. Endpoints in the code with no entry in `docs/reference/api.md`.
2. Entries in the reference whose anchor file no longer contains that route -
   check with `git diff --name-only <anchor-sha>..HEAD -- <paths>`.
3. Features documented that no longer exist.
4. Anything marked `undocumented - needs a human` that is still unanswered.

Report the counts and the list. Do not fix silently: a reference quietly
rewritten is indistinguishable from one that was right all along.

## Every file starts with

```
> Generated from <repo>@<short-sha> on <date>. Every entry is anchored to a
> file and line - re-verify the anchor before trusting the entry.
```

## When you finish

Say which areas you enumerated, which you did not, and how many entries are
marked `undocumented`. An incomplete reference that says so is useful; one that
implies full coverage is not.

Then add a rule to `.crew/verify.json` so the reference goes stale loudly:

```json
{ "paths": ["src/**/*Controller*", "**/routes/**", "**/urls.py", "jobs/**"],
  "run": ["true"],
  "why": "endpoint or job changed - run /crew:reference --audit before merging" }
```
