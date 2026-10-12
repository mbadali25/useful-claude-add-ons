# Changelog

## [0.1.6] - 2026-10-11

One-command deployment over Tailscale, onboarding in three commands, and the peer-deploy fixes from crew's
review (W-0129). The deployment was numbered 0.1.5 on its branch and never published under that number:
the 0.1.5 below is L-0790's test fix, which reached main first.

### Added
- `deploy invite --name N`: a single-use, non-ephemeral, pre-approved `tag:ai-peer` join key as one `aic1.` invite code, written owner-only (`--out`) or shown once
- `deploy join --invite-file F` (or `--invite` at a hidden prompt, or `--name N --bridge H` for a browser login): preflight, Tailscale installed and joined with the pinned flags, the machine's own token (0600, its directory 0700), the client config, the enrolment hash, and a VPN / port / token summary where an unapproved token is PENDING
- `deploy approve --name N [--token-sha256 H]`: add-peer, the Bridge restart, and the node's key expiry turned off through the API
- `deploy remove --name N --yes`: the node off the tailnet, the peer out of the Bridge, the Bridge restarted
- `deploy list`: every tailnet node (IP, tags, online, key expiry) beside the Bridge's peers, naming any key that still expires
- `deploy/ONBOARDING.md`: add, remove and rotate a machine, troubleshooting, VPN coexistence

### Changed
- `vpn/mint-key` mints non-ephemeral keys by default; `--ephemeral` opts in, for throwaway and CI nodes
- `deploy peer` and `deploy join` install no plugin hooks and register no MCP server unless asked (`--install-hooks` / `--with-hooks`, `--register-mcp [--scope project|user]`), each with a bypass-permissions warning
- `--dry-run` runs no tool at all and needs no token or key file; `status` runs nothing through `sudo` and no `claude` command
- The apt install falls back to Tailscale's install script only when the repository does not carry the release; a held dpkg lock or no network stops instead
- What keeps running is installed outside the checkout: the venv and a copy of the plugin in `~/.local/share/ai-connect` (Windows `%LOCALAPPDATA%\ai-connect`); a rerun from a newer checkout updates the copy and restarts the Bridge, and a scheduled task left pointing elsewhere is registered again
- `deploy bridge` and `tailnet-setup` turn the Bridge's own node key expiry off; `deploy status` flags a node key that still expires

### Added (the deployment)
- `deploy/deploy.sh` and `deploy/deploy.ps1`, one core (`deploy/deploy.py`): `bridge`, `peer`, `add-peer`, `status`, `uninstall`, `tailnet-setup` and `test`. Every step is idempotent, `--dry-run` prints each change and command and makes none, and no secret is printed or put on a command line. Runbook: `deploy/README.md`
- `deploy tailnet-setup` (admin, once per tailnet), through the Tailscale API with a one-time access token: validates `vpn/acl-template.hujson`, shows a diff against the current policy, and with `--apply` backs the policy up, replaces it (`If-Match`), tags the Bridge machine `tag:bridge` and creates the OAuth client `mint-key` and `revoke` use (`POST /tailnet/-/keys`, `keyType: "client"`). The client goes to the OS credential store through `keyring`, or to an owner-only file without it; when the API refuses, the admin-console steps are printed. Never waits without a terminal: `--yes`, the token from `TS_API_TOKEN` or the credential store, `--json` for one JSON object with no secret in it
- Enrolment by hash: `deploy peer --print-enrolment` makes the peer's own token and prints `{name, token_sha256}`; `deploy add-peer --name N --token-sha256 HEX` lets it in on the Bridge. No long-lived secret crosses machines
- `deploy bridge`, `peer` and `tailnet-setup` install Tailscale when it is missing: Tailscale's apt repository with a `signed-by` keyring on Debian and Ubuntu, its install script elsewhere on Linux, `winget` or the MSI on Windows, Homebrew on macOS. Every command is printed first; as root nothing goes through `sudo`
- `deploy test --bridge HOST --name N`: Tailscale up, the Bridge's port, this machine's token, a message round trip inside the untrusted frame, a wrong token refused. A PASS/FAIL table, exit code 1 on any FAIL
- `server.max_unread_per_peer` and `server.max_unread_bytes_per_peer` in `config.yaml` (the offline queue caps)
- A CI workflow that runs the plugin's suites; until now no workflow did

