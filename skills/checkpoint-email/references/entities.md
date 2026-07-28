# Email entities: search, inspect, remediate

An **entity** is a protected object - for email, a single message. Each has a stable Check
Point `entityId`. Entities carry an `entityPayload` (the mail metadata), an
`entitySecurityResults` block (per-engine verdicts), and an `entityAvailableActions` list.

Supported email SaaS values: `office365_emails` (entity type `office365_emails_email`) and
`google_mail` (`google_mail_email`).

## Get one entity

```
GET /search/entity/{entityId}
```

Returns the full entity: `entityInfo` (ids, saas, `entityActionState`), `entityPayload`
(see fields below), `entitySecurityResults.combinedVerdict` (`ap`, `dlp`,
`clicktimeProtection`, `shadowIt`, `av`), `entityActions` (actions already taken), and
`entityAvailableActions` (what you can do now).

CLI: `python scripts/checkpoint_email_client.py entity <entityId>`

## Search entities

```
POST /search/query
{
  "requestData": {
    "entityFilter": {
      "saas": "office365_emails",
      "saasEntity": "office365_emails_email",
      "startDate": "2026-07-01T00:00:00.000Z",   // required
      "endDate": ""                                // optional (empty = up to now)
    },
    "entityExtendedFilter": [
      {"saasAttrName": "entityPayload.fromEmail", "saasAttrOp": "is", "saasAttrValue": "x@y.com"},
      {"saasAttrName": "entityPayload.attachmentCount", "saasAttrOp": "greaterThan", "saasAttrValue": "0"}
    ],
    "scrollId": ""
  }
}
```

`saas` and `startDate` are required. Every extended-filter clause is ANDed.

**Operators** (`saasAttrOp`): `is`, `isNot`, `contains`, `notContains`, `startsWith`,
`isEmpty`, `isNotEmpty`, `greaterThan`, `lessThan`.

**Common `saasAttrName` fields** (prefix `entityPayload.`): `fromEmail`, `fromDomain`,
`fromName`, `to`, `cc`, `subject`, `received`, `size`, `attachmentCount`,
`internetMessageId`, `isQuarantined`, `isRestored`, `SpfResult`, `saasSpamVerdict`.

**Pagination**: if `responseEnvelope.scrollId` is non-empty, resend the identical query with
that value in `requestData.scrollId` until it returns empty.

CLI (auto-paginates):
```
python scripts/checkpoint_email_client.py search-entities \
    --start 2026-07-01T00:00:00.000Z \
    --filter entityPayload.subject contains "invoice" \
    --filter entityPayload.fromDomain isNot ourcompany.com \
    --max 200
```

### Key entityPayload fields

`internetMessageId`, `subject`, `received`, `size`, `emailLinks`, `attachmentCount`,
`attachments`, `recipients`, `fromEmail`, `fromDomain`, `fromName`, `to`, `cc`, `bcc`,
`replyToEmail`, `isRead`, `isDeleted`, `isIncoming`, `isInternal`, `isOutgoing`,
`isQuarantined`, `isQuarantineNotification`, `isRestored`, `isRestoreRequested`,
`isRestoreDeclined`, `saasSpamVerdict`, `SpfResult`.

## Take action on entities (mutating - dry-run gated)

```
POST /action/entity
{
  "requestData": {
    "entityIds": ["<id1>", "<id2>"],
    "entityActionName": ["quarantine"],   // one action, applied to all ids
    "entityActionParam": [""]
  }
}
```

Returns a `taskId` per entity. The action is **queued** - poll `GET /task/{taskId}` for
status (`init` / `inprogress` / `completed` / `failed` / `stopped` / `paused`).

Actions available depend on the entity's current state and appear in its
`entityAvailableActions`. Common email actions: **quarantine**, **restore**. Always read the
entity's available actions rather than assuming - a mail already quarantined will not offer
`quarantine` again.

CLI (dry-run by default; resolves and prints each target before doing anything):
```
python scripts/checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2
python scripts/checkpoint_email_client.py action-entity --action quarantine --ids ID1 ID2 --confirm
```

`restore` returns a quarantined message to the user's mailbox - only do this on explicit
instruction naming the message.
