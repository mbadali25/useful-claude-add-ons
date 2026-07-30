# Inventory and status

## Two different device lists

| Endpoint | Returns |
|---|---|
| `GET /organizations/{organizationId}/inventory/devices` | everything **claimed into the org**, including devices not yet assigned to a network |
| `GET /organizations/{organizationId}/devices` | devices **assigned to networks** |

Use `inventory/devices` to answer "what do we own / what's on the shelf". Use
`devices` to answer "what is deployed". A spare in the closet appears in the first
and not the second — which is the usual reason a serial "doesn't exist".

## Status

```
GET /organizations/{organizationId}/devices/statuses
```

`status` is one of:

- `online`
- `offline`
- `alerting` — reachable but reporting a problem; **not** the same as offline, and
  the one most often missed when someone filters for `offline` alone
- `dormant` — configured but never brought up

```
GET /organizations/{organizationId}/devices/availabilities
```

Availability over time rather than a point-in-time snapshot — use this to tell a
device that is flapping from one that is cleanly down.

## Uplink health

```
GET /organizations/{organizationId}/devices/uplinksLossAndLatency
GET /organizations/{organizationId}/appliance/uplinks/statuses/overview
GET /organizations/{organizationId}/appliance/uplink/statuses
GET /networks/{networkId}/appliance/uplinks/usageHistory
```

`uplinksLossAndLatency` reports per-uplink loss percentage and latency in
milliseconds, sampled over the requested `timespan`. This is the first call for
"the site feels slow" — it distinguishes a saturated or lossy WAN link from an
application problem.

## Licensing: detect the model before you call

An organization uses **one** of two licensing models, and each answers on a
different endpoint. Calling the wrong one returns a `400` whose text reads like a
permissions failure, which sends people down the wrong path.

| Model | Endpoint |
|---|---|
| Co-termination (one shared expiry for the whole org) | `GET /organizations/{organizationId}/licenses/overview` |
| Per-device (each license bound to a serial, own expiry) | `GET /organizations/{organizationId}/licenses` |

How to tell them apart without guessing:

- `GET /organizations` includes a `licensing` object with a `model` field —
  `co-term`, `per-device`, or `subscription`. Read it first; it is authoritative.
- Failing that, call `licenses/overview`. On a co-term org it returns a summary
  with `status` and `expirationDate`. On a per-device org it errors — treat that
  error as the signal to use `licenses` instead, not as a permissions problem.

Do not hardcode one model. Orgs get migrated, and the failure is silent until a
renewal is missed.

## Self-audit

```
GET /organizations/{organizationId}/apiRequests
```

Every API call made against the org, with source IP, path, method, response code,
and timestamp. Useful for two things: proving what this skill did during an
incident review, and finding the other integration that is burning the org's
10 req/sec budget.