### Changed (the deployment)
- `tailscale up` (`vpn/vpn-up` and deploy) passes `--accept-dns=false`: Tailscale no longer takes over the machine's DNS unless `--accept-dns` is given, because MagicDNS collides with a VPN client or DNS hook that is already there. Reach the Bridge by its `100.x.y.z` address
- `vpn/tsadmin.py` also finds the `tailscale` command in the directory a fresh install uses, before a new shell has it on `PATH`, and reads the OAuth client as a whole pair from one source: the environment, the credential store, then `~/.config/ai-connect/tailscale-oauth.json`

### Fixed
- A `history` request with a `limit` that is not a whole number from 1 to the maximum is refused (`invalid_limit`) instead of reaching the store
- `README_DE.md` is back in step with `README.md`; a test compares their section outlines

### Known limitations
- Nothing in `deploy/` has run against a real tailnet: the suites use a fake Tailscale API, fake system tools and a fake credential store. The `winget` package ID and the Homebrew cask name are the documented ones, untested
- A Bridge on macOS is refused (no launchd service); a peer there works
- firewalld keeps the old rule when `--vpn-subnet` is narrowed on a rerun; ufw and Windows Firewall replace it. A Windows rule is compared by subnet and port only
- `deploy.ps1` does not raise its own UAC prompt: `bridge` and `uninstall` need an elevated shell

## [0.1.5] - 2026-10-11

A test-only fix (L-0790). Nothing the plugin installs or runs changes. Verified on Linux as a non-root user; not run on Windows.

### Fixed
- `tests/test_ops_firewall.py` could run the host's real `sudo ufw allow` (or `firewall-cmd --add-rich-rule`): it put its fake tools in front of the caller's whole `PATH`, and its fake `sudo` ran whatever that `PATH` resolved. Run as root, or by a user with passwordless sudo, on a host with ufw, the suite added the bridge's allow rule to the real firewall configuration. The child now gets a `PATH` of two directories the test creates (the fakes, and wrappers for `grep` and `cat`), the fake `sudo` runs only a file inside the fake directory and refuses anything else, and the harness sets the euid the function sees (a normal user unless the test says otherwise) instead of inheriting the caller's. Every child also checks, before the code under test, that `sudo`, `ufw` and `firewall-cmd` resolve to a fake or to nothing, and stops if not
- New tests fail if the harness can reach a real `ufw`, `firewall-cmd` or `sudo` again, using canary tools planted on the caller's `PATH`, so they do not depend on what the host has installed
- The module skips, with the reason, when the real euid is 0 unless `AI_CONNECT_TEST_ALLOW_ROOT=1` says the caller is sandboxed, and when `bash` is Windows' WSL launcher (`System32\bash.exe`), whose shell takes neither the test's `PATH` nor its fakes

### If you ran the suite before 0.1.5
- As root or with passwordless sudo on a Linux or WSL host with ufw or firewalld: check for a rule allowing TCP 9999 from `100.64.0.0/10` that you did not add (ufw's carries the comment `AI-Connect Bridge`; firewalld's rich rule has no comment) (`sudo ufw status`, or `sudo firewall-cmd --permanent --list-rich-rules`), and delete it if the bridge is not meant to listen there

## [0.1.4] - 2026-10-11

Fixes from a Codex QA pass over the whole fork (W-0121). 0.1.2 and 0.1.3 were set on the branch and never released: the PR's CI found the first three items after them.

