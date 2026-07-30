---
name: cisco-meraki
description: >
  Work with a Cisco Meraki organization through the Dashboard API v1 — inventory
  and device status, network event log, org configuration change log, MX security
  and IDS events, Air Marshal rogue APs, live diagnostics (ping, cable test,
  throughput, ARP/MAC table, wake-on-LAN), and configuration changes to MX
  appliances, MS/Catalyst switches, and MR access points with snapshot/diff/
  confirm and rollback on every write. Use this skill whenever the user mentions
  Meraki, Cisco Meraki, the Meraki Dashboard, an MX/MS/MR device, a Meraki serial
  (Q2xx-xxxx-xxxx), or api.meraki.com — and also when they describe the work
  without naming the product: "which APs are offline", "who changed the firewall
  rules", "why is this switch port flapping", "cycle port 12", "what broke since
  Friday", "add a VLAN", "is that site's VPN up". Also use it when troubleshooting
  a 429 rate limit from api.meraki.com, or a 404 from the Meraki event log that is
  actually a missing productType on a combined network.
---

# Cisco Meraki Dashboard API

Read, diagnose, and safely change a single Meraki organization over Dashboard API
v1 at `https://api.meraki.com/api/v1`. Scope is MX, MS/Catalyst, and MR. Cameras
(MV), sensors (MT), and Systems Manager are out of scope — say so rather than
improvising against those endpoints.

## The one thing to internalize first

Meraki collection endpoints are **full-replacement PUTs**. `PUT` on
`/networks/{id}/appliance/firewall/l3FirewallRules` with three rules does not add
three rules — it deletes every rule not in the payload. Never hand-write a `PUT`.
Always go through `scripts/meraki_config.py`, which snapshots, diffs, and confirms
before it writes.

## Quick start

```bash
export MERAKI_DASHBOARD_API_KEY=...        # never paste the key into chat
python scripts/meraki_client.py orgs       # validates the key, resolves the org
python scripts/meraki_client.py networks   # network map, cached
python scripts/meraki_client.py status     # org-wide online/offline/alerting
```

Those three calls are the bootstrap. Results cache to `.meraki-snapshots/` so
routine work costs four calls total, not four per question.

If `orgs` returns more than one organization, stop and ask the user which one —
this skill is scoped to a single org and will refuse to guess.

## Reading

```bash
python scripts/meraki_client.py inventory
python scripts/meraki_client.py get /networks/N_1/appliance/vlans
python scripts/meraki_client.py get-all /organizations/O_1/devices
python scripts/meraki_client.py events --network N_1 --product-type switch --timespan 3600
python scripts/meraki_client.py changes --timespan 86400
python scripts/meraki_client.py security-events --timespan 86400
python scripts/meraki_client.py air-marshal --network N_1 --timespan 3600
python scripts/meraki_client.py live ping Q2XX-1111-1111 --json '{"target":"8.8.8.8"}'
python scripts/meraki_client.py live cableTest Q2XX-1111-1111 --json '{"ports":["12"]}'
```

`events` needs `--product-type` on a combined network. Omitting it returns a `404`
that reads like the network does not exist; the client catches this and tells you
which product types the network actually has.

## Changing configuration

```bash
python scripts/meraki_config.py snapshot /networks/N_1/appliance/firewall/l3FirewallRules
python scripts/meraki_config.py diff /networks/N_1/appliance/firewall/l3FirewallRules proposed.json
python scripts/meraki_config.py apply /networks/N_1/appliance/firewall/l3FirewallRules proposed.json
python scripts/meraki_config.py rollback .meraki-snapshots/20260729-120000_networks-N-1-....json
```

`apply` cannot write without first snapshotting and rendering a diff — that is its
control flow, not a rule you have to remember. Show the user the rendered diff and
get explicit agreement before confirming.

For anything touching multiple networks or devices, stage a batch so Meraki
validates the whole payload server-side first:

```bash
python scripts/meraki_config.py batch-stage actions.json   # confirmed:false
python scripts/meraki_config.py batch-commit B_1
```

Read the staged batch's error list back to the user as the dry-run result before
committing. Caps: 100 actions per batch, 5 pending batches per org.

## Reference map

| Task | Reference |
|---|---|
| API key setup, org API access, bootstrap, rate limits, redirects | `references/auth-and-bootstrap.md` |
| Inventory, device status, uplink health, licensing models | `references/inventory-and-status.md` |
| MX: VLANs, L3/L7 firewall, static routes, site-to-site VPN, content filtering, traffic shaping | `references/appliance-mx.md` |
| MS: port config/status, ACLs, STP, QoS, stacks, L3 interfaces, port cycling | `references/switch-ms.md` |
| MR: SSIDs, RF profiles, radio settings, client connectivity and latency | `references/wireless-mr.md` |
| Event log, config change log, security events, Air Marshal | `references/logs-and-events.md` |
| Ping, cable test, throughput, ARP/MAC table, wake-on-LAN | `references/live-tools.md` |
| Snapshot/diff/rollback, action batches, hard blocks, the default-rule trap | `references/change-safety.md` |

Read the relevant reference before writing calls — each carries exact paths,
payload shapes, and the per-endpoint quirks.

## Safety rails

- **Never hand-write a config `PUT`.** Use `meraki_config.py`.
- **Show the diff, not a count.** "3 rules will change" is not informed consent;
  the rendered diff is.
- **Refused outright**, regardless of confirmation, because no snapshot can undo
  them: delete network, delete organization, remove/unclaim a device, revoke admin
  access, rotate or delete an API key. These need the Dashboard UI.
- **Never echo the API key.** It comes from `MERAKI_DASHBOARD_API_KEY` only. If the
  user pastes a key into chat, tell them to rotate it.
- **Snapshots contain live secrets** (VPN PSKs, RADIUS secrets). They live in the
  gitignored `.meraki-snapshots/`. Displayed diffs redact secrets; snapshot files
  do not, because rollback needs them intact. Never paste a snapshot file into a
  ticket or commit one.
- **Rate limit is 10 req/sec per org.** The client backs off on `429`
  automatically; don't defeat it with parallel invocations.
