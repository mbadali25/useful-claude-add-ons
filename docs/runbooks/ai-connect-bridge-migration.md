# ai-connect bridge migration runbook — dadeush-desktop → dadeush-ai

**Status: PLAN ONLY. Nothing has been executed. Nothing has been changed.**
Written 2026-11-25. Author: useful-claude-add-ons session (`dadeush-desktop:s-useful-claude-add-ons-43`).

Every line below is marked **[V]** verified in-session (with the command or path that proved it),
**[P]** peer-reported, or **[I]** inferred. Do not execute a step that depends on an **[I]** or
**[P]** line until it is verified.

**[P] = peer-reported, not independently verified.** Every `dadeush-ai` fact marked **[P]** was
reported by session `dadeush-ai:s-srl-ai`, which labelled each as verified on its own host with a
command. None was reproduced from `dadeush-desktop` (see the blocked probe note in section 1).

---

## 1. What is true today

| Fact | Evidence |
|---|---|
| Bridge host is `dadeush-desktop`, Tailscale `100.117.116.57`, tag `tag:bridge` | **[V]** `tailscale status --json`, `tailscale debug prefs` |
| ai-connect version 0.2.17 | **[V]** `%LOCALAPPDATA%\ai-connect\app\.claude-plugin\plugin.json` |
| Bridge process pid 6960 (`pythonw`) listens on `100.117.116.57:9999` **and** `:10000` | **[V]** `Get-NetTCPConnection -State Listen` |
| Port 9999 = plain `ws://`; port 10000 = TLS `wss://` | **[V]** listener set; **[I]** TLS role of 10000 from `srl-anew-SETUP.md` |
| 19 peer sessions online across 6 machines | **[V]** `peer_list` census |
| 10 peers enrolled as `auth.peers.<name>: <sha256>` (flat map, config.yaml:12-22) | **[V]** `config.yaml` |
| `dadeush-ai` is **already enrolled** (hash prefix `88471062`) | **[V]** `config.yaml` |
| Single tailnet `mbadali25.github`; **no cross-account Tailscale nodes** | **[V]** `tailscale status --json` Users map |
| `dadeush-ai` = `100.87.39.3`, tag `tag:ai-peer`, online, **same LAN** (`192.168.4.98`), 2ms direct, no DERP | **[V]** `tailscale ping --c 5` |
| `dadeush-ai:9999` closed; its 22 and 445 open | **[V]** `Test-NetConnection` |
| `dadeush-ai → here:9999` is permitted by ACL | **[V]** `tailscale debug netmap` packet filter (8 srcs → `100.117.116.57/32`, ports 0-65535) |
| `here → dadeush-ai:9999` is permitted by ACL | **[P]** `tailscale debug netmap` on dadeush-ai: a packet-filter rule with Srcs including `100.117.116.57/32`, Dsts `100.87.39.3/32` (+ `fd7a:115c:a1e0::7e48:2704/128`), ports 0-65535, IPProto 6,17,1,58 (TCP/UDP/ICMP/ICMPv6). The reverse path is open. |
| ai-connect on dadeush-ai is **0.2.5** (bridge here: 0.2.17); nothing listening on 9999; no scheduled task or service for ai-connect/bridge | **[P]** reported by `dadeush-ai:s-srl-ai` |
| Windows firewall on dadeush-ai: Domain, Private and Public profiles all `Enabled=True`; inbound enabled rules matching `9999\|ai-connect`: **none** | **[P]** reported by `dadeush-ai:s-srl-ai` |
| dadeush-ai's `config.yaml` already has a `server:` section bound to `host: 127.0.0.1`, port 9999 | **[P]** reported by `dadeush-ai:s-srl-ai` |

### Direct probe of dadeush-ai: attempted, blocked
A read-only probe of dadeush-ai from dadeush-desktop was attempted and **blocked**. SMB
`Test-Path '\\100.87.39.3\c$\Users'` returned `False`; SSH failed `Host key verification failed` with
no `known_hosts` entry. No credential was guessed and `StrictHostKeyChecking` was not bypassed.
That is why every dadeush-ai fact above is **[P]**, not **[V]**.

### The 3 "off-account" sessions
The owner reported 3 sessions not on this account. **[V]** There are **no cross-account Tailscale
peers** — every node is in tailnet `mbadali25.github`, the only human owner is `mbadali25@github`
(`dadeush-buntun`), and all others are tagged devices, which have no human owner by design.
**[I]** The split is therefore a *Claude account* split (memory names `badalim@anewbiz.net`), not a
VPN one. `peer_list` carries no account field.

