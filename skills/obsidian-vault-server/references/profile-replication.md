# Getting a workstation's plugins onto the server

A fresh server vault has no plugins beyond the REST API one. There are two ways to
fix that, and one of them is in this repo.

## Option A — the standard set (this repo)

If the goal is "make the server vault look like our standard vault", use the
installers in [`claude-obsidian-setup/`](../../../claude-obsidian-setup/):

```bash
./install-obsidian-plugins.sh --vault /opt/obsidian-server/config/vault           # preview
./install-obsidian-plugins.sh --vault /opt/obsidian-server/config/vault --apply
sudo chown -R 1000:1000 /opt/obsidian-server/config/vault/.obsidian
docker restart obsidian
```

Reads `obsidian-plugin-profile.json` — 15 community plugins with pinned versions and
repos, plus the 27 core plugins to enable. Dry run by default, idempotent, additive.

**Run it on the host, not inside the container.** The vault is bind-mounted from
`/opt/obsidian-server/config` to `/config`, so host-side edits are the same files.
The container has no `jq`. Re-`chown` afterwards or Obsidian cannot write.

## Option B — mirror a specific workstation vault

If the goal is "reproduce *my* vault, with its settings", use the export/apply pair
in `infrastructure-scripts/Bash/Obsidian/`:

```powershell
.\Export-ObsidianProfile.ps1 -VaultPath C:\repos\claude-memories
```

```bash
scp -r obsidian-profile you@server:~/
sudo ./apply-obsidian-profile.sh ~/obsidian-profile --dry-run
sudo ./apply-obsidian-profile.sh ~/obsidian-profile --restart
```

This carries per-plugin `data.json` settings as well as the plugins themselves.

## Never copy `.obsidian` wholesale, and never let Sync carry plugins

The same file blocks both routes: `plugins/obsidian-local-rest-api/data.json` holds
an API key with full vault read/write.

- **Copying** overwrites the server's key and breaks the MCP endpoint.
- **Syncing** — enabling *"Installed community plugins"* in Obsidian Sync — pushes
  that credential to every device on the account.

Both apply scripts treat the plugin as protected and refuse to write its settings.
`workspace.json` is excluded too: per-device UI layout that conflicts on essentially
every sync cycle.

## How plugin ids resolve to repositories

A plugin's `manifest.json` records its id and version but **not** its repository. So
the scripts fetch the official registry —
`obsidianmd/obsidian-releases/community-plugins.json`, roughly 6,700 entries — and
map `id -> repo`, cached for an hour.

Release assets come from `github.com/<repo>/releases/download/<tag>/`. Obsidian
plugins usually tag the bare version (`1.2.0`), occasionally with a `v` prefix, so
both are tried before falling back to `releases/latest` with a warning naming the
mismatch. `styles.css` is optional; its absence is not an error.

## Two traps worth knowing

**jq built for Windows writes CRLF.** Reading `jq ... @tsv` output with `read`
leaves a carriage return on the last field, which silently corrupts every URL built
from it — and the printed repo name still *looks* right, because `\r` only moves the
cursor. Pipe through `tr -d '\r'`. Harmless on Linux, essential under Git Bash.

**PowerShell's `@(<pipeline>)` does not unroll.** `ConvertFrom-Json` emits a JSON
array as one object, so `@(Get-Content x | ConvertFrom-Json)` is a 1-element array
*containing* the array. Assign to a variable first, then wrap — otherwise every
pre-existing entry is silently dropped from a merge.
