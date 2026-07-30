# Live diagnostic tools

Live tools run **on the device**, not against it from here. They are asynchronous:
create a job, then poll it.

## The create-then-poll pattern

```
POST /devices/{serial}/liveTools/{tool}        -> 201, returns a job id
GET  /devices/{serial}/liveTools/{tool}/{id}   -> poll until terminal
```

The `POST` returns **`201 Created`** (not `200`) with `{<tool>Id, url, request,
status, callback}`. `status` walks `new` → `ready`/`running` → `complete` |
`failed`. `meraki_client.py` treats `complete` and `failed` as terminal and polls
with backoff.

The response also carries a `url` pointing at the poll endpoint — useful if you
ever need to poll by hand.

**Job ids survive a client-side timeout.** If `--timeout` expires, the job is still
running server-side and still pollable at the same id. Don't re-issue the `POST`;
that starts a second job and doubles the load on the device.

### Job-id key names are not uniform

The id field is named after the tool — except `pingDevice`, which returns
**`pingId`**, not `pingDeviceId`:

| Tool | POST returns | Poll path param |
|---|---|---|
| `ping` | `pingId` | `/liveTools/ping/{id}` |
| `pingDevice` | **`pingId`** | `/liveTools/pingDevice/{id}` |
| `cableTest` | `cableTestId` | `/liveTools/cableTest/{id}` |
| `throughputTest` | `throughputTestId` | `/liveTools/throughputTest/{throughputTestId}` |
| `arpTable` | `arpTableId` | `/liveTools/arpTable/{arpTableId}` |
| `macTable` | `macTableId` | `/liveTools/macTable/{macTableId}` |
| `wakeOnLan` | `wakeOnLanId` | `/liveTools/wakeOnLan/{wakeOnLanId}` |

`meraki_client.py` checks a known-key list first and falls back to scanning for a
`*Id` key, with a denylist (`networkId`, `organizationId`, `deviceId`, `clientId`,
`serialId`) so it never mistakes a resource id for a job id.

## Platform support

Checked client-side before the call, so an unsupported combination fails with a
clear refusal instead of a bare `400`. This mirrors `LIVE_TOOLS` in
`meraki_client.py`:

| Tool | Platforms |
|---|---|
| `ping` | MX, MS, MR, MG, Z, C9 |
| `pingDevice` | MX, MS, MR, MG, Z, C9 |
| `cableTest` | MS, C9 |
| `throughputTest` | MX, MR, Z |
| `arpTable` | MX, MS, C9 |
| `macTable` | MS, C9 |
| `wakeOnLan` | MX, MS, C9 |

`ping` pings **from** the device to a target you supply. `pingDevice` pings **the
device itself** from the Meraki cloud. Confusing the two produces a confidently
wrong answer about reachability.

## Payloads

```bash
python scripts/meraki_client.py live ping Q2XX-1111-1111 \
  --json '{"target":"8.8.8.8","count":5}'

python scripts/meraki_client.py live cableTest Q2XX-1111-1111 \
  --json '{"ports":["12"]}'

python scripts/meraki_client.py live throughputTest Q2XX-1111-1111
python scripts/meraki_client.py live arpTable Q2XX-1111-1111
python scripts/meraki_client.py live macTable Q2XX-1111-1111
python scripts/meraki_client.py live wakeOnLan Q2XX-1111-1111 \
  --json '{"vlanId":100,"mac":"00:11:22:33:44:55"}'
```

`cableTest` `ports` are **strings**. It reports per-pair status
(`ok`/`open`/`short`/`crosstalk`) and estimated length — the fastest way to
separate a bad patch cable from a switch port fault.

`wakeOnLan` needs both `vlanId` and `mac`; the MX or switch sends the magic packet
into that VLAN.

## Not wired into this skill

The API also exposes `leds/blink`, `ports/cycle`, `ports/status`, `power/usage`,
`routingTable/lookups`, `routingTable/summaries`, and `multicastRouting` under
`/devices/{serial}/liveTools/`. They follow the identical create-then-poll shape.
They are not in `LIVE_TOOLS` — reach for the raw `get`/`POST` path deliberately
rather than assuming the `live` subcommand covers them.

Note `POST /devices/{serial}/liveTools/ports/cycle` (async, pollable) is a
different endpoint from `POST /devices/{serial}/switch/ports/cycle` (immediate).
Both bounce the port. Both are disruptive — confirm the port list first.

## Licensing and permissions

Live tools require the Dashboard account behind the key to hold write access to the
network; a read-only key gets a `403` on the `POST` even though every read in this
skill works. `throughputTest` additionally depends on the device model and firmware
supporting it.
