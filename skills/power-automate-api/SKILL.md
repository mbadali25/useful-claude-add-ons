---
name: power-automate-api
description: Use when reading, editing, creating or diagnosing Microsoft Power Automate cloud flows through an API instead of the maker portal - including a flow definition that must be changed reliably, an expression the designer refuses or mangles, a trigger input to add or remove, connection references running as the wrong identity, run history to inspect, or a 401 InvalidAuthenticationAudience / AADSTS7000218 from api.flow.microsoft.com, api.bap.microsoft.com, api.powerplatform.com or a Dataverse org endpoint.
---

# Power Automate via API

Editing a flow through its API is faster and far more reliable than the
designer, whose expression editor silently discards hand-typed references. But
the definition is a JSON string inside a JSON column with no version history,
so a bad write is unrecoverable without a snapshot.

**Core principle: snapshot before every write, and validate before every PATCH.**
`scripts/pa.py` enforces both in code. Prefer it over hand-rolled HTTP.

## Which API

| Flow kind | Source of truth | Write here |
|---|---|---|
| **Solution-aware** (in a solution; has a Dataverse `workflow` row) | Dataverse `workflows(<id>).clientdata` | Dataverse Web API |
| **Non-solution** ("My flows") | `api.flow.microsoft.com` | Flow management API |

A solution-aware flow read through `api.flow.microsoft.com` looks editable and
is not: writes there are second-class and a solution sync can revert them.
`workflowid` is the GUID in the maker URL.

## Audience is the #1 failure

Every endpoint wants a different token. A wrong audience returns 401 with an
unhelpful body, or `InvalidAuthenticationAudience` naming the allowed list.
**Read `references/auth.md` before requesting a token** — do not guess these
from memory. Three independent agents asked to produce this table produced
three different tables, and none matched.

## The edit workflow

1. **`pa.py get`** — writes a timestamped snapshot. This is the only rollback.
2. **Parse `clientdata`.** It is a JSON *string* containing
   `{properties: {connectionReferences, definition}, schemaVersion}`. Parse it,
   edit the object, re-serialise. **Never regex it.**
3. **Edit the object.** Mirror the host shape the designer writes
   (`{apiId, operationId, connectionName}`), and repoint `runAfter` on whatever
   followed what you removed.
4. **`pa.py patch`** — re-validates, re-snapshots, then PATCHes. 204 = written.
5. **Reload the designer** and confirm the flow checker is clean.
6. **Launch it once.** A definition that saves is not a definition that runs.

Details and worked examples: `references/editing-definitions.md`.

## Traps

- **Removing a dynamically-added trigger input means two places** —
  `properties` *and* the same schema's `required` array. Leaving it in
  `required` blocks every launch, creates **no run**, and therefore leaves
  nothing in run history to diagnose from. `pa.py` refuses a PATCH that
  orphans a `required` entry.
- **`Terminate` cannot be nested inside `Apply to each`** — the service
  rejects the save with `InvalidWorkflowRunAction`. Set a variable in the loop,
  terminate after it. `pa.py` checks this too.
- **A new *connector* needs one designer save first.** The API cannot mint a
  connection reference. But check `properties.connectionReferences` before
  assuming: an action often reuses a connector the flow already has, and then
  no designer save is needed at all.
- **`runtimeSource: invoker` runs as whoever launched the flow.** For
  infrastructure lookups set `embedded` against a service account — and
  repoint `connectionReferenceLogicalName` too. Changing one of the two leaves
  it running as the invoker.
- **Check `ismanaged` before patching.** Patching a managed flow creates an
  unmanaged layer: future solution imports stop reaching it. Decide that
  deliberately; the change usually belongs in the unmanaged source solution.
- **Never run an interactive login from a tool call.** Device-code and
  `Connect-MgGraph` block on a prompt the harness cannot see, burn the
  timeout, and drop cached scopes when cancelled. Have the user run it.

## Red flags — stop

- About to PATCH without a snapshot file on disk
- About to edit `clientdata` as text rather than as a parsed object
- Reciting an audience or public-client GUID from memory
- "It saved with 204, so it works" — 204 means stored, not runnable
- Removed a trigger property and did not touch `required`

## Quick reference

```bash
python pa.py login  --org https://<org>.crm.dynamics.com
python pa.py get    --org https://<org>.crm.dynamics.com --flow <guid>
python pa.py validate --clientdata flow.json          # offline, no token
python pa.py patch  --org https://<org>.crm.dynamics.com --flow <guid> \
                    --clientdata flow.json
python pa.py runs   --env <env-guid> --flow <guid>
```

Run `python pa.py --help` for the rest.