### Fixed
- `vpn/tsadmin.py` resolves `icacls` and `taskkill` with `shutil.which` instead of running bare names; a missing `icacls` fails `mint-key --out` closed, and the shim tests give every `pwsh` they spawn its own `XDG_CACHE_HOME`
- `vpn/` `.ps1` shims are self-contained instead of dot-sourcing `_common.ps1` (removed), which the repo's PowerShell static check cannot follow; each shim's test runs that check
- `install.ps1`'s firewall and scheduled-task cmdlets (NetSecurity, NetTCPIP, ScheduledTasks) are exempted in `scripts/check-powershell.ps1`, the firewall names scoped to this one file
- Untrusted framing: the warning in front of a peer's message is constant. The sender's name is peer-controlled, so it appears only inside the block (its start marker), in `peer_read`, `peer_history` and the watcher's wake notice
- Client inbound queue: capped at 500 messages and 8 MiB. Past either cap newer messages are not queued, and one notice points at `peer_history` for missed direct messages
- Refused sends: a coded error frame from the Bridge (`recipient_queue_full`, `message_too_large`, `rate_limited`, ...) is queued as a notice for `peer_read` instead of only logged. `peer_send`/`peer_context` refuse a frame over the Bridge's limit (`AI_CONNECT_MAX_MESSAGE_BYTES`, default 64 KiB) before sending it, and the default file cap drops from 256 KiB, which could never be sent, to 48 KiB
- IPv6: the MCP client brackets an IPv6 `bridge_url` host (`ws://[::1]:9999`) like the watcher does
- Concurrent `peer_history`/`peer_list` requests of one type run one at a time, and each carries a `request_id` the Bridge echoes, so neither a concurrent nor a late answer to a timed-out request reaches the wrong caller (an answer without one, from an older Bridge, is still matched by type)
- Bridge: a direct message to a registered peer is marked delivered only once its send returns; a holder whose socket had closed gets it as unread on its next register. A holder whose socket is already closed counts as offline, so the unread caps apply, and a registration replay skips a message that is being sent live, so it arrives once; if that send fails because a reconnect replaced the holder meanwhile, the new holder gets it at once
- Bridge: `notify_when_idle` takes a string peer only, a peer may hold at most 32 subscriptions (`too_many_subscriptions`), and they end when the subscriber's name leaves the registry (a same-credential reconnect that replaces a dead holder keeps them)
- Installer, POSIX: `config.yaml`, `observer.token` and `user.token` are written to a 0600 temp file and moved into place, in a 0700 directory, so a secret is never readable by others, even briefly. On Windows the files inherit the config directory's ACL, as before

### Known limitations
- A send is reported as sent once the Bridge has the frame. A later refusal (`recipient_queue_full`, `rate_limited`) reaches the model as a notice in the next `peer_read`, not as the tool's result, and that notice is itself dropped while the inbound queue is full
- `peer_history` reads one conversation, so a broadcast missed while the inbound queue was full is not in it
- `vpn/` `mint-key --out` on Windows fails closed, writing nothing, when `icacls` cannot restrict the key file or `USERNAME` is unset

## [0.1.1] - 2026-10-11

Marketplace plugin version 0.1.1; the plugin's 0.1.0 shipped upstream 2.3.0-hardened. Two review-fix rounds and the VPN tooling.

### Fixed
- File sharing: `_read_shareable` opens the file first (`O_NOFOLLOW` where it exists) and decides on the handle: a regular file, its final path (`GetFinalPathNameByHandleW`, `/proc/self/fd`, `F_GETPATH`) inside the project, at most the cap read. A file or ancestor swapped for a symlink or junction after the name check is refused; a platform that cannot name the handle refuses
- `peer_list`: every peer-set field (name, state, detail, status) goes inside one untrusted block, one escaped line per peer
- `peer_read` / `peer_history`: the sender and time header is the first line inside each message's untrusted block, not a line above it
- Malformed peer fields (a non-dict context, non-string content or sender, a bad timestamp) render escaped instead of raising; `peer_read` peeks, renders, then drops, so a render failure no longer loses the queue
- `PeerRegistry.register` inserts the new holder before closing the dead one, with no await between check and insert, so two connections can no longer be authorised under one name
- Peers may send to `User:<name>` again (the documented reply path); registering or watching a user name stays refused
- Offline delivery: each recipient's unread queue is capped (`max_unread_per_peer` 500, `max_unread_bytes_per_peer` 8 MiB) and a send past it is refused with `recipient_queue_full`; unread messages go out in frames of at most 1 MiB, each marked delivered only after its send returns
- `observer_client.cli send` prints the Bridge's error for a refused recipient and exits 1, instead of "waits until it is online"

