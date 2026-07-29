# Fortinet Skill — Design

**Date:** 2026-07-29
**Status:** Approved for implementation planning
**Target:** `skills/fortinet/` in `useful-claude-add-ons`

## 1. Purpose

A Claude Code skill that works directly against FortiGate firewalls — reading logs and
configuration, making configuration changes, and running the CLI-only diagnostic tooling —
plus the FortiAPs and FortiSwitches those FortiGates manage.

## 2. Environment (decided, not assumed)

These answers were confirmed with the user and constrain the whole design:

| Question | Answer |
|---|---|
| Management topology | **Direct to each FortiGate.** No FortiManager, no FortiAnalyzer, no FortiCloud. |
| FortiAP / FortiSwitch access | **Through the FortiGate** — WTP profiles for APs, FortiLink for switches. The FortiGate is the single control point. |
| Transports | **Both** REST API (`/api/v2`) and SSH CLI. |
| VDOMs | **Enabled** — multi-VDOM. |
| HA | **Yes**, HA clusters present. |
| Scale | **Multiple sites/devices** — needs a device inventory concept. |
| Write safety | **Backup + preview + confirm** on every mutation. |
| Credentials | **Env vars + gitignored inventory file** (inventory stores the env var *name*, never the secret). |
| SSH mechanism | **paramiko primary, system `ssh` binary fallback.** |
| Skill structure | **One skill, two transports, domain-split references.** |

Explicitly out of scope: FortiManager, FortiAnalyzer, FortiCloud/FortiGate Cloud,
FortiClient/EMS, FortiAuthenticator, FortiWeb, FortiMail. If the user later adopts
FortiManager or FortiAnalyzer those are separate skills, not extensions of this one, because
they invert the source of truth for configuration.

## 3. Directory layout

```
skills/fortinet/
├── SKILL.md                      # connect → identify → route; safety rails
├── references/
│   ├── auth-inventory.md
│   ├── config-cmdb.md
│   ├── monitor-state.md
│   ├── logs.md
│   ├── diagnostics-cli.md
│   ├── fortiap.md
│   ├── fortiswitch.md
│   └── runbooks.md
├── scripts/
│   ├── fortigate_client.py       # REST — Python stdlib only
│   └── fortigate_cli.py          # SSH — paramiko preferred, ssh binary fallback
└── assets/
    └── inventory.example.json
```

Skill `name:` is `fortinet`, matching the directory exactly, per the authoring standard.

### Why one skill, not three

FortiAPs and FortiSwitches are managed *through* the FortiGate. Splitting into `fortigate`,
`fortiap`, and `fortiswitch` skills would triplicate identical auth, inventory, VDOM scoping,
HA detection, and write-safety logic, and force constant cross-invocation. Rejected.

## 4. Frontmatter

`name: fortinet`. The `description` must carry, per authoring standard section 3:

- **What:** direct FortiGate access over REST API `/api/v2` (cmdb config, monitor state, log
  retrieval) and SSH CLI (`diagnose`/`get`/`execute`), covering the managed FortiAP and
  FortiSwitch estate, with VDOM and HA awareness and backup-preview-confirm on writes.
- **When:** trigger phrases naming products (FortiGate, FortiOS, FortiAP, FortiSwitch,
  FortiLink, WTP profile, VDOM, `diagnose debug flow`, `fnsysctl`), **plus symptom phrasings
  that never name the vendor**: "traffic is being blocked and I don't know which policy",
  "why is this session dropping", "the AP at the branch is offline", "which switch port is
  this MAC on", "the site-to-site tunnel is down", "firewall CPU is pegged", "clients can't
  associate to wifi". Also trigger on FortiGate-specific error signatures: HTTP 403 from an
  `/api/v2` path (trusted-host/accprofile denial), HTTP 424 dependency errors, and
  `cli_error` payloads.

## 5. Session bootstrap — the fixed opening sequence

Every session performs these in order before doing anything else:

1. **Resolve device** from inventory by `--device <name>` or `--tag <tag>` → host, port,
   default VDOM, token env var name, ssh user, TLS verification setting.
2. **`GET /api/v2/monitor/system/status`** — serves three purposes at once: validates the
   token, returns `hostname`/`serial`, and returns `version` + `build` for **firmware
   detection**. All references document per-release behavior (7.0 / 7.2 / 7.4 / 7.6) rather
   than assuming a single version, because FortiOS relocates and renames API paths between
   releases. The skill branches on detected version; it never guesses.
3. **HA role check** — determine whether the target is HA primary. Reads are fine anywhere;
   **writes against an HA secondary are refused**, not attempted. The role is determined
   **live from the device**, not from the inventory file: the inventory's `role` field is a
   human-facing hint only, and a stale hint must never authorize a write. If the live check
   cannot be completed, treat the role as unknown and refuse the write.
4. **VDOM scoping** — every cmdb and monitor call carries an explicit `?vdom=<name>`.
   `?vdom=*` for deliberate cross-VDOM reads, `?global=1` for global-scope objects. The skill
   never relies on the token's implicit default VDOM, because that is how you edit the wrong
   VDOM's policy set.