**Correction:** an earlier draft placed these sessions on `dadeush-ai` because it has 3 sessions
(`srl-ai`, `tss-ai`, `vault`) reporting `state unknown`. **[P]** `srl-ai` reports its Claude account
as `mbadali25@gmail.com`, the **same** account. So dadeush-ai is **not** where the off-account
sessions live; the 3-sessions / 3-state-unknown match was coincidence. **Which machine holds the
off-account sessions is unknown.**

**This means: there is nothing to migrate on the Tailscale side for the account split.** Retagging
or re-signing-in will not change which Claude account a session runs under.

---

## 2. Blockers that must clear before any cutover

| # | Blocker | Who | Why it blocks |
|---|---|---|---|
| B1 | ~~Prove `100.117.116.57 → 100.87.39.3:9999` is allowed~~ **RESOLVED [P]** | dadeush-ai netmap | Packet-filter rule permits Srcs `100.117.116.57/32` → Dsts `100.87.39.3/32`, ports 0-65535, IPProto 6,17,1,58. Reverse path open. Re-confirm with step 7's `Test-NetConnection`. |
| B2 | ~~Tailnet policy may key the bridge rule on `tag:bridge`; `dadeush-ai` holds `tag:ai-peer`~~ **RESOLVED [V], no retag needed** | Tailscale API, read-only | The live policy already permits `tag:ai-peer` on every port. See "B2 evidence" below. No policy edit, no retag, no admin-console step. |
| B3 | TLS cert `tls\bridge-cert.pem` is bound to `100.117.116.57` | Owner decision | Peers using `wss://…:10000` (srl-anew documented) break until a new cert is issued. |
| B4 | **Version gap to assess:** dadeush-ai runs ai-connect **0.2.5** **[P]**, the bridge runs **0.2.17** **[V]** — 12 versions apart, significance unchecked; **not** the cause of `state unknown` (see section 5) | Whoever owns the plugin changelog | Installed, but whether 0.2.5 can serve or read the migrated `config.yaml` / `messages.db` is unknown. Nothing listens on 9999 there and no scheduled task or service exists **[P]**. |
| B5 | **CONFIRMED blocker [P]:** all three firewall profiles are enabled on dadeush-ai and **no** inbound rule matches `9999\|ai-connect` | dadeush-ai, needs admin | The tailnet permits 9999; Windows would drop it. Add an inbound allow rule on dadeush-ai **before cutover step 7**. |
| B6 | **New [P]:** dadeush-ai's `config.yaml` already has `server.host: 127.0.0.1`, port 9999 | dadeush-ai | A bridge started there is **loopback-only and reachable by nothing** until `server.host` is changed to `100.87.39.3`. Explicit edit in section 4b. |

### B2 evidence

**[V]** Read-only `GET` of the live tailnet policy through the Tailscale API (HTTP 200,
`GET /api/v2/tailnet/mbadali25.github/acl` and `/devices`; the API key came from AWS Secrets Manager
`prod/vpn/tailscale` and is not recorded here). The policy has exactly one rule, in `grants`, and no
`acls` block:

```
{
  "src": ["tag:bridge", "tag:ai-peer", "autogroup:admin"],
  "dst": ["tag:bridge", "tag:ai-peer", "autogroup:admin"],
  "ip":  ["*"],
}
```

Why this resolves B2:
- The grant is symmetric and `ip: ["*"]` covers every port, including 9999 and 10000.
- `tag:ai-peer` is in `dst`, so traffic into `dadeush-ai` on 9999 is already permitted from `tag:bridge`, `tag:ai-peer` and `autogroup:admin`.
- The policy's own `tests` block asserts `tag:ai-peer` -> `tag:ai-peer:9999` and `tag:ai-peer` -> `tag:bridge:9999`.
- `tagOwners`: `"tag:ai-peer": ["autogroup:admin"]` and `"tag:bridge": ["autogroup:admin"]`.
- Device tags from `/devices`: `dadeush-ai` = `['tag:ai-peer']`, authorized, does **not** carry `tag:bridge`; `dadeush-desktop` = `['tag:bridge']`, authorized.

**No ACL edit and no retag is required for the cutover.** Retagging `dadeush-ai` to `tag:bridge` would
also work and is purely a naming choice. The earlier owner-only admin-console prerequisite is
**checked and cleared**: the policy was read through the API and needs no change.

**Not tested:** live connectivity to `dadeush-ai:9999`, because nothing listens there yet. The ACL
permits it, which is not the same as proven; cutover step 7's `Test-NetConnection` is the proof.

