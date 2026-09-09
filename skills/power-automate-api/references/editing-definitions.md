# Editing a flow definition

## Shape of the data

For a solution-aware flow the definition is the `clientdata` column of a
Dataverse `workflow` row. It is a **JSON string containing JSON**:

```jsonc
// clientdata, once parsed
{
  "properties": {
    "connectionReferences": {
      "shared_sharepointonline": {
        "connectionName": "shared-sharepointonl-...",
        "source": "Embedded",
        "id": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
        "tier": "NotSpecified",
        "connectionReferenceLogicalName": "new_sharedsharepointonline_a1b2c",
        "runtimeSource": "invoker"
      }
    },
    "definition": {
      "$schema": "https://schema.management.azure.com/.../workflowdefinition.json#",
      "contentVersion": "1.0.0.0",
      "parameters": {},
      "triggers": {},
      "actions": {}
    }
  },
  "schemaVersion": "1.0.0.0"
}
```

Parse it, edit the object, re-serialise, PATCH the string back. Editing it as
text with a regex is how flows get corrupted — the escaping is nested and a
near-miss still stores successfully.

## Read

```
GET https://<org>.crm.dynamics.com/api/data/v9.2/workflows(<workflowid>)
    ?$select=name,clientdata,statecode,statuscode,ismanaged,category,
             solutionid,workflowidunique,modifiedon
Authorization: Bearer <dataverse token>
Accept: application/json
OData-MaxVersion: 4.0
OData-Version: 4.0
```

Keep the raw response. There is **no version history on `clientdata`** — that
file is the entire rollback story.

Check `ismanaged` in the same read. Patching a managed flow creates an
unmanaged layer that future solution imports will not overwrite.

## Write

```
PATCH https://<org>.crm.dynamics.com/api/data/v9.2/workflows(<workflowid>)
If-Match: *
Content-Type: application/json

{ "clientdata": "<the re-serialised JSON string>" }
```

`204 No Content` is success. `statecode` is untouched by this, so a flow that
was On stays On — the new definition is live the moment the PATCH returns.

`If-Match: *` means "overwrite whatever is there". To make the write fail if
someone else changed the flow since your read, send the `@odata.etag` from the
GET instead. Prefer the etag when the flow has multiple owners.

## Removing a dynamically-added trigger input

The input appears in **two places in the same schema object**, and both must go.

**The user's inputs are usually not at the top level.** A *For a selected file*
trigger nests them under `properties.rows.items`, which has its own `properties`
and its own sibling `required`. The top level holds only `rows`:

```jsonc
"triggers": {
  "manual": {
    "type": "Request",
    "kind": "ApiConnection",
    "splitOn": "@triggerBody()['rows']",
    "inputs": {
      "operationId": "ForASelectedFileHybridTrigger",
      "schema": {
        "type": "object",
        "properties": {
          "rows": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {                       // <-- the real inputs
                "email":   { "title": "First Approver", "type": "string",
                             "format": "email", "x-ms-dynamically-added": true },
                "text":    { "title": "Notes", "type": "string",
                             "x-ms-dynamically-added": true },
                "boolean": { "title": "Include File Set?", "type": "boolean",
                             "x-ms-dynamically-added": true },
                "entity":  { "type": "object", "properties": { "ID": {},
                             "fileName": {}, "itemUrl": {} } }
              },
              "required": ["email", "boolean", "entity"]   // <-- and here
            }
          }
        },
        "required": ["rows"]                        // <-- NOT here
      }
    }
  }
}
```

Delete `email` from the `properties` **and** from the `required` **that sits
beside it** — here, both inside `rows.items`. Checking only the outermost
`properties`/`required` pair finds nothing wrong and tells you the schema is
fine; that pair is consistent whatever the nested one says.

`pa.py validate` walks every nested schema object for this reason. Its message
names the path (`schema.rows[].required`) so you edit the right level.

Leaving it in `required` fails JSON-schema validation at launch. The failure
mode is nasty: the Run flow panel errors, **no run is created**, and run
history therefore shows nothing at all to diagnose from. It looks like the flow
is broken rather than the schema.

`x-ms-dynamically-added: true` is how you identify these unambiguously — it
distinguishes a user-added input from a trigger's built-in fields.

Then find every `triggerBody()?['email']` reference in `definition.actions` and
repoint or remove it.

## Adding an action

Mirror the shape the designer writes, or the flow checker rejects it:

```jsonc
"Get_item": {
  "type": "OpenApiConnection",
  "inputs": {
    "parameters": { "dataset": "https://...", "table": "<list guid>", "id": 1 },
    "host": {
      "apiId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
      "connectionName": "shared_sharepointonline",
      "operationId": "GetItem"
    }
  },
  "runAfter": { "Previous_Action": ["Succeeded"] }
}
```

`host.connectionName` is a **key into `properties.connectionReferences`**, not
a connection id. If the key is absent the flow will not save.

Whatever action previously ran first now needs its `runAfter` repointed at your
new action, or it runs in parallel.

## Connectors and connection references

- **The API cannot mint a connection reference.** Introducing a connector the
  flow has never used requires one designer save: drop the action in anywhere,
  fill the fields with anything valid, Save. That creates the reference; then
  do the real edit through the API.
- **Check first.** Many "new" actions reuse a connector already present — a
  SharePoint *Get item* added to a flow with a SharePoint trigger needs no
  designer save, because `shared_sharepointonline` is already there. Read
  `connectionReferences` before planning around a save you may not need.
- **`runtimeSource`** decides identity. `invoker` runs as whoever launched the
  flow, so every user consents separately and any one of them can break it with
  a password change (`AADSTS50173`). `embedded` runs as the connection's owner
  — right for infrastructure lookups. Changing it means changing
  `connectionReferenceLogicalName` too; changing one alone silently leaves it
  running as the invoker.

## Constraints the service enforces at save

- **`Terminate` cannot be nested inside `Apply to each`** —
  `InvalidWorkflowRunAction`. Set a boolean variable inside the loop and
  terminate after it.
- Action names are keys, so they must be unique, and `runAfter` references them
  by that exact key. Renaming an action means updating every `runAfter` that
  names it.
- Spaces in an action's display name become underscores in the key.

## After the write

1. Reload the designer. It should render your change with no flow-checker
   errors.
2. **Launch it once.** 204 means stored, not runnable. Every failure above
   except the schema one survives a successful PATCH.
3. For a *For a selected file* trigger, *Test → Manually* refuses — it must be
   started from the document library, which makes a pass test a real run. Use a
   disposable document and run the reject path first.
