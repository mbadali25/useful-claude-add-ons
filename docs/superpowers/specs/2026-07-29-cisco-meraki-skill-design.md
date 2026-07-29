# Cisco Meraki Skill — Design

**Date:** 2026-07-29
**Status:** Approved, pending implementation plan
**Target:** `skills/cisco-meraki/`

## 1. Purpose

A skill that gives Claude direct, safe access to a Cisco Meraki estate through the Dashboard API v1: read configuration and status, pull logs and audit trails, run live diagnostics, and make configuration changes to MX appliances, MS switches, and MR access points.

The defining risk this design addresses: Meraki's collection config endpoints are **full-replacement PUTs**. `PUT /networks/{id}/appliance/firewall/l3FirewallRules` carrying three rules does not add three rules — it deletes every rule not present in the payload. Most Meraki API accidents trace to that single behavior, so the architecture makes the mitigation structural rather than advisory.

## 2. Environment (decided, not assumed)

| Dimension | Decision |
|---|---|
| Management plane | Dashboard API v1 only — `https://api.meraki.com/api/v1`. No on-box access, no MQTT, no Scanning API, no Captive Portal API, no Webhooks receiver. |
| Org scope | Single organization. Bootstrap resolves exactly one org ID; if the key can see more than one, the skill stops and asks rather than guessing. |
| Product families | MX (appliance), MS/Catalyst (switch), MR (wireless). MV cameras, MT sensors, and SM/Systems Manager are explicitly out of scope. |
| Transport | HTTPS REST with `Authorization: Bearer <key>`. |
| Client dependencies | stdlib-only Python (`urllib`). No pip install step. |
| Write model | Snapshot → diff → confirm on every persistent-config change. Bulk changes go through staged Action Batches. |
| Official SDK | Not used, and not documented as an alternative. The `meraki` pip package would hide the HTTP layer that the write gate depends on inspecting. |

### Why one skill, not several

Meraki is a single cloud API with a single auth model and a single rate-limit domain. MX, MS, and MR are product surfaces *within* that API, not separate systems — they share org resolution, network resolution, pagination, backoff, and the change-safety machinery. Splitting by product family would triplicate all of it and force constant cross-invocation for any question spanning a site.

## 3. Directory layout

```
skills/cisco-meraki/
├── SKILL.md
├── references/
│   ├── auth-and-bootstrap.md
│   ├── inventory-and-status.md
│   ├── appliance-mx.md
│   ├── switch-ms.md
│   ├── wireless-mr.md
│   ├── logs-and-events.md
│   ├── live-tools.md
│   └── change-safety.md
└── scripts/
    ├── meraki_client.py     # reads + ephemeral live-tool jobs
    └── meraki_config.py     # the only persistent-config mutation path
```

## 4. Frontmatter

`name: cisco-meraki`, matching the directory.

The `description` follows the repo's two-part what+when shape. It must name: Meraki, Cisco Meraki, Meraki Dashboard, MX/MS/MR, `api.meraki.com`, and the concrete operations (inventory, device status, event log, config change log, firewall rules, VLANs, switch ports, SSIDs, live diagnostics).

It must also carry symptom phrasings that never name the product, since those are how the skill will actually get invoked in practice:

- "which APs are offline"
- "who changed the firewall rules"
- "why is this switch port flapping"
- "cycle port 12 on the second-floor switch"
- "what broke since Friday"

And the API's characteristic failures: `429` rate limiting, and the `404` returned when the event-log endpoint is called without a `productType` on a combined network.

## 5. Bootstrap — the fixed opening sequence

Every session, in order:

1. **Read the key** from `MERAKI_DASHBOARD_API_KEY` — the name the official Meraki tooling uses, so it is likely already present in the environment. Never echo it. Never accept it pasted into chat; if missing, instruct the user to export it.
2. **`GET /organizations`** — resolves the org ID and simultaneously validates the key. Exactly one org is expected. More than one is a hard stop that lists them for the user to choose.
3. **`GET /organizations/{orgId}/networks`** — the network map. Every subsequent call needs a `networkId`. This is also where each network's `productTypes` is cached, because the event-log endpoint requires `productType` on combined networks and returns a misleading `404` without it.
4. **`GET /organizations/{orgId}/devices/statuses`** — one call for org-wide `online` / `offline` / `alerting` / `dormant`. This answers most status questions before any per-device endpoint is touched.

Steps 2–4 are cached to `.meraki-snapshots/.cache-{orgId}.json` — the same gitignored directory the snapshots use, so there is one path to exclude rather than two. Routine work then costs four calls total rather than four per question. The cache is keyed by org ID and invalidated on explicit user request or when a network lookup misses.

## 6. Authentication model

- API keys are generated per-user in Dashboard under **My Profile → API access**. A key inherits that user's Dashboard permissions — there is no separate API RBAC. Recommend a dedicated service account scoped to the minimum required role, and say so when helping a user create one.
- Org-level API access must be enabled under **Organization → Settings → Dashboard API access**. If it is not, calls fail in a way that reads like an auth problem; `references/auth-and-bootstrap.md` documents the distinction.
- The key is read from the environment only. It never appears in output, logs, snapshots, error text, or committed files.

