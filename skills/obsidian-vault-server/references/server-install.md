# Server install

The installer is `obsidian-vault-server.sh`. It lives in the private
`infrastructure-scripts` repo under `Bash/Obsidian/`; this reference describes what
it does so the behaviour can be reproduced or debugged without it.

## Prerequisites

| Requirement | Notes |
|---|---|
| Ubuntu 22.04+ | Debian works; the script warns on anything else |
| root / sudo | Installs Docker, writes under `/opt` |
| ~2 GB free RAM | Electron plus a virtual display; `shm_size` is 1 GB |
| SSH from the workstation | The MCP endpoint is reached over a tunnel, never published |
| obsidian.md account **with a Sync subscription** | Only for cloud sync; the vault and MCP work without it |

Outbound HTTPS to `get.docker.com`, `lscr.io`, `api.github.com`, `sync.obsidian.md`.

## What `install` does

1. `apt-get install curl jq ca-certificates gnupg unzip`, then Docker Engine via
   `get.docker.com` **only if `docker` is absent**.
2. Docker Compose, through four escalating attempts (see below).
3. Writes `/opt/obsidian-server/docker-compose.yml` — `lscr.io/linuxserver/obsidian`,
   `network_mode: host`, `shm_size: 1gb`, `security_opt: seccomp:unconfined`
   (Electron's sandbox needs it), `CUSTOM_USER` + generated `PASSWORD`.
4. Seeds the vault: `.obsidian/community-plugins.json` listing
   `obsidian-local-rest-api` (which also takes it out of Restricted Mode), minimal
   `app.json` / `appearance.json`, a `Welcome.md`.
5. Registers the vault in `config/.config/obsidian/obsidian.json` with `open: true`
   so Obsidian boots straight into it instead of showing the vault picker.
6. Downloads the plugin's latest release from GitHub.
7. `chown -R` to `PUID:PGID` (default `1000:1000`), `docker compose up -d`, then
   waits up to 60 s for the plugin to write `data.json` with an API key.

### Paths

```
/opt/obsidian-server/
├── docker-compose.yml            mode 600 - carries the GUI password
├── .gui-credentials              mode 600 - GUI basic auth
└── config/                       -> /config in the container
    ├── .config/obsidian/obsidian.json
    └── vault/
        └── .obsidian/
            ├── community-plugins.json
            └── plugins/obsidian-local-rest-api/data.json   API key
```

Note the `config/` level. The vault is `$OBS_BASE/config/$OBS_VAULT_NAME`, not
`$OBS_BASE/$OBS_VAULT_NAME` — a common source of "no vault at ..." errors.

### Environment overrides

`OBS_BASE`, `OBS_VAULT_NAME`, `OBS_CONTAINER`, `OBS_IMAGE`, `OBS_GUI_PORT`,
`OBS_GUI_PORT_TLS`, `OBS_REST_HTTP`, `OBS_REST_HTTPS`, `OBS_GUI_USER`,
`OBS_GUI_PASSWORD`, `OBS_PUID`, `OBS_PGID`, `OBS_TZ`.

## Docker Compose: why it needs four fallbacks

The installer only runs `get.docker.com` when `docker` is **absent**. On a host
where Docker came from Ubuntu's own `docker.io` package, Docker is present and the
Compose plugin never was. So:

1. `apt-get install docker-compose-plugin` — works if Docker's apt repo is set up.
2. **Configure Docker's official apt repo, retry.** Keyring to
   `/etc/apt/keyrings/docker.asc`, source list from `VERSION_CODENAME` (`jammy` on
   22.04, `noble` on 24.04) and `dpkg --print-architecture`. The usual fix.
3. `apt-get install docker-compose-v2` — Ubuntu 24.04+ universe name.
4. **Static binary** from the `docker/compose` release page into
   `/usr/local/lib/docker/cli-plugins/docker-compose`, architecture-aware.

**Snap Docker cannot be fixed this way.** Snap does not load CLI plugins from that
path, so dropping the binary there appears to succeed and then does not work. The
script detects the snap and stops:

```bash
sudo snap remove docker && curl -fsSL https://get.docker.com | sh
```

## Locking it down

Not optional. The GUI is a full desktop session whose built-in terminal has
passwordless `sudo`.

```bash
sudo ./obsidian-vault-server.sh lockdown             # deny 3000/3001, use a tunnel
sudo ./obsidian-vault-server.sh lockdown 192.0.2.10  # allow one host on HTTPS
```

`lockdown` runs `ufw allow 22/tcp` **first** — ufw defaults to deny-incoming on
enable, so without it you lose the SSH session you are typing into. Any allow-from
exception is added ahead of the denies so ufw's first-match-wins ordering keeps it
working. By hand:

```bash
sudo ufw allow 22/tcp
sudo ufw deny 3000/tcp
sudo ufw deny 3001/tcp
sudo ufw --force enable
```

The REST/MCP port needs no rule; it is bound to loopback.

## Lifecycle

| Command | Effect |
|---|---|
| `status` | Container, note count, plugin/API key presence, endpoint probe |
| `apikey` / `gui-password` | Print the respective credentials |
| `connect` | Re-print the tunnel and `claude mcp add` commands |
| `logs` | Tail container logs |
| `restart` | Restart the container — picks up plugin setting changes |
| `uninstall` | Remove the container, **keep** the vault data |

The container is `restart: unless-stopped` and Docker is enabled at boot, so the
vault runs and syncs continuously. Nothing needs starting per session except the
SSH tunnel on the workstation.

Updating:

```bash
cd /opt/obsidian-server && sudo docker compose pull && sudo docker compose up -d
```

## Troubleshooting

| Symptom | Cause |
|---|---|
| *"This application requires a secure connection (HTTPS)"* | Browsed `http://<ip>:3000`. Use the tunnel or `https://<ip>:3001` |
| `apikey` says "not generated yet" | The plugin initialises only once Obsidian opens the vault. Load the GUI first |
| Endpoint silent after `finalize` | Obsidian needs a reload to bind the new listener. `restart`, wait ~20 s |
| Restricted Mode re-enables | Obsidian's trust-the-author prompt. Accept it in the GUI |
| Black screen / crash loop | Shared memory. Check `logs` and `free -h` |
| Sync pane offers nothing | No Sync subscription on the signed-in account |
