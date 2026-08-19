---
name: obsidian-vault-server
description: >
  Run a self-hosted Obsidian vault on a headless Ubuntu server - the real Obsidian
  desktop app in a container, signed in to an obsidian.md account and syncing, with
  the Local REST API plugin's built-in MCP endpoint exposed to Claude over an SSH
  tunnel. Covers install, Docker Compose recovery, GUI basic auth, ufw lockdown,
  the API key, replicating a workstation's plugin set onto the server, and the
  failure modes that look like something else. Use this skill whenever the user
  mentions a self-hosted or server-side Obsidian vault, Obsidian Sync on a server,
  running Obsidian headless or in Docker, linuxserver/obsidian, KasmVNC, the
  obsidian-local-rest-api plugin, or connecting Claude to a vault over MCP - even
  if they never say "server". Also use it for the symptoms: "This application
  requires a secure connection (HTTPS)" from an Obsidian web UI, "docker compose
  plugin not found" during an Obsidian install, an Obsidian MCP endpoint that
  will not answer on 27123/27124, an Obsidian API key that regenerated and broke
  Claude, or "how do I get my plugins onto the server vault".
---

# Obsidian vault server

Runs Obsidian on a headless Ubuntu host and gives Claude read/write access to the
vault over MCP.

Two facts shape everything else:

- **Obsidian Sync has no headless client.** Sync is a feature of the Electron
  desktop app. No CLI, no daemon, no sign-in API. The only way to run it on a
  server is to run the real desktop app against a virtual display and reach it
  through a browser — `lscr.io/linuxserver/obsidian` (KasmVNC).
- **No separate MCP server process is needed.** The `obsidian-local-rest-api`
  plugin ships a built-in MCP endpoint at `/mcp/`. Claude speaks streamable HTTP
  straight to the plugin.

## Not to be confused with

| If the user wants | Use |
|---|---|
| A vault on a **server**, reachable by Claude over MCP | This skill |
| A **local** vault on the workstation, wired into Claude | `claude-obsidian-setup/` in this repo |
| Reading or writing notes in a vault already connected | The `obsidian` MCP tools directly — no skill needed |
| The `claude-obsidian` product (transactional writes, provenance ledgers) | `claude-obsidian-setup/`, which installs it |

## Quick start

Read [`references/server-install.md`](references/server-install.md) before running
anything. The short version:

```bash
# on the Ubuntu host
sudo ./obsidian-vault-server.sh install     # docker, vault, plugin, container
sudo ./obsidian-vault-server.sh lockdown    # firewall the GUI - do not skip
sudo ./obsidian-vault-server.sh gui-password
```

Then sign in through the GUI (this part cannot be scripted) and finish:

```bash
sudo ./obsidian-vault-server.sh finalize    # reads the API key, enables MCP
```

### Reaching the GUI

`http://<ip>:3000` **will not work.** It loads and then refuses with *"This
application requires a secure connection (HTTPS)"* — KasmVNC uses WebCodecs, which
browsers gate behind a secure context, and LinuxServer's port table says 3000 "must
be proxied". Use one of:

```bash
ssh -N -L 3000:127.0.0.1:3000 user@server   # then http://127.0.0.1:3000
```

`localhost` counts as a secure context even over plain HTTP. Or hit
`https://<ip>:3001` and accept the self-signed certificate.

## Reference map

| Task | Read |
|---|---|
| Install, paths, env overrides, Docker Compose fallbacks, lockdown | [`references/server-install.md`](references/server-install.md) |
| Wiring Claude Code / Claude Desktop, the API key, TLS choice | [`references/mcp-connection.md`](references/mcp-connection.md) |
| Getting a workstation's plugins and settings onto the server | [`references/profile-replication.md`](references/profile-replication.md) |

## Common tasks

**"Connect Claude to my vault server."** Get the key with `obsidian-vault-server.sh
apikey`. Open a tunnel, then register:

```bash
ssh -N -L 27123:127.0.0.1:27123 user@server
claude mcp add --transport http obsidian-server http://127.0.0.1:27123/mcp/ \
  --header "Authorization: Bearer <api-key>"
```

Use plain HTTP on 27123 through the tunnel, not HTTPS on 27124 — the plugin's
certificate is self-signed and most MCP clients reject it. SSH provides the
encryption. Details in `references/mcp-connection.md`.

**"The install failed with `docker compose plugin not found`."** Docker came from
Ubuntu's `docker.io` package, which ships no Compose plugin, so the installer's
`get.docker.com` step was skipped. Current versions install Compose themselves
through four fallbacks. If it still fails, the host almost certainly has Docker
from **snap**, which does not load CLI plugins from
`/usr/local/lib/docker/cli-plugins`; remove the snap and install from the official
repo.

**"Claude says the MCP server failed."** Order of operations. The tunnel must be up
before Claude resolves the server. Bring the tunnel up, then
`claude mcp remove obsidian-server` and re-add.

**"Put my laptop's plugins on the server."** Export a profile on the workstation,
copy it over, apply it. Never copy `.obsidian` wholesale and never let Sync carry
plugins — both move the REST API key. See `references/profile-replication.md`.

## Safety rails

- **The GUI is a root shell.** LinuxServer: *"The web interface includes a terminal
  with passwordless `sudo` access. Any user with access to the GUI can gain root
  control within the container, install arbitrary software, and probe your local
  network."* Always run `lockdown` and reach it over SSH. Never expose 3000/3001 to
  a network, and never to the internet.
- **`network_mode: host` is deliberate** — the plugin may bind loopback-only inside
  the container, which would make a published port silently useless. The cost is
  that Docker cannot bind-restrict the GUI to `127.0.0.1`, so basic auth and ufw
  are load-bearing rather than optional.
- **`lockdown` allows `22/tcp` first, always.** ufw defaults to deny-incoming on
  enable; without that rule you lose your SSH session mid-command. Never reorder it.
- **Never overwrite `plugins/obsidian-local-rest-api/data.json`** on a vault that is
  already connected. It holds the API key; replacing it silently breaks every MCP
  client pointed at that vault. Both profile-apply scripts treat it as protected.
- **Never commit or paste the API key.** It grants full read/write on the vault.
  Rotate by deleting `apiKey` from `data.json`, restarting the container, re-running
  `finalize`, and re-registering with Claude.
- **Obsidian Sync is a paid add-on.** If the Sync pane offers nothing, there is no
  subscription on that account. Do not debug it as a technical fault.
