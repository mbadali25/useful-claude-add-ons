# Change safety

Everything in this file exists because a Meraki config write can destroy state that
no amount of care afterwards can reconstruct.

## Full-replacement PUT semantics

Collection endpoints replace the entire collection. The body **is** the new state.

A worked example of the accident. Current rules:

```json
{"rules": [
  {"comment": "Allow DNS",      "policy": "allow", "protocol": "udp", "destPort": "53",  "destCidr": "any", "srcCidr": "any", "srcPort": "any"},
  {"comment": "Allow HTTPS",    "policy": "allow", "protocol": "tcp", "destPort": "443", "destCidr": "any", "srcCidr": "any", "srcPort": "any"},
  {"comment": "Deny guest→LAN", "policy": "deny",  "protocol": "any", "destPort": "any", "destCidr": "10.0.0.0/8", "srcCidr": "192.168.99.0/24", "srcPort": "any"}
]}
```

Someone wants to add an NTP allow and sends:

```json
{"rules": [
  {"comment": "Allow NTP", "policy": "allow", "protocol": "udp", "destPort": "123", "destCidr": "any", "srcCidr": "any", "srcPort": "any"}
]}
```

The result is **one rule**. DNS, HTTPS, and the guest isolation rule are gone. The
API returns `200`. Nothing warns you. The guest network can now reach the LAN.

This is why `meraki_config.py apply` cannot write without first snapshotting and
rendering a diff — it is the control flow, not a convention.

## The implicit default rule

`GET` on `/networks/{networkId}/appliance/firewall/l3FirewallRules` returns a
trailing entry:

```json
{"comment": "Default rule", "policy": "allow", "protocol": "any",
 "srcCidr": "any", "srcPort": "any", "destCidr": "any", "destPort": "any"}
```

`PUT` **rejects** that entry. Left unhandled it breaks a snapshot→restore round
trip outright, and makes every diff show a phantom removal of the last rule.

`meraki_diff.strip_default_rule()` drops it on read. The writer re-derives it by
simply not sending it — Meraki re-appends it server-side.

**Do not "fix" this by passing the default rule through.** The write will fail, and
the obvious-looking fix (deleting the strip) reintroduces the phantom diff.

## Why the diff is positional

Meraki evaluates rules top-down, first match wins. So position is semantics:

```
1. allow  tcp 22  from 10.1.0.0/16      1. deny   tcp 22  from any
2. deny   tcp 22  from any         →    2. allow  tcp 22  from 10.1.0.0/16
```

Identical set membership. Completely different behavior — after the swap, nobody
reaches SSH. A set-based diff reports **"no change"** on that edit.

`meraki_diff.diff_rules()` is therefore positional, built on
`difflib.SequenceMatcher`, and classifies each rule as added / removed / moved /
unchanged. Reordering is a first-class change, not a no-op.

A documented limitation: when a rule is edited *and* moved in the same change, the
diff may render it as a remove plus an add rather than a single move. The rendered
result is still correct and complete — it just reads as two operations. There is a
regression test pinning this behavior so it cannot silently get worse.

## Snapshots

Written to `.meraki-snapshots/` as:

```json
{"path": "/networks/N_1/appliance/firewall/l3FirewallRules",
 "captured": "2026-07-29T12:00:00Z",
 "payload": { ... exactly what GET returned ... }}
```

`rollback` reads the file and re-`PUT`s `payload` to `path` — through the same
diff-and-confirm gate as any other write, so a rollback also shows you what it is
about to do.

The directory is **gitignored**. Do not commit it, and do not paste a snapshot into
a ticket.

## Secrets

`meraki_diff.SECRET_KEYS` covers `psk`, `secret`, `sharedsecret`, `passphrase`,
`password`, `privatekey`, `authkey`, `presharedkey`, `radiussecret` (matched
case-insensitively, at any depth).

- **Displayed diffs redact** these to `***REDACTED***`.
- **Snapshot files do not.** A rollback that restored an SSID without its PSK, or a
  VPN tunnel without its pre-shared key, would take the network down. The secret
  has to survive the round trip.

That asymmetry is deliberate. It is also why the snapshot directory is treated as
sensitive material.

## Action batches

For anything spanning multiple networks or devices, stage a batch instead of
looping `PUT`s:

```bash
python scripts/meraki_config.py batch-stage actions.json   # confirmed:false
python scripts/meraki_config.py batch-commit B_1
```

`actions.json` is a list of `{"resource": "...", "operation": "...", "body": {...}}`.

**`confirmed: false` is a real server-side dry run.** Meraki validates the whole
payload and returns per-action errors without changing anything. Read that error
list back to the user as the dry-run result before committing. This is stronger
than any local validation, because it is the same validator that will run the
write.

Limits — verified against Meraki's action-batches guide:

| Limit | Value |
|---|---|
| actions per asynchronous batch | **100** |
| actions per **synchronous** batch | **20** |
| concurrent batches per org | **5** |
| unconfirmed batches auto-deleted after | one week |

`meraki_config.py` enforces the 100-action and 5-batch caps locally so an
oversized batch fails immediately with a clear message rather than as an opaque
server rejection.

Batches are **atomic**: either every action applies or none does. A loop of `PUT`s
has no such property — it fails halfway and leaves the org in a state that matches
neither the before nor the after.

## Hard blocks

Refused outright regardless of confirmation, because **no snapshot can restore
them**:

| Operation | Why |
|---|---|
| `DELETE /networks/{id}` | destroys all config and history for the network |
| `DELETE /organizations/{id}` | irreversible |
| `POST /networks/{id}/devices/remove` | loses the device's per-network config |
| `POST /organizations/{id}/inventory/release` | unclaims the device from the org |
| `DELETE /organizations/{id}/admins/{adminId}` | can lock out the operator running this skill |
| any method on `/identities/me/api/keys` | key rotation must be done by a human in Dashboard |

These are matched by regex in `meraki_config.HARD_BLOCKS` and raise `HardBlocked`
before any HTTP call is made. The check runs on batch actions too, so a blocked
operation cannot be smuggled in inside a batch.

If one of these is genuinely intended, the answer is the Dashboard UI — not a flag.

## Why not the official `meraki` SDK

The official Python SDK is deliberately not used. It abstracts away the HTTP layer
that the write gate needs to inspect — the raw method, path, and body are what
`check_hard_block()` and the snapshot/diff logic operate on. Wrapping the SDK would
mean trusting its retry, pagination, and error semantics rather than the explicit
ones here, and would add a pip dependency to a skill that is otherwise stdlib-only.