## 7. Read path — `scripts/meraki_client.py`

Handles every `GET`, plus live-tool job creation and polling. It contains no code path that writes persistent configuration — that separation is the enforcement mechanism for the write gate described in section 8.

Live-tool `POST`s live here rather than in the config tool because they create ephemeral diagnostic jobs and mutate no stored configuration. The dividing line between the two scripts is exactly one question: *does this change persistent org or network config?*

### Subcommands

| Subcommand | Covers |
|---|---|
| `orgs`, `networks`, `inventory`, `status` | The cached bootstrap set |
| `get <path>` | Generic single-page GET with `--params` |
| `get-all <path>` | Auto-paginate, following `Link: rel=next` until exhausted |
| `events --network <id>` | Network event log, auto-injecting `productType` from the cached network map |
| `changes` | Org configuration change log |
| `security-events` | MX IDS/malware events, org-wide or per-network |
| `air-marshal --network <id>` | MR rogue-AP detections |
| `live <tool> <serial>` | Create job, poll to terminal state, print result |

### Pagination

`perPage` maxima are **per-endpoint, not global** — 1000 on some endpoints, 50 or as low as 5 on others. `get-all` therefore never hardcodes a page size. It treats the server's `Link` header as authoritative and leaves the endpoint's own default in place unless `--per-page` is passed explicitly.

### Time windows

`--timespan <seconds>`, or `--t0` / `--t1` as ISO 8601. Per-endpoint maximums differ materially (the config change log accepts up to 365 days; most telemetry endpoints cap at 31). The client validates against a per-endpoint table and fails fast quoting the actual limit, rather than letting the API return an opaque `400`.

### Live tools

Create-then-poll: `POST /devices/{serial}/liveTools/{tool}` returns a job ID, then `GET` that ID until `status` reaches a terminal value. The client polls with backoff and a hard timeout so a stuck job cannot hang the session.

Tool availability is platform-bound — cable test is MS-only, throughput test is MX/MR. The client checks the device model against the cached inventory and refuses early with a clear reason rather than surfacing a bare `400`.

### Transport requirements

Two behaviors that are easy to get silently wrong in `urllib` and must be implemented explicitly:

- **Redirects.** Meraki may respond `308` pointing at a shard host. `urllib`'s default redirect handler downgrades `POST` to `GET` on `301`/`302` and drops the `Authorization` header on a cross-host redirect. Install a custom handler that preserves both method and header.
- **Rate limiting.** 10 requests/second per organization, token-bucket enforced. On `429`, honor `Retry-After`, then exponential backoff with jitter.

Surface the `X-Request-Id` response header on any failure — Meraki support asks for it, filling the same role as Sophos Central's `correlationId`.

### Error surface

Non-2xx responses return JSON shaped `{"errors": [...]}`. Map these to actionable messages, distinguishing in particular: org API access disabled, insufficient Dashboard role, wrong `productType`, and endpoint-not-available-for-this-model.

## 8. Write path — `scripts/meraki_config.py`

The only route by which persistent configuration changes.

```
snapshot <path>                # GET current state → timestamped JSON under .meraki-snapshots/
diff <path> <proposed.json>    # semantic diff vs live state; exits non-zero when no change
apply <path> <proposed.json>   # snapshot, diff, require confirmation, then PUT
rollback <snapshot.json>       # re-PUT a prior snapshot
batch-stage <actions.json>     # POST action batch with confirmed:false — server-side validation
batch-commit <batchId>         # PUT confirmed:true, then poll to completion
```

`apply` cannot execute without having written a snapshot and rendered a diff, because that is its own control flow — not a rule documented elsewhere that the model must remember to follow.

### Semantic diff

The diff is semantic, not textual. A textual diff of two JSON blobs for a full-replacement collection is unreadable and obscures the thing that matters. The diff renders rule-level `+ added` / `- removed` / `~ changed` lines with positional context.

Position is included because in an ordered rule set **position is semantics**: moving a deny above a permit changes behavior while set membership stays identical. A diff that treats rule lists as unordered sets would report "no change" on a reorder that breaks production.

### The implicit default rule

`GET` on L3 firewall rules returns Meraki's implicit trailing `Allow any → any` default rule, but `PUT` rejects that rule in the payload. Consequences if unhandled:

- A naive snapshot → `PUT` round trip fails outright.
- A naive diff reports a spurious removal on every single change.

The tool strips the default rule on read and re-derives it on write. `references/change-safety.md` documents this explicitly so that a future contributor does not "fix" it back.

### Bulk changes via staged Action Batches

Any change touching multiple networks or devices is assembled into an action batch and staged with `confirmed: false`. Meraki then validates the entire payload server-side before anything commits, and the staged batch's own error list becomes the dry-run result shown to the user. Commit is a separate explicit step.

Caps the tool enforces rather than discovers at runtime: 100 actions per batch, 5 pending batches per org.

