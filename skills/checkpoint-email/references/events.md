# Security events: search, inspect, triage

A **security event** is a detection about an entity - e.g. a phishing verdict on a specific
email. Each has an `eventId` and points back to its `entityId`. Acting on an event changes
its triage state (dismiss, severity) or triggers a remediation (quarantine, restore) on the
underlying mail.

## Get one event

```
GET /event/{eventId}
```

Returns `eventId`, `entityId`, `saas`, `type`, `state`, `severity`, `confidenceIndicator`,
`description`, `eventCreated`, `availableEventActions` (with per-action parameters), and
`actions` already taken.

CLI: `python scripts/checkpoint_email_client.py event <eventId>`

## Search events

```
POST /event/query
{
  "requestData": {
    "startDate": "2026-07-20T00:00:00.000Z",   // required
    "endDate": "",
    "eventTypes": ["phishing", "malware"],
    "severities": ["High", "Highest"],
    "eventStates": [],
    "saas": ["office365_emails"],
    "confidenceIndicator": "",
    "description": "",
    "scrollId": ""
  }
}
```

Only `startDate` is strictly required; the rest narrow the result. Array fields are ORed
within a field and ANDed across fields.

- **type** (examples): `phishing`, `malware`, `dlp`, `spam`, `anomaly`, `shadow_it`. (Types reflect the engines enabled on the tenant.)
- **severity**: `Low`, `Medium`, `High`, `Highest`.
- **confidenceIndicator**: e.g. `malicious`, `suspicious`.

**Pagination**: same `scrollId` scheme as entities - resend with the returned `scrollId`
until empty.

CLI (auto-paginates):
```
python scripts/checkpoint_email_client.py search-events \
    --start 2026-07-20T00:00:00.000Z --type phishing malware --severity High Highest --max 200
```

## Take action on events (mutating - dry-run gated)

```
POST /action/event
{
  "requestData": {
    "eventIds": ["<ev1>"],
    "eventActionName": ["dismiss"],
    "eventActionParam": [""]
  }
}
```

Returns a `taskId` (poll `GET /task/{taskId}`). Read each event's `availableEventActions`
for what is valid and what parameter it needs.

| Action | Param | Effect |
|---|---|---|
| `dismiss` | - | Close/triage the event without remediation |
| `severityChange` | `Low` / `Medium` / `High` / `Highest` | Re-rate the event |
| `quarantine` | - | Remediate the underlying mail |
| `restore` | - | Un-remediate the underlying mail |
| `sendToAdmin` | admin email | Route the event to an admin |

CLI (dry-run by default):
```
python scripts/checkpoint_email_client.py action-event --action dismiss --ids EV1 EV2
python scripts/checkpoint_email_client.py action-event --action severityChange --param High --ids EV1 --confirm
```

## Task status

```
GET /task/{taskId}
```

Returns the queued task with `status` and a per-action breakdown. `completed` means the
action finished; `failed` / `stopped` need investigation. CLI:
`python scripts/checkpoint_email_client.py task <taskId>`
