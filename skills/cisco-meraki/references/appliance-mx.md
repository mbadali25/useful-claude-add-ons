# MX security appliance

All writes go through `meraki_config.py`. The paths below are documented so you
can read state and build a proposed payload — not so you can hand-write a `PUT`.

## VLANs

```
GET /networks/{networkId}/appliance/vlans
GET /networks/{networkId}/appliance/vlans/{vlanId}
PUT /networks/{networkId}/appliance/vlans/{vlanId}      <- prefer this
POST /networks/{networkId}/appliance/vlans              <- create
```

**Prefer the per-VLAN `PUT`.** It changes one VLAN. There is no collection-level
`PUT` for VLANs, which is a mercy — but the same instinct applies everywhere else
in this file: the narrowest endpoint that does the job is the safe one.

Per-VLAN `PUT` fields: `name`, `subnet`, `applianceIp`, `groupPolicyId`,
`vpnNatSubnet`, `dhcpHandling`, `dhcpRelayServerIps`, `dhcpLeaseTime`,
`dhcpBootOptionsEnabled`, `dhcpBootNextServer`, `dhcpBootFilename`,
`fixedIpAssignments`, `reservedIpRanges`, `dnsNameservers`.

VLANs must be enabled on the network first
(`GET/PUT /networks/{networkId}/appliance/vlans/settings` — note the slash, it is
not `vlansSettings`); on a single-LAN network the VLAN endpoints return `400`.

## L3 firewall — the full-replacement endpoint

```
GET /networks/{networkId}/appliance/firewall/l3FirewallRules
PUT /networks/{networkId}/appliance/firewall/l3FirewallRules
```

Payload: `{"rules": [ ... ]}`

Rule fields: `comment`, `policy` (`allow`|`deny`), `protocol`
(`tcp`|`udp`|`icmp`|`any`), `srcCidr`, `srcPort`, `destCidr`, `destPort`,
`syslogEnabled`.

Two traps live here, both handled by the tooling:

1. **Full replacement.** The `PUT` body *is* the new rule list. Sending one rule
   deletes the rest. Always snapshot → diff → confirm.
2. **The implicit default rule.** `GET` returns a trailing "Default rule"
   allow-any entry. `PUT` **rejects** it. `meraki_diff.strip_default_rule()`
   removes it on read and the writer simply omits it. Do not pass it through to
   "preserve" it — the write will fail. See `change-safety.md`.

Rule **order is semantics** — Meraki evaluates top-down, first match wins. Moving
a `deny` above a `permit` changes behavior with identical set membership, which is
why the diff is positional rather than set-based.

## L7 firewall

```
GET /networks/{networkId}/appliance/firewall/l7FirewallRules
PUT /networks/{networkId}/appliance/firewall/l7FirewallRules
```

Also full-replacement. Rules are `{"policy": "deny", "type": ..., "value": ...}`
where `type` is one of `application`, `applicationCategory`, `host`, `port`,
`ipRange`. L7 is deny-only — there is no allow action.

## Other firewall surfaces

```
GET/PUT /networks/{networkId}/appliance/firewall/inboundFirewallRules
GET/PUT /networks/{networkId}/appliance/firewall/cellularFirewallRules
GET/PUT /networks/{networkId}/appliance/firewall/oneToOneNatRules
GET/PUT /networks/{networkId}/appliance/firewall/portForwardingRules
```

All full-replacement collections. Same rules apply.

## Static routes

```
GET  /networks/{networkId}/appliance/staticRoutes
POST /networks/{networkId}/appliance/staticRoutes
GET/PUT/DELETE /networks/{networkId}/appliance/staticRoutes/{staticRouteId}
```

Per-route endpoints — no collection `PUT`. Use them.

## Site-to-site VPN — contains secrets

```
GET /networks/{networkId}/appliance/vpn/siteToSiteVpn
PUT /networks/{networkId}/appliance/vpn/siteToSiteVpn
```

`mode` is `none` | `spoke` | `hub`. Spokes carry a `hubs` list with
`useDefaultRoute`; `subnets` carries `localSubnet` / `useVpn` pairs.

**Third-party peers carry pre-shared keys** on
`GET/PUT /organizations/{organizationId}/appliance/vpn/thirdPartyVPNPeers`. The
`psk` field is redacted in displayed diffs and left intact in snapshot files
(rollback needs it). Never paste a snapshot into a ticket.

Related read-only surfaces:

```
GET /organizations/{organizationId}/appliance/vpn/statuses
GET /organizations/{organizationId}/appliance/vpn/stats
```

Use `statuses` for "is that site's VPN up".

## Content filtering and traffic shaping

```
GET/PUT /networks/{networkId}/appliance/contentFiltering
GET     /networks/{networkId}/appliance/contentFiltering/categories
GET/PUT /networks/{networkId}/appliance/trafficShaping
GET/PUT /networks/{networkId}/appliance/trafficShaping/rules
GET/PUT /networks/{networkId}/appliance/trafficShaping/uplinkBandwidth
GET/PUT /networks/{networkId}/appliance/trafficShaping/uplinkSelection
```

`contentFiltering` takes **category IDs**, not names — fetch `categories` first and
map. Blocked-URL patterns are full-replacement lists.

## Uplink settings are per-device

```
GET/PUT /devices/{serial}/appliance/uplinks/settings
```

There is **no** `/networks/{networkId}/appliance/uplinks/settings`. Per-uplink WAN
configuration (static IP, VLAN tagging, PPPoE) is addressed by device serial. The
network-level uplink paths that do exist are
`/networks/{networkId}/appliance/uplinks/nat` (PUT) and
`.../uplinks/usageHistory` (GET), which are different things.
