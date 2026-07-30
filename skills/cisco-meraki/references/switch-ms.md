# MS / Catalyst switching

Catalyst models (`C9...`) managed in Dashboard answer on these same switch
endpoints. Where behavior differs, Dashboard exposes an `isCatalyst` marker on the
event log rather than a separate API surface.

## Ports

```
GET /devices/{serial}/switch/ports
GET /devices/{serial}/switch/ports/statuses
GET /devices/{serial}/switch/ports/{portId}
PUT /devices/{serial}/switch/ports/{portId}      <- per-port, safe
```

**There is no collection `PUT` for ports** — every change is per-port. This is the
safest write surface in the whole skill; use it rather than batching ports into
something broader unless you genuinely need atomicity across many ports (in which
case, use an action batch of per-port `PUT`s).

Per-port fields: `name`, `tags`, `enabled`, `poeEnabled`, `type` (`access` |
`trunk`), `vlan`, `voiceVlan`, `allowedVlans`, `isolationEnabled`, `rstpEnabled`,
`stpGuard`, `stpPortFastTrunk`, `linkNegotiation`, `portScheduleId`, `udld`,
`accessPolicyType`.

`ports/statuses` is the diagnostic view: `status`, `speed`, `duplex`, `errors`,
`warnings`, `usageInKb`, `cdp`/`lldp` neighbor data, and `powerUsageInWh`. For
"why is this port flapping", read `errors` and `warnings` here before running a
cable test.

`allowedVlans` on a trunk is a string like `"1,10-20,30"` — not a list. Sending a
list is a `400`.

## Cycling a port — disruptive

```
POST /devices/{serial}/switch/ports/cycle        body: {"ports": ["12"]}
```

This bounces the port: anything attached drops link. **Confirm the exact port list
with the user before sending**, and name what is attached if `ports/statuses`
shows an LLDP/CDP neighbor. Cycling a port that turns out to be an uplink takes
the switch offline.

Port numbers are **strings** in this payload, not integers.

There is also a live-tool form, `POST /devices/{serial}/liveTools/ports/cycle`,
which returns a pollable job — see `live-tools.md`.

## Access control lists — full replacement

```
GET /networks/{networkId}/switch/accessControlLists
PUT /networks/{networkId}/switch/accessControlLists
```

Payload `{"rules": [...]}`, full replacement, order-significant — same hazards as
the MX L3 firewall.

**Field-name trap:** switch ACL rules use **`dstCidr`** and **`dstPort`**, while MX
L3 firewall rules use **`destCidr`** and **`destPort`**. Copying a rule from one to
the other without renaming produces a `400`, or worse, a rule that does not match
what you intended. Full ACL rule fields: `comment`, `policy`, `ipVersion`,
`protocol`, `srcCidr`, `srcPort`, `dstCidr`, `dstPort`, `vlan`.

Meraki appends an implicit trailing `allow any` ACL rule on read, in the same
spirit as the MX default rule. Do not send it back.

## STP, QoS, multicast, DHCP

```
GET/PUT  /networks/{networkId}/switch/stp
GET/POST /networks/{networkId}/switch/qosRules              <- collection: no PUT
GET/PUT  /networks/{networkId}/switch/qosRules/{qosRuleId}  <- edit one rule
GET/PUT  /networks/{networkId}/switch/qosRules/order        <- reorder only
GET/PUT  /networks/{networkId}/switch/routing/multicast
GET/PUT  /networks/{networkId}/switch/dhcpServerPolicy
GET      /networks/{networkId}/switch/dhcp/v4/servers/seen
```

QoS is the one collection Meraki models *well*: there is no collection `PUT`, so
you cannot accidentally wipe the rule set. Create with `POST`, edit one rule by id,
and change precedence through the dedicated `qosRules/order` endpoint rather than
by re-sending the whole list.

`stp` carries `rstpEnabled` and per-switch `stpBridgePriority`. Changing bridge
priority re-converges the spanning tree — treat it as disruptive.

`dhcpServerPolicy` is the rogue-DHCP defense (`alerting` vs `blocking`, plus
allow/block lists). `dhcp/v4/servers/seen` shows what DHCP servers the network has
actually observed, which is how you find the rogue before you block it.

## Stacks and L3 interfaces

```
GET  /networks/{networkId}/switch/stacks
GET  /networks/{networkId}/switch/stacks/{switchStackId}
GET/PUT /devices/{serial}/switch/routing/interfaces/{interfaceId}
GET  /networks/{networkId}/switch/stacks/{switchStackId}/routing/interfaces
GET/PUT /devices/{serial}/switch/routing/staticRoutes/{staticRouteId}
```

On a stack, L3 interfaces belong to the **stack**, not to a member serial. Writing
the device-level interface path on a stacked switch is a common source of "the
change didn't take" — check `switch/stacks` first and use the stack path if the
serial is a member.