## 6. Authentication model

- **REST:** API token in an `Authorization: Bearer <token>` header. Never the deprecated
  `?access_token=` query parameter, which lands the token in device logs.
- Tokens come from an API user created on the device (`config system api-user`) with:
  - a **restricted accprofile** — the skill documents creating a read-only profile for
    diagnosis and a separate write-capable profile, and recommends using the read-only one by
    default;
  - a **`trusthost` restriction** limited to the admin subnet the skill runs from. An
    unrestricted API user is called out as unacceptable.
- **SSH:** dedicated service admin account, key auth preferred, password auth supported via
  paramiko. Credentials resolve from env vars, never from the inventory file.
- Tokens and passwords are never echoed, never logged, and are **redacted from captured CLI
  output** before it reaches the transcript.

## 7. Inventory

Shipped as `assets/inventory.example.json`. The live file lives at
`%USERPROFILE%\.fortinet\inventory.json`, overridable with `$FORTINET_INVENTORY`, and is
gitignored.

```json
{
  "devices": [
    {
      "name": "dfw-edge",
      "host": "10.10.0.1",
      "port": 443,
      "default_vdom": "root",
      "role": "ha-primary",
      "ha_peers": ["dfw-edge-b"],
      "token_env": "FGT_TOKEN_DFW_EDGE",
      "ssh_user": "svc-claude",
      "verify_tls": "C:/certs/fgt-ca.pem",
      "tags": ["dallas", "edge"]
    }
  ]
}
```

Rules:

- The file stores the **name of the env var** holding each token (`token_env`), never a token.
- `verify_tls` accepts a CA bundle path, or `false` for self-signed appliances. When `false`,
  the client emits a visible warning on every call rather than silently disabling
  verification.
- A missing inventory file is not an error: the client falls back to
  `FORTIGATE_HOST` / `FORTIGATE_TOKEN` / `FORTIGATE_VDOM` for one-off use.

## 8. REST client — `scripts/fortigate_client.py`

**Python stdlib only** (`urllib.request`, `ssl`, `json`, `argparse`). No `pip install` step,
so it runs anywhere. Importable as `from fortigate_client import FortiGateClient` for larger
scripts.

### Commands

| Command | Purpose |
|---|---|
| `status` | Bootstrap: version, build, serial, hostname, HA role. The live smoke test. |
| `devices` | List inventory entries (names/tags/hosts only — no secrets). |
| `get <path>` | Single GET against `/api/v2/...`. |
| `get-all <path>` | Auto-paginated GET (`start`/`count`) until exhausted. |
| `post` / `put` / `delete <path>` | Mutations. Dry-run by default. |
| `backup` | `GET /api/v2/monitor/system/config/backup` → timestamped local file. |
| `revisions` | List on-device config revisions. |
| `logs <source>/<type>/<subtype>` | Wrapper over `/api/v2/log/...` with `--since`, `--filter`, `--rows`. |

Global flags: `--device`, `--tag`, `--vdom`, `--global`, `--filter`, `--fields`, `--json`.

### Mutation flow

`--dry-run` is the **default** on every mutating verb. `--apply` is required to write, and
`--apply` executes this sequence:

1. Fetch a full config backup to a timestamped local file.
2. `GET` the current state of the target object.
3. Print a **field-level diff** of current vs. proposed.
4. Require explicit confirmation.
5. Write.
6. Re-`GET` and print the resulting object so the outcome is verified, not assumed.

If step 1 fails, the mutation aborts. No backup, no write.

### Error mapping

FortiGate's status codes mislead in ways that cost real time, so the client names the actual
cause:

| Code | Reported as |
|---|---|
| 401 | Token expired, malformed, or revoked. |
| 403 | **Trusted-host or accprofile denial — not a bad token.** Names both candidates. |
| 404 | Path does not exist on this firmware; includes the detected version in the message. |
| 424 | Dependency failure — a referenced object is missing or the target is still referenced. |
| 5xx | Surface the `cli_error` value from the response body verbatim. |

## 9. SSH runner — `scripts/fortigate_cli.py`

Covers what REST cannot: `diagnose debug flow`, `diagnose sniffer packet`,
`diagnose sys session`, routing-daemon `get router info`, IKE/VPN debug, and the
wireless/switch `diagnose` families.

**Transport:** paramiko when importable — it gives real interactive-shell control, which the
multi-step debug-flow sequence and `--More--` pager handling require, and supports password
auth. Falls back to the system `ssh` binary (present on Windows 11) when paramiko is absent,
which requires key auth and handles single commands only. The paramiko dependency is declared
at the top of `SKILL.md` and in the script header, per authoring standard section 1.

### Recipes

`flow-trace` · `sniffer` · `session-list` · `route-lookup` · `bgp` · `ha-status` · `perf` ·
`vpn-tunnels` · `raw "<command>"`

### The teardown rule (non-negotiable)

Every debug recipe runs its teardown in a `finally` block. A `diagnose debug enable` or an
abandoned sniffer pins the firewall's CPU and will eventually take a site down. The recipe
owns its own cleanup — `diagnose debug disable`, `diagnose debug flow trace stop`,
`diagnose debug flow filter clear`, sniffer interrupt — rather than trusting the conversation
to remember. This is enforced in code, not documented as a reminder.

