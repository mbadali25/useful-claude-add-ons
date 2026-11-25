# ai-connect bridge migration runbook — dadeush-desktop → dadeush-ai

**Status: PLAN ONLY. Nothing has been executed. Nothing has been changed.**
Written 2026-11-25. Author: useful-claude-add-ons session (`dadeush-desktop:s-useful-claude-add-ons-43`).

Every line below is marked **[V]** verified in-session (with the command or path that proved it)
or **[I]** inferred. Do not execute a step that depends on an **[I]** line until it is verified.

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
| `here → dadeush-ai:9999` | **COULD NOT TELL** — that rule lives in dadeush-ai's own netmap |

### The 3 "off-account" sessions
The owner reported 3 sessions not on this account. **[V]** There are **no cross-account Tailscale
peers** — every node is in tailnet `mbadali25.github`, the only human owner is `mbadali25@github`
(`dadeush-buntun`), and all others are tagged devices, which have no human owner by design.
**[I]** The split is therefore a *Claude account* split (memory names `badalim@anewbiz.net`), not a
VPN one. `dadeush-ai` has exactly 3 sessions (`srl-ai`, `tss-ai`, `vault`) and they are the only
peers reporting `state unknown` while every other peer reports busy/idle/waiting with a timestamp —
consistent with them being those 3, but **not verified**. `peer_list` carries no account field.

**This means: there is nothing to migrate on the Tailscale side for the account split.** Retagging
or re-signing-in will not change which Claude account a session runs under.

---

## 2. Blockers that must clear before any cutover

| # | Blocker | Who | Why it blocks |
|---|---|---|---|
| B1 | Prove `100.117.116.57 → 100.87.39.3:9999` is allowed | dadeush-ai (`tailscale debug netmap`) — **asked, reply pending** | Every peer must reach the new bridge. Unproven = all 19 peers drop. |
| B2 | Tailnet policy may key the bridge rule on `tag:bridge`; `dadeush-ai` holds `tag:ai-peer` | **Owner only**, Tailscale admin console | An agent cannot and must not edit the policy file. Retag or widen before cutover. |
| B3 | TLS cert `tls\bridge-cert.pem` is bound to `100.117.116.57` | Owner decision | Peers using `wss://…:10000` (srl-anew documented) break until a new cert is issued. |
| B4 | Is ai-connect even installed on dadeush-ai, and what version | dadeush-ai — **asked, reply pending** | A 0.1.x or absent install changes the whole procedure. |
| B5 | Windows firewall inbound TCP 9999 on dadeush-ai | dadeush-ai — **asked, reply pending** | Tailnet ACL can allow it while the host firewall drops it. |

**Do not begin section 4 until B1, B2 and B4 are resolved.**

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

Second hazard: the bridge scheduled task `\AI-Connect Bridge` uses a **LogonTrigger only — no boot
trigger** **[V]** `schtasks /query /tn "AI-Connect Bridge" /xml`, running as
`DADEUSH-DESKTOP\d3ade` with InteractiveToken. Replicated as-is on `dadeush-ai`, the bridge starts
only when that user interactively logs in. On a headless box that is an availability regression; add
a boot trigger or run it as a service there.

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
3. Confirm ai-connect is installed on dadeush-ai at a matching version (B4); install/upgrade if not.
4. Place the migrated files on dadeush-ai; set `server.host: 100.87.39.3`, `client.bridge_url: ws://100.87.39.3:9999`.
5. Issue a new TLS cert for `100.87.39.3` if port 10000 is to keep serving (B3).
6. Create the bridge scheduled task on dadeush-ai **with a boot trigger**, not logon-only.
7. Start it. Verify from dadeush-desktop: `Test-NetConnection 100.87.39.3 -Port 9999` succeeds. **If this fails, stop — B1/B5 was wrong. Do not touch the peers.**
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
- The 3 `dadeush-ai` sessions' `state unknown` is **a pre-existing condition, not caused by the move** — do not use it as a success signal either way. Its cause is still unknown (B4 query pending).

## 6. Open unknowns

- B1, B2, B3, B4, B5 above.
- Which peers are *currently live* on the bridge versus merely enrolled: 10 names in `auth.peers`, 6 machines online, 8 sources in the ACL rule. The three sets do not match and nobody has reconciled them.
- `dadeush-legion` (offline 10h) and `dadeush-buntu` (offline 43d) are enrolled but absent. They will need repointing whenever they return, or they come back pointing at a dead bridge.
- `mcp` port 9998 is configured but **nothing was listening** at inventory time.
- `client.bridge_fingerprint` is unset and `config_loader.py:257` flags plain `ws://` as unencrypted. `ai-connect pin` would move peers to `wss://`. Out of scope for the move, worth deciding alongside B3.
