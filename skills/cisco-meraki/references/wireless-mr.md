# MR wireless

## SSIDs

```
GET /networks/{networkId}/wireless/ssids
GET /networks/{networkId}/wireless/ssids/{number}
PUT /networks/{networkId}/wireless/ssids/{number}      <- per-SSID, safe
```

A network always has **15 SSID slots (numbered 0–14)**, whether or not they are in
use. `GET` on the collection returns all fifteen; the unused ones come back named
`Unconfigured SSID N` with `enabled: false`. Do not read that as "the API invented
SSIDs" — and do not try to delete a slot, because there is no delete. Disabling is
the way to remove an SSID.

There is no collection `PUT`. Every change is addressed by slot number, which makes
this a naturally safe surface.

Common `PUT` fields: `name`, `enabled`, `authMode` (`open` | `psk` |
`8021x-radius` | `8021x-meraki` | …), `encryptionMode`, `psk`, `wpaEncryptionMode`,
`dot11w`, `dot11r`, `splashPage`, `ipAssignmentMode`, `vlanId`,
`useVlanTagging`, `radiusServers`, `perClientBandwidthLimitUp/Down`,
`availabilityTags`.

**Secrets live here.** `psk` and any `radiusServers[].secret` are redacted in
displayed diffs and kept intact in snapshot files, because a rollback that restores
an SSID without its PSK would take the network down. See `change-safety.md`.

Changing `authMode`, `psk`, or the VLAN of a live SSID **disconnects every client
on it**. Say so before applying, not after.

## RF profiles and radio settings

```
GET  /networks/{networkId}/wireless/rfProfiles
POST /networks/{networkId}/wireless/rfProfiles
GET/PUT/DELETE /networks/{networkId}/wireless/rfProfiles/{rfProfileId}
GET/PUT /devices/{serial}/wireless/radio/settings
```

Per-device radio settings override the assigned RF profile for that AP —
`channel`, `channelWidth`, `targetPower`, and `rfProfileId`. Setting a manual
channel pins the radio and takes it out of auto-RF; that is occasionally correct
and frequently the cause of "why is this AP on a bad channel six months later".

## Diagnostics

```
GET /networks/{networkId}/wireless/clients/connectionStats
GET /networks/{networkId}/wireless/clients/latencyStats
GET /networks/{networkId}/wireless/latencyStats
GET /networks/{networkId}/wireless/connectionStats
GET /networks/{networkId}/wireless/failedConnections
GET /networks/{networkId}/wireless/channelUtilizationHistory
GET /networks/{networkId}/wireless/signalQualityHistory
GET /networks/{networkId}/wireless/clientCountHistory
```

Triage order for "wifi is bad here":

1. `failedConnections` — returns the failing step (`assoc`, `auth`, `dhcp`, `dns`)
   per client. This usually ends the investigation in one call: DHCP and DNS
   failures are not wireless problems.
2. `connectionStats` — aggregate success/failure counts by stage.
3. `channelUtilizationHistory` — distinguishes RF congestion from everything else.
   High utilization with low client count means interference, not load.
4. `latencyStats` — per-traffic-class latency once you know the association is fine.

`signalQualityHistory` accepts `clientId` or `deviceSerial` and is the right call
for one specific complaining user.

## Air Marshal

`GET /networks/{networkId}/wireless/airMarshal` — see `logs-and-events.md`.