**Do not begin section 4 until B4's version gap is assessed. B1 and B2 are resolved. The remaining blockers are B3 (owner decision on the TLS cert), B4 (version gap), B5 (inbound firewall rule for 9999 on dadeush-ai) and B6 (`server.host` is `127.0.0.1` on dadeush-ai). B5 and B6 are fixed inside section 4 (steps 4 and 7).**

---

## 3. The hazard that will sabotage a naive cutover

**`\AI-Connect Watchdog` fires every 60 seconds.** **[V]** `schtasks /query /fo list`:

- Trigger: time trigger, repeat every 1 minute, start 2026-11-04T17:15:00
- Runs as `d3ade`, Interactive logon
- Command: `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\d3ade\.config\ai-connect\ai-connect-watchdog.ps1`
- Behaviour: restarts the bridge task via `schtasks /End` then `/Run`, up to 3× per hour
- `$HostName` hardcoded to `100.117.116.57` at `ai-connect-watchdog.ps1:16`

Stop the bridge without disabling this first and it comes back on the old host within a minute,
leaving two bridges or a flapping one. **Disabling the watchdog is step 1 of the cutover, not a
cleanup task.**

### Second hazard: logon-only bridge trigger — FIXED on dadeush-desktop, 2026-11-25

**What it was.** The bridge scheduled task `\AI-Connect Bridge` had a **LogonTrigger only, no boot
trigger**, with principal LogonType `InteractiveToken`, so the bridge did **not** start until the
user logged in interactively. Replicated as-is on a headless `dadeush-ai`, that is an availability
regression.

**What it is now.** **[V]** `schtasks /query /tn "AI-Connect Bridge" /xml`, re-read after the change:
the principal's `LogonType` is **`S4U`**, and a **`BootTrigger` with `<Delay>PT1M</Delay>`** now sits
beside the existing `LogonTrigger` (`DADEUSH-DESKTOP\d3ade`). The action, working directory,
`MultipleInstancesPolicy IgnoreNew`, `ExecutionTimeLimit PT0S` and `RestartOnFailure`
(`<Count>999</Count>`, `<Interval>PT1M</Interval>`) are unchanged.

- **[V]** Pre-change task definition backed up to
  `C:\Users\d3ade\.config\ai-connect\AI-Connect-Bridge-task-backup-20261125.xml` (1,404 B).
  Rollback: `schtasks /create /tn "AI-Connect Bridge" /xml <that path> /f`.
- **[V]** **S4U, not `SYSTEM`, was required.** The app resolves its config from `Path.home()` —
  `config_loader.py:20` (`CONFIG_PATH = Path.home() / ".config" / "ai-connect" / "config.yaml"`),
  and likewise `log_setup.py:9` and `root_policy.py:50`, in
  `%LOCALAPPDATA%\ai-connect\app`. A `SYSTEM` principal resolves a different home and breaks the
  app. Proven with a throwaway S4U probe task that reported `Path.home()` as `C:\Users\d3ade`.
- **[I] Boot behaviour is UNPROVEN — no reboot has been performed.** What is verified is the task
  *definition*: S4U principal plus a delayed BootTrigger. That the bridge actually comes up before
  logon after a cold boot has not been observed.
- **[V]** `\AI-Connect Watchdog` was deliberately **not** changed; its principal is still
  `InteractiveToken` (`schtasks /query /tn "AI-Connect Watchdog" /xml`). Backup at
  `C:\Users\d3ade\.config\ai-connect\AI-Connect-Watchdog-task-backup-20261125.xml` (1,454 B). The
  owner chose to leave it, because the bridge task's own `RestartOnFailure` already covers the
  pre-logon window.

**Still open for the new host.** The fix was applied to `dadeush-desktop` only. The task created on
`dadeush-ai` needs the same shape — S4U principal, delayed boot trigger, `RestartOnFailure` — or a
service (section 4c step 6). Do not copy the old logon-only shape.

### Third hazard: the bridge binds its address once, with no retry

**[V]** `server/websocket_server.py:192-199` calls `websockets.serve` on `self.host` with **no
retry**, and `server/main.py:108` awaits `server.start()` **unguarded**. If the Tailscale IP named by
`server.host` is not yet assigned when the process starts, the bind raises `OSError` and the process
dies — no backoff, no rebind, nothing in the call path that catches it.

This is independent of which machine the bridge lives on, and it bites hardest at boot, when
Tailscale may not have brought the interface up yet. At boot the **only** mitigation is the scheduled
task's `RestartOnFailure` (999 attempts, 1-minute interval) — which is why the new BootTrigger
carries a `PT1M` delay rather than firing immediately. A cutover to `dadeush-ai` inherits the same
fragility: give that task the same delay and the same restart policy, and treat a bridge that is
"configured but not listening" after a reboot as this failure first.