Batches are also the atomicity mechanism — a looped sequence of individual PUTs that fails halfway leaves the org in a mixed state, which a batch avoids.

## 9. Safety rails

- **Snapshot before every write, without exception.** The snapshot path is printed on completion so rollback is always one command away.
- **Confirmation shows the diff, not a count.** "3 rules will change" is not a confirmation prompt. The rendered diff is the prompt.
- **Hard-block list.** Refused outright regardless of confirmation, because they are destructive beyond what a snapshot can restore:
  - delete network
  - delete organization
  - remove or unclaim a device from the org
  - revoke admin access
  - rotate or delete API keys

  These require the Dashboard UI. The refusal names the operation and the reason.
- **Credential and secret redaction.** The API key never appears in output, logs, snapshots, or error text. Snapshots are written under a gitignored directory. Configuration carrying shared secrets — site-to-site VPN PSKs, RADIUS secrets — is redacted in *displayed* diffs while preserved intact in the snapshot, so that a diff pasted into a ticket does not leak a secret.

## 10. Reference map

| Task | Reference |
|---|---|
| API key setup, org access enablement, bootstrap, rate limits, redirect handling | `auth-and-bootstrap.md` |
| Org inventory, device statuses, uplink health, licensing models | `inventory-and-status.md` |
| MX: VLANs, L3/L7 firewall, static routes, site-to-site VPN, content filtering, traffic shaping | `appliance-mx.md` |
| MS: port config and status, ACLs, STP, QoS, stacks, L3 interfaces, port cycling | `switch-ms.md` |
| MR: SSIDs, RF profiles, radio settings, client connectivity and latency stats | `wireless-mr.md` |
| Network event log, config change log, security events, Air Marshal | `logs-and-events.md` |
| Ping, cable test, throughput test, ARP/MAC table, wake-on-LAN | `live-tools.md` |
| Snapshot/diff/rollback semantics, action batches, hard-block list, implicit default rule | `change-safety.md` |

## 11. Runbooks

Written as "user says X → do Y then Z" against real endpoint paths.

1. **What's down right now** — org status sweep → uplink statuses → uplink loss/latency → live ping the suspect device.
2. **What changed / what broke since Friday** — config change log windowed to the outage, correlated against the network event log for the affected networks.
3. **Change a firewall rule safely** — snapshot → edit → diff → apply, including implicit-default-rule handling.
4. **Switch port troubleshooting** — port statuses → error and discard counters → cable test → cycle port.
5. **Wireless client complaints** — client connectivity stats → latency stats → channel utilization → Air Marshal for interference.
6. **Site-to-site VPN tunnel down** — VPN status → uplink loss/latency → event log correlation.
7. **Inventory and license audit** — detect the licensing model *first*. Co-termination orgs answer on `/licenses/overview`; per-device orgs answer on `/licenses`. Calling the wrong one returns a `400` that reads like a permissions problem.
8. **Bulk change across networks** — build actions → `batch-stage` → review server-side errors → `batch-commit`.

## 12. Testing

Fixture-driven unit tests requiring no live API, covering what is most likely to break silently:

- `Link: rel=next` pagination termination
- `429` backoff honoring `Retry-After`
- redirect handler preserving both HTTP method and `Authorization` header across a `308`
- L3 firewall implicit-default-rule strip-on-read / re-derive-on-write round trip
- semantic diff flagging a **reorder** as a change when set membership is unchanged
- hard-block refusals for each listed operation
- redaction — assert the API key and any PSK never appear in rendered output

Plus one live smoke test, read-only, gated behind an env var: bootstrap → status → a single event-log page.

## 13. Verify against the live API during implementation

Listed as verification tasks rather than asserted facts. Meraki relocates these between API revisions, and a wrong path returns a `404` that reads like a permissions failure — so asserting them from memory would produce confidently wrong code.

- exact `perPage` maximum for each endpoint the skill uses
- current canonical path for org uplink statuses (`/uplinks/statuses` vs `/appliance/uplink/statuses`)
- the live-tools set actually available, and per-model licensing prerequisites for each
- action-batch caps (documented here as 100 actions / 5 pending per org)
- configuration-change-log maximum timespan
- whether `Authorization: Bearer` or `X-Cisco-Meraki-API-Key` is currently canonical, and whether the legacy header is still accepted
- the exact terminal status values returned by live-tool job polling

## 14. Repo registration (authoring-standard checklist)

- [ ] `skills/cisco-meraki/SKILL.md` exists, no double nesting
- [ ] `name:` matches the directory exactly
- [ ] `description` covers what + when with concrete trigger phrases
- [ ] No secrets, real org IDs, serials, or hostnames anywhere in the skill's files
- [ ] Every mutating operation has a documented dry-run path and confirm-before-acting rule
- [ ] `references/` carries anything long enough not to warrant preloading; `SKILL.md` stays skimmable
- [ ] Added to the table in `skills/README.md`
- [ ] Registered as a plugin entry in `.claude-plugin/marketplace.json`
- [ ] `CHANGELOG.md` updated under `Unreleased`
- [ ] `.meraki-snapshots/` added to `.gitignore`
