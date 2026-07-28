# Exceptions: allow/block lists

Exceptions are the tenant's allow/block rules. The base surface is a **Whitelist** (allow)
and a **Blacklist** (block); there are also per-engine exception lists (Anti-Phishing, Spam,
Anomaly, Click-Time, Anti-Malware, URL-Reputation, DLP). Most workflows only need the
Whitelist/Blacklist. Use the helper's raw `get` / `post` commands for these.

## Read

```
GET /exceptions/{excType}            # excType = whitelist | blacklist
GET /exceptions/{excType}/{excId}
```

CLI: `python scripts/checkpoint_email_client.py get /exceptions/whitelist`

Each exception record includes matching criteria: `senderEmail`, `senderName`,
`senderDomain`, `senderIp`, `recipient`, `subject`, `linkDomains`, `attachmentMd5`, plus
`*Matching` fields (`is` / `contains` / etc. per criterion), `comment`, `addedBy`,
`updateTime`.

## Create (mutating)

```
POST /exceptions/{excType}
{
  "requestData": {
    "senderEmail": "user@email.com",
    "senderDomain": "email.com",
    "subject": "Allow this email",
    "subjectMatching": "contains",
    "senderEmailMatching": "contains",
    "senderDomainMatching": "contains",
    "comment": "created via API",
    "actionNeeded": "phishing"
  }
}
```

`excType` may be `whitelist`, `blacklist`, or `spam_whitelist`. Supply only the criteria you
want to match on, each paired with its `*Matching` operator.

## Modify / delete (mutating)

```
PUT  /exceptions/{excType}/{excId}          # body same shape as create
POST /exceptions/{excType}/delete/{excId}   # note: delete is a POST, no body
```

## Safety and limits

- These edits change what is allowed or blocked tenant-wide - treat them like any other
  production change: confirm the exact rule (criteria + operators) with the user before
  writing, and prefer the narrowest match that solves the problem.
- **Rate limits**: Anti-Phishing exceptions ~1 request/second; all other exception types
  ~10 requests/second. Batch and sleep accordingly; honor `Retry-After` on 429.
- The per-engine lists (Anti-Phishing, Spam, Anomaly, Click-Time, Anti-Malware,
  URL-Reputation, DLP) follow the same GET/POST/PUT/delete shape under
  `/exceptions/{type}`; consult the vendor API reference for the exact `{type}` slug and any
  per-engine fields if a workflow needs them.