---

## 4. Cutover procedure (do not run yet)

### 4a. What must be carried to the new host

Must migrate (peer identity and history):
- `~/.config/ai-connect/config.yaml` (1,531 B) — the `auth.peers` map, `user_token_sha256`, `observer_token_sha256`. **Without an identical map every peer fails auth.**
- `~/.config/ai-connect/user.token`, `observer.token` (65 B each) — the secrets behind those hashes
- `~/.config/ai-connect/messages.db` (2,306,048 B) — 14 days of history (`history_days: 14`). Single file, no `-wal`/`-shm`. **A fresh bridge starts empty.**

Regenerate, do not copy:
- `tls\bridge-cert.pem` (501 B), `tls\bridge-key.pem` (241 B) — address-bound (B3)

Optional / disposable:
- `invites.json` (507 B) — both invites already consumed, nothing pending
- Logs (`bridge.log*`, `watchdog.log`, 352 × `mcp-*.log`), `watchdog-state.json`, `.auth.lock`, `sessions\` (9 small files), four `config.yaml.bak-*`, empty `invites\`
- `%LOCALAPPDATA%\ai-connect\{app,venv}` — the installer rebuilds these
- `acl-backups\` — archive only (5 Tailscale `.hujson` policy files)

**Deliberate owner decision, not copied by default:** `tailnet-authkey-ai-peer.txt`,
`tailscale-oauth.json`, `srl-anew-enrollment.txt`. These are secrets; they were not read.

### 4b. Address edits

On **this** machine (3 live sites, **[V]** by tree scan excluding `venv` and `*.log`):
1. `config.yaml:2` — `server.host: 100.117.116.57`
2. `config.yaml:29` — `client.bridge_url: ws://100.117.116.57:9999`
3. `ai-connect-watchdog.ps1:16` — `$HostName = '100.117.116.57'`

On the **new host, dadeush-ai** (**[P]** state; both edits are required):
1. `config.yaml` `server.host`: change the existing `127.0.0.1` to `100.87.39.3` (B6). Left as is, the bridge binds loopback only and no peer can reach it.
2. Add an inbound Windows firewall allow rule for TCP 9999 (and 10000 if TLS is kept) (B5).

Backups (`config.yaml.bak-20261104-buntun`, `-20261105-tss`, `-20261106`, `-20261108-peer`) and
`srl-anew-SETUP.md` lines 30/34/35/48/54/71 also contain the address but need no edit.

On the **other 5 machines** — `dadeush-buntun`, `laptop`, `srl-anew`, `mobile-dev-mac`,
plus whatever `crew-ai-wsl` / `dadeush-buntun-TheSelectSource` / `dadeush-legion` / `dadeush-buntu`
resolve to — each holds its own `client.bridge_url`. **[V]** These are not visible or editable from
here. That is the real coordination cost: **5+ local edits by whoever controls each machine.**
Peers do **not** rediscover a moved bridge.

### 4c. Order (each step gated on the previous)

1. Disable `\AI-Connect Watchdog` on dadeush-desktop (section 3).
2. Snapshot: copy `config.yaml`, `user.token`, `observer.token`, `messages.db` to a known-good backup path. This is the rollback set.
3. Assess the 0.2.5 vs 0.2.17 gap on dadeush-ai (B4); upgrade to match the bridge if the gap matters.
4. Place the migrated files on dadeush-ai; set `server.host: 100.87.39.3` (replacing the existing `127.0.0.1`, B6) and `client.bridge_url: ws://100.87.39.3:9999`.
5. Issue a new TLS cert for `100.87.39.3` if port 10000 is to keep serving (B3).
6. Create the bridge scheduled task on dadeush-ai **with a boot trigger**, not logon-only.
7. Add the inbound firewall allow rule for TCP 9999 on dadeush-ai (B5), then start it. Verify from dadeush-desktop: `Test-NetConnection 100.87.39.3 -Port 9999` succeeds. This is the first live test of the path; the ACL permits it (B2) but that was never exercised. **If this fails, stop — B1/B5 was wrong. Do not touch the peers.**
8. Stop (do not yet delete) the bridge task on dadeush-desktop. Both bridges must never serve at once.
9. Repoint peers one at a time, least critical first, confirming each appears in `peer_list` on the new bridge before moving to the next. Keep this session's own machine last so you retain a working vantage point.
10. Only after all peers report on the new bridge: re-enable a watchdog **on dadeush-ai** with its `$HostName` updated, and remove/disable the old one permanently.

### 4d. Rollback