### Pager handling

`--More--` prompts are answered by feeding spaces. The skill does **not** set
`config system console` → `set output standard`, because that is a persistent configuration
write performed as a side effect of a read. The device-side setting is documented as an
optional one-time operator change.

### Capture hygiene

Sniffer output can contain payload data. The runner warns before writing captures to disk and
notes that pcap conversion produces a file containing potentially sensitive traffic.

## 10. Reference map

| Task | Reference file |
|---|---|
| Token creation, accprofiles, trusthosts, inventory, VDOM and HA scoping | `references/auth-inventory.md` |
| Config read/write: firewall policy, address/service objects, interfaces, static/dynamic routing, VPN | `references/config-cmdb.md` |
| Operational state: sessions, routing table, ARP, interface counters, licenses, performance | `references/monitor-state.md` |
| Log retrieval via REST and CLI: source/type/subtype matrix, filter syntax, disk-vs-memory retention caveats | `references/logs.md` |
| CLI-only diagnostics: debug flow, sniffer, session filters, IKE/VPN debug, teardown requirements | `references/diagnostics-cli.md` |
| FortiAP: `wireless-controller` cmdb (wtp, wtp-profile, vap), managed-AP/client/rogue monitor endpoints, RF troubleshooting | `references/fortiap.md` |
| FortiSwitch: `switch-controller` cmdb, port state and stats, PoE control, MAC-to-port lookup, VLAN, 802.1X | `references/fortiswitch.md` |
| End-to-end troubleshooting flows | `references/runbooks.md` |

### Runbooks to write

1. Traffic is being blocked — identify the deciding policy (flow trace → policy ID → policy object).
2. A user cannot reach an application — session lookup, route lookup, UTM log correlation.
3. FortiAP offline, or clients failing to associate.
4. Which switch port is this MAC on, and bounce its PoE.
5. Site-to-site VPN down — IKE phase 1/2 triage.
6. Config drift — diff running config against the last backup.
7. HA cluster out of sync — checksum comparison.
8. CPU or memory spike triage.

Each runbook names the exact commands and endpoints, in order, with the decision points
between them.

## 11. Safety rails

1. **Read-only by default.** Every mutating verb requires `--apply` plus explicit user
   confirmation that names the device *and* the VDOM.
2. **Backup before every mutation**, aborting the mutation if the backup fails.
3. **Hard-block list.** These require the user to type the device name to proceed, because
   they can sever access to the device being edited:
   - management interface addressing
   - `system admin`, `system api-user`, `trusthost`
   - HA settings
   - admin access ports (`system global`)
   - certificate changes
   - VDOM deletion
   - firmware upgrade
   - factory reset
   - setting a policy carrying live traffic to `deny`
4. **Writes refused against an HA secondary.**
5. **No credential leakage** — tokens never echoed, never written to the inventory file,
   redacted from captured CLI output.
6. **Mandatory debug teardown** — the skill must never leave `diagnose debug enable` active.
7. **TLS verification on by default**; disabling it warns on every call.

## 12. Testing

- **Fixture-driven unit tests.** Sanitized recorded JSON responses (system status, firewall
  policy list, log query, managed AP list, managed switch list, error bodies) drive tests for:
  pagination termination, explicit-VDOM parameter construction, diff generation, error-code
  mapping, HA-secondary write refusal, and **teardown ordering in the SSH recipes**. No live
  device required.
- **One live smoke test:** `python scripts/fortigate_client.py status --device <name>`.
- Fixtures contain no real hostnames, serials, IPs, or tenant identifiers, per `SECURITY.md`.

## 13. Verify against real firmware during implementation

These need confirmation against the user's actual FortiOS build rather than being asserted
from memory. Each is a documented implementation task, not a design assumption:

- CMDB transaction support (`transaction-start` / `-commit` / `-abort` and its header name) —
  use it if present, fall back to per-object writes if not.
- Exact `config-revision` endpoint paths for listing and fetching revisions.
- Exact FortiAP action endpoint paths under `/api/v2/monitor/wifi/` (AP restart, status set).
- Exact FortiSwitch action endpoint paths under `/api/v2/monitor/switch-controller/`
  (PoE reset, switch restart, port stats).
- Log API time-range parameter form (`filter` date comparison vs. dedicated time params) for
  the detected release.
- Whether the FortiGate SSH service on the target build honors a single-command exec channel,
  which determines how usable the `ssh`-binary fallback actually is.

## 14. Repo registration (authoring-standard checklist)

- [ ] `skills/fortinet/SKILL.md`, no double-nesting, `name:` matches directory.
- [ ] Row added to the table in `skills/README.md` — category "Security / Networking".
- [ ] Plugin entry added to `.claude-plugin/marketplace.json` at version `1.0.0`.
- [ ] `CHANGELOG.md` updated under `Unreleased`.
- [ ] No secrets, real hostnames, serials, or customer data in any file.
- [ ] Every mutating operation has a documented dry-run path.