### Added
- `vpn/`: Tailscale self-join tooling. `mint-key` (one single-use, ephemeral, pre-authorised `tag:ai-peer` key via an OAuth client), `revoke`, `vpn-up` (idempotent join, userspace fallback with a SOCKS5 proxy), `vpn-down`; one stdlib `tsadmin.py` behind `.sh`/`.ps1` shims, and an ACL template allowing `tag:ai-peer` to reach `tag:bridge:9999` only. See [vpn/README.md](vpn/README.md)
- `mint-key --peer-token` runs `installer.py add-peer <name>` with the venv beside the installer (`venv/bin/python` or `venv\Scripts\python.exe`), falling back to the running Python

## [2.3.0-hardened] - 2026-10-11

Security hardening across server, client and ops. Updating from 2.2: config keys move (see below); `install.sh`/`install.ps1` or `installer.py config` migrate `bridge.*` automatically, with a deprecation warning, and write the new `client:` section and per-peer tokens.

### Added
- Per-peer tokens: `auth.peers` maps `{name: sha256(token)}`, so a token can only register and watch its own name (constant-time match against every entry). The old shared `auth.token` still works, but only with `auth.allow_shared_token: true`, logs a warning on every use, and can never take a bound name. `installer.py add-peer`/`revoke-peer` generate a 256-bit token per peer and print it once; the example's own placeholder token is rejected wherever it would otherwise be trusted
- Name-takeover block: a live registered name can no longer be taken over by another connection (refused with `name_taken`); standby still works, and a dead holder's name is freed for the same credential
- `Bridge` and `User` are reserved (case-insensitive) as register, watch and message-target names
- Observer restriction: the observer token (`bridge.observer_token_sha256`) may only read (`observe`, `history_all`, `list_peers`, `ping`) — it cannot register, send or hold a name
- Limits: max message size (64 KiB), a per-connection rate limit (10/s, with burst), and a per-sender cap on stored messages; a refusal sends an error frame with a code and logs one structured JSON line without the token or body
- Untrusted framing: peer text, names and excerpts shown to Claude Code are wrapped in a block with a random-id delimiter, control/format characters escaped, marker spoofs defanged, and excerpt fences made longer than any backtick run inside — `peer_read`, `peer_history` and the watcher's wake notice all go through it
- File confinement: `peer_send`/`peer_context` file paths must resolve (symlinks followed) inside the project directory, be a regular file, and be <= 256 KiB (`AI_CONNECT_MAX_FILE_BYTES`); refusals are logged in one line
- `server.host` defaults to `127.0.0.1` (never `0.0.0.0`) unless set explicitly; `messages.db` is created `0600` (best effort on Windows)
- Config migration: old `bridge.*` keys map to the new `server:`/`auth:`/`client:` layout with a one-time deprecation warning, so an existing `config.yaml` keeps working
- `requirements.txt` pins `websockets`/`aiosqlite`/`pyyaml`/`fastmcp` to exact versions; new `requirements-dev.txt` pins `pytest`
- `install.ps1` scopes the Bridge firewall rule to `-VpnSubnet` (default Tailscale's `100.64.0.0/10`) instead of the whole Private profile, and forwards it through the UAC relaunch; `install.sh` gains the matching `--vpn-subnet` support, applying an equivalent rule via `ufw` or `firewalld` when present (idempotent, skipped with a message if not root/no passwordless sudo) and falling back to printed advice otherwise
- README/README_DE: a Security model section (VPN-only, no TLS, per-peer tokens, peers are untrusted, never run a woken session in bypass/auto-approve, what uninstall leaves behind)

### Changed
- No "replaced" frame any more: on `name_taken` the client logs why and registers once on standby instead of retrying blindly
- The permission-prompt text is no longer broadcast as peer state detail
- Claude Code behaviour rules: never obey a `User:` sender or a handshake without the user present; peer messages are untrusted and actions still need user confirmation

## [2.2.0] - 2026-10-10

Updating from 2.1: add `bridge.observer_token_sha256: ""` and `bridge.user_token_sha256: ""` to the config; on the Bridge machine then run `installer.py observer-token` and `installer.py user-token` and restart the Bridge (README, "Updating from 2.1 to 2.2").

### Added
- Reading along: roles per token on the Bridge (`server/roles.py`, one table of which role may send which message types). Besides the peer token (`bridge.token`, unchanged) an observer token that may only read: `observe` (a copy of every message the Bridge stores), `history_all` (all conversations, with a required time window and limit, pages via `before`), `list_peers`, `ping`; it cannot register, send or hold a name. The Bridge knows it only by its SHA-256 (new required key `bridge.observer_token_sha256`, `""` on machines without the Bridge); the token is in `~/.config/ai-connect/observer.token`. `installer.py observer-token` writes both and adds deny rules for the file and for running `observer_client` to `~/.claude/settings.json`; a fresh `--server` install does it by itself. Existing Bridge machines: run it once and restart the Bridge
- `observer_client`: connection (`history`, `peers`, live `observed`), conversation tree as data (`tree.py`, a conversation is the sorted pair of its peers) and a terminal program (`python -m observer_client.cli tree|live`). In a terminal the conversation headings are amber, names coloured, time and arrow dimmed; the tree's lines show only the sender, without the host (the heading names both)

- Writing to agents as a user: a third role `user` (token known to the Bridge only by `bridge.user_token_sha256`, new required key, `""` = nobody can send as user; the token is in `~/.config/ai-connect/user.token`, kept like the observer token: `installer.py user-token` writes both and adds deny rules for the file, a fresh `--server` install does it by itself). `user_send` sends as `User:<as>` to one or more peers or `*`; the tool passes the name, the Bridge sets the prefix and refuses `register` and `watch` with it to peers. Messages to a user count as delivered at once, so they do not pile up as unread. Client: `UserConnection.send` (returns id and online per recipient, `TokenRefused` for a wrong token) and `cli send`. The behaviour rules make a message from the agent's own user an instruction, from any other user information, without a handshake
- JSON lines for programs with their own Python environment (Agent-Orc), started as a process with the AI-Connect venv: `observer_client.jsonl observe` (peers, past messages, `history_end`, then live events until ended; errors as a last line with exit code 1) and `observer_client.jsonl send` (request with the token on stdin, never in the arguments). The Bridge pushes the peer list to observers whenever a peer joins or leaves; the live iterator is `events()` (messages and peer lists)
- `AI_CONNECT_PEER_SUFFIX`: the STDIO client joins as `Host:Project-Suffix`, so a second session in the same project (e.g. a reviewer started by Agent-Orc) is reachable under its own name instead of pushing the first onto standby. `AI_CONNECT_PEER_NAME` still takes precedence

### Changed
- A connection may send only the message types of its role; anything else gets an error instead of being ignored. A `message` without `to` gets an error instead of being dropped with a log line
- `bridge_time.py`: the Bridge timestamp format in one place (store, MCP tools, watcher, observer)

## [2.1.0] - 2026-10-04

### Changed
- The watcher starts by itself: the plugin runs it as an `asyncRewake` hook at session start and after every turn, and its exit wakes the session. Sessions no longer start and restart it (the rule and the 110-minute limit are gone). One watcher per session (the Bridge turns away a second), a message that arrived while no watcher ran is reported at once (`peer_read` records the read state), and it reconnects after a Bridge restart. The watcher hooks set a 7-day timeout: Claude Code ends asyncRewake hooks after its default 600 s otherwise, which left idle sessions deaf after ten minutes

### Fixed
- A watcher outlived its session (Windows does not end the process tree of hooks, and the VS Code extension briefly starts a second session); it now checks every 30 s whether its session still runs and ends otherwise. At start the client removes the name and read-state files of sessions that no longer run
- `peer_read` during standby says so and to try again in a few seconds, instead of "Not connected"

## [2.0.0] - 2026-10-04

### Added
- Release workflow: a tag `v*` builds a GitHub release with two downloads from the same code, `AI-Connect-<tag>-linux.tar.gz` and `AI-Connect-<tag>-windows.zip` (CRLF for `.cmd`/`.ps1`, without developer files such as `.github/`)
- Claude Code plugin `ai-connect@ai-connect` (`integrations/claude-code/plugin/`, the repository is its local marketplace) with the state hooks. It does not ship the MCP server, whose Python path differs between Linux and Windows; the installer registers that
- `peer_name.py`: one naming rule for the STDIO client and the watcher (project from `CLAUDE_PROJECT_DIR` when Claude Code sets it). The client records its name per session (`~/.config/ai-connect/sessions/<pid>`), the watcher looks it up by `CLAUDE_PID`, so it no longer reads `/proc` and works on Windows too
- `installer.py`: the platform-independent installation steps (write and check the config, generate or ask for the token, register MCP server and plugin with Claude Code, remove them again), used by `install.sh` and the Windows installer
- Peer state and status line: `peer_set_status` (one line on the current work) and `peer_set_state` (busy / idle / waiting, reported by hooks; for Claude Code `mcp_tool` hooks on UserPromptSubmit, PostToolUse, Notification and Stop); `peer_list` shows both. `peer_notify_when_idle` asks the Bridge for one message as soon as a peer is done or waits for an approval, across machines. The client resends state and status after every reconnect
- Bridge token: the Bridge refuses every connection whose handshake lacks `Authorization: Bearer <bridge.token>` (clients, HTTP/SSE server and watcher send it). `install.sh` generates the token on the Bridge machine and asks for it on clients. New required key `bridge.token`; a refused client stops reconnecting and `peer_status` says why
- The Bridge deletes messages older than `bridge.history_days` from the history, at start and then daily. New required config keys `bridge.history_days` and `logging.*`: add them to existing configs (see `config.yaml.example`)
- The rules make every Claude Code session keep its watcher running from the start, so messages wake the recipient without the user prompting it; the tool descriptions carry the exact watcher command of the installation
- `requirements.txt` as the single list of dependencies; `install.sh` installs from it (`aiosqlite` was missing, the Bridge crashed on fresh machines)
- `config_loader.py`: one config loader for the Bridge and both MCP clients

### Changed
- No blocking wait any more: the `/ai-connect:consult` command and the `peer_wait` tool are removed. Sessions send, end their turn and are woken by the watcher; `peer_notify_when_idle` tells them when a partner is done. The "second opinion" guidance moved into the behaviour rules
- Windows installer `install.cmd` / `install.ps1`, tested on Windows 11 (client and server): the same modes as `install.sh`; services as scheduled tasks (start at logon, no console window, restart on failure, as the user); tasks and the firewall rule for port 9999 (private networks only) need administrator rights, so the script restarts itself elevated through UAC. Clients on the Bridge machine connect to 127.0.0.1 when `bridge.host` is 0.0.0.0, which Windows refuses as a target
- The watcher's "no peer name" error says to restart the session (or reconnect `ai-connect` in `/mcp`) after an update, because the running MCP client records its name only at start
- `install.sh` reworked: `--client` installs venv, config and the Claude Code registration only, with no service and no sudo; `--server` adds the Bridge service; `--http` adds the HTTP/SSE service for other MCP clients (was installed on every machine)
- The Bridge also logs to a rotated `bridge.log`, and it stops on SIGTERM/SIGINT through `signal.signal`, which Windows supports too
- The watcher command in the tool descriptions is quoted with forward slashes, so it runs in the Git Bash that Claude Code uses on Windows
- A missing config file or key stops every service with a message; the silent defaults (including a hard-coded Bridge IP) are gone
- Code, log messages, tool descriptions and `install.sh` are in English; `install.sh` writes the PolicyKit rule for the installing user instead of a fixed one, asks clients for the Bridge address and suggests `0.0.0.0` as the Bridge's listen address (`127.0.0.1` locked out every other machine); it ends with the ready `claude mcp add` line
- `/beratung` renamed to `/consult` and rewritten in English, as are the Claude Code rules and the integration README; tag `[WEITER]` is now `[CONTINUE]`
- README (EN/DE) rewritten: setup via `install.sh`, Claude Code via the STDIO client, current architecture diagram, corrected heartbeat timings
- README (EN/DE): AI-Connect works across people, accounts and subscriptions; comparison with Claude Code's built-in cross-session messaging; security note (no authentication or encryption: LAN or VPN only); the limitation "no way to signal a running session from outside" is outdated since Claude Code's per-session inbox socket
- Logs of the MCP clients are rotated by size (`logging.max_megabytes`, `logging.backup_count`); each STDIO client writes its own `mcp-<Host>_<Project>.log` instead of all sessions sharing `mcp.log` (a rotated file must have a single writer, and the shared file did not show which session wrote a line)

### Fixed
- On Windows the watcher crashed on characters outside the ANSI code page (an arrow, an emoji), and umlauts arrived garbled; watcher output, log files, config and session files now use UTF-8
- `install.sh --update` installed the newest fastmcp (4.0.10), which broke `ai-connect-mcp.service` (ImportError); `requirements.txt` pins `fastmcp>=2.14,<3`
- A session replaced by a newer one with the same name stayed offline for good, even after the newer one had left (2026-10-04: a short second instance of the archimedes-lander session left the running one unreachable); it now waits on standby (`register` with `standby`, Bridge answers `standby` and later `name_free`) and takes the name back. Both sessions get a notice from `Bridge`
- The watcher read the Bridge's database file and therefore worked on the Bridge machine only; it now asks the Bridge over the network (`watch`, no registration) and works on every machine, pushed instead of polling every 5 s
- `peer_send` with a file and `peer_context` sent only the path and line numbers; the file content (or the given lines) now travels with the message
- `peer_history` showed only the local, already emptied queue; it now asks the Bridge
- A broadcast to offline peers was handed to whichever peer came online first and marked delivered (possibly back to its sender); broadcasts now reach the peers online at that moment
- A client that could not reach the Bridge at start never retried; it now reconnects in the background
- The Bridge refreshed a peer's heartbeat whenever it sent to it, so silent peers never timed out; only the peer's own pings count now
- `register` without a name is rejected instead of registering `None`
- The HTTP/SSE server had its own copy of every tool and lacked `peer_wait`; both servers now share `client/mcp_app.py`

### Removed
- `chat_viewer.py`: it registered as an ordinary peer and therefore never saw the messages it promised to show
- `peer.auto_connect`: with `false` the client stayed disconnected for good
- The "Salomo Principle" (AIfred/Sokrates/Salomo roles, 2/3 voting) from docs and command: nothing in AI-Connect implemented it
- `pyproject.toml`: unused, its entry point named a module that does not exist

## [Unreleased] - 2026-09-28

### Added
- `integrations/claude-code/aiconnect_watch.py`: message watcher that wakes a Claude Code session via a finished background task instead of polling
- Waiting rules in `integrations/claude-code/CLAUDE.md` and in the `peer_read`/`peer_wait` tool descriptions

### Changed
- `aiconnect_watch.py` takes the peer name from the session's MCP client instead of the shell's current directory, prints it at start and exits with an error when it cannot tell (a watcher started from a worktree listened for the wrong name)
- A second session with the same peer name takes over; the Bridge sends the older one `replaced` and it stops reconnecting (was: the two pushed each other out every ~27 s)
- Docs: peer names are `Host:Project`; `/advisor` skill replaced by the `/beratung` command (now `/consult`)

### Fixed
- Duplicate entries in the client's peer list after re-registrations
- The client noticed a clean close by the Bridge only at the next ping (25 s)
- ruff/mypy findings in client and server

## [1.0.0] - 2025-01-03

### Added
- Multi-agent communication via MCP bridge
- SSE transport for stable Claude Code connections
- Salomo Principle for multi-agent consensus (AIfred/Sokrates/Salomo)
- `/advisor` skill for polling mode
- Offline message storage with SQLite
- Project-based peer names (e.g., "Aragon (myproject)")
- Unique client IDs with PID suffix for multiple instances
- Install script with server/client modes
- English and German documentation

### Architecture
- Bridge Server (WebSocket, port 9999) - routes messages between peers
- MCP HTTP Server (SSE, port 9998) - local interface for Claude Code
- Persistent WebSocket connections with heartbeat