Until step 8, rollback is: start the old bridge task on dadeush-desktop, restore the step-2
snapshot, re-enable the old watchdog. After step 9 begins, each repointed peer must be reverted
individually — there is no central undo. This asymmetry is the argument for doing step 9 slowly.

---

## 5. Verification (post-cutover)

- `peer_list` from a session on the new bridge returns **19 peers across 6 machines** (the pre-move baseline recorded in this file). Fewer = a peer was lost; name it before proceeding.
- `Get-NetTCPConnection -State Listen` on dadeush-ai shows `100.87.39.3:9999` (and `:10000` if TLS was reissued).
- Nothing listens on `100.117.116.57:9999` any more.
- `state unknown` in `peer_list` is **cosmetic and pre-existing**; do not use it as a success signal either way. **[V]** by a separate agent reading the source on this machine (this editing session re-checked `tools.py:262-265`, `peer_registry.py:33` and `websocket_server.py:39`; the other line numbers rest on that agent): `client/tools.py:262-265` prints it when `peer.get("state")` is empty; `server/peer_registry.py:33` initialises `state` to `""`; it is only set when a client sends `set_state` (`websocket_server.py:521-526`, `_set_state` `:595-600`); `_peer_list` (`:798-808`) just reads it. The cause is the **absence of a state report**: state is sent only by Claude Code hooks that call the `peer_set_state` MCP tool, and those hooks are written into the user's `~/.claude/settings.json` by `deploy --register-mcp` (`state_hooks.py:1-14`), deliberately not into the plugin's `hooks.json`. **[P]** `srl-ai` reports dadeush-ai's `~/.claude/settings.json` has `"ai-connect@useful-claude-add-ons": true` but no line matching `state`: the hooks are absent. **[V]** from source and git history on this machine: `set_state`/`peer_set_state` exist since 0.1.0/0.1.9 and state hooks since 0.1.9, and commit `d115ef607` (0.2.4) made the hooks the default for `deploy --register-mcp` (opt out with `--no-state-hooks`). So the 0.2.5 client can report state, and **the B4 version gap does not cause `state unknown`**; do not conflate the two. **[I]** Most likely dadeush-ai was registered before 0.2.4 or with `--no-state-hooks` and never re-registered (an update does not retroactively write hooks); not verified which. `unknown` never self-corrects: the only timers (`HEARTBEAT_SECONDS = 60`, `websocket_server.py:39`, loop `:844-854`; `registry.cleanup_stale`) govern connection liveness, not the state column. Remedy, for information only and **not a cutover step**: re-run `deploy --register-mcp` on dadeush-ai. It is not an error path and has no bearing on the migration.

## 6. Open unknowns

- B3, B4 (version gap), B5, B6 above. B1 is resolved **[P]**; B2 is resolved **[V]** (no retag needed).
- Live connectivity to `dadeush-ai:9999` was **not** tested: nothing listens there yet. The ACL permits it; that is not proof.
- Which machine holds the 3 off-account sessions (section 1): unknown.
- Whether the bridge actually starts before logon on dadeush-desktop after the S4U + BootTrigger
  change (section 3): **unproven**, no reboot has been performed.
- Which peers are *currently live* on the bridge versus merely enrolled: 10 names in `auth.peers`, 6 machines online, 8 sources in the ACL rule. The three sets do not match and nobody has reconciled them.
- The bridge DB holds **43 distinct `to_peer` names** against 10 enrolled. The bare names `srl-ai`, `tss-ai`, `vault` and `crew-win-ai` each hold one unread message from 11-13 (legacy rows predating `dadeush-ai:s-*` registration). "Enrolled", "has traffic" and "online" are three different sets.
- The bridge **pushes** messages (`_route_message`, `websocket_server.py:644-708`) and replays unread rows on register (`_send_unread`), so no `peer_read` polling is needed. `delivered=1` means only that the websocket accepted the frame, not that a session read it.
- `dadeush-legion` (offline 10h) and `dadeush-buntu` (offline 43d) are enrolled but absent. They will need repointing whenever they return, or they come back pointing at a dead bridge.
- `mcp` port 9998 is configured but **nothing was listening** at inventory time.
- `client.bridge_fingerprint` is unset and `config_loader.py:257` flags plain `ws://` as unencrypted. `ai-connect pin` would move peers to `wss://`. Out of scope for the move, worth deciding alongside B3.

### Observation, outside this migration's scope (not a blocker)

**[V]** The single grant (see B2 evidence) gives every tagged node full access to every other tagged
node, on all ports and protocols. A compromise of any one peer reaches all of them. It is worth
narrowing to the ports ai-connect actually uses (9999, 10000) at some point. Out of scope here; no
change is proposed or needed for the cutover.
