# Logs and events

Four distinct log surfaces. Picking the wrong one is the most common reason a
question goes unanswered.

| Question | Surface |
|---|---|
| what happened on this network | `GET /networks/{networkId}/events` |
| **who changed what** | `GET /organizations/{organizationId}/configurationChanges` |
| what did the MX block | `.../appliance/security/events` |
| what rogue APs are nearby | `GET /networks/{networkId}/wireless/airMarshal` |

## Network event log

```
GET /networks/{networkId}/events
```

**`productType` is required on a combined network.** A combined network (one that
holds more than one of appliance/switch/wireless) rejects the call without it —
and the rejection is a **`404`**, which reads as "this network does not exist".
This is the single most confusing error in the API. `meraki_client.py` catches it
and reports which product types the network actually has.

Response: `{"pageStartAt", "pageEndAt", "events", "message"}` — note the events
are under `events`, not at the top level.

Pagination is **cursor-based, not page-numbered**: use `startingAfter` /
`endingBefore` with `perPage`, and follow the `Link` header's `rel=next`. There is
no `page` parameter; constructing one silently returns the first page forever.

Useful filters: `includedEventTypes`, `excludedEventTypes`, `deviceSerial`,
`deviceName`, `clientMac`, `clientIp`, `eventSeverity`, `isCatalyst`.

## Configuration change log — the audit trail

```
GET /organizations/{organizationId}/configurationChanges
```

This is the answer to *"what broke since Friday"* and *"who changed the firewall
rules"*. Fields: `ts`, `adminName`, `adminEmail`, `adminId`, `networkName`,
`networkId`, `ssidName`, `page`, `label`, `oldValue`, `newValue`.

`oldValue`/`newValue` give the before/after directly, so this often resolves an
incident without touching device state at all.

**Retention is up to 365 days here**, versus 31 days on most other timespan
endpoints. `meraki_client.max_timespan_for()` encodes exactly this: 31536000s for
`/configurationChanges`, 2678400s elsewhere. Exceeding a ceiling returns an opaque
`400`, so the client validates locally and quotes the real limit instead.

For a longer window than one request allows, page with `t0`/`t1` rather than
raising `timespan`.

## Security / IDS events

```
GET /organizations/{organizationId}/appliance/security/events
GET /networks/{networkId}/appliance/security/events
```

MX IDS/IPS and AMP detections: `ts`, `eventType`, `clientName`, `clientMac`,
`srcIp`, `destIp`, `protocol`, `priority`, `action` (`blocked` | `allowed`),
`signature`, `ruleId`, plus file/AMP fields (`fileHash`, `fileType`,
`dispositionScore`) where relevant.

`action: "allowed"` on a high-priority signature means IDS is in **detection**
mode, not prevention — worth flagging explicitly, because the events look alarming
and nothing was actually stopped.

Requires an Advanced Security license.

## Air Marshal

```
GET /networks/{networkId}/wireless/airMarshal
```

Rogue and neighboring SSIDs seen by the APs: `ssid`, `bssids`, `channels`,
`firstSeen`, `lastSeen`, `wiredMacs`, `wiredVlans`, `rssi`.

`wiredMacs` being populated is the important signal — it means the rogue SSID was
seen bridging onto **your wired network**, which escalates it from "a neighbor's
wifi" to a genuine security finding.

## API self-audit

```
GET /organizations/{organizationId}/apiRequests
GET /organizations/{organizationId}/apiRequests/overview
```

Who called what, when, from where, and with what response code. Use it to prove
what this skill did during a change review, or to find the integration eating the
org's 10 req/sec budget.
