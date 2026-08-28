---
name: obsidian-setup
description: Install and configure Obsidian, the Local REST API bridge, and this plugin's config for a vault. Use when the user says set up Obsidian, configure the vault bridge, run obsidian init, or asks why mcp__obsidian__* tools are not working.
---

# Obsidian setup

The steps `/obsidian-vault:init` follows. Read this before running that command by
hand or debugging a bridge that will not connect.

## 1. Resolve the vault

Check, in order:

1. An explicit path given to the command.
2. `~/.claude/obsidian/config.json` -> `vaults.<name>.path` (or the legacy
   `vaultPath` for the default vault), if the named vault already exists in
   config - this is a re-run for that vault, not a first setup.
3. Obsidian's own vault registry:
   - Windows: `%APPDATA%\obsidian\obsidian.json`
   - macOS: `~/Library/Application Support/obsidian/obsidian.json`
   - Linux: `~/.config/obsidian/obsidian.json` (respects `XDG_CONFIG_HOME`)

   That file is `{"vaults": {"<id>": {"path": "...", "ts": <ms>, "open": bool}}}`.
   Prefer a vault with `"open": true`; otherwise take the newest by `ts`. This
   tells you what Obsidian itself currently considers current, without the
   user repeating it.
4. If nothing resolves, ask where to create or point at a vault. Never invent
   a path - a wrong default silently pointed a hook at the wrong directory is
   how the personal version of this plugin's hooks used to fail for anyone
   else who installed them.

## 2. Install Obsidian if missing

**Windows:** `winget install Obsidian.Obsidian` (winget is on PATH by default
on Windows 10 2004+ / Windows 11).

**macOS:** `brew install --cask obsidian` if Homebrew is present; otherwise
point at https://obsidian.md/download.

**Linux:** there is no universal package. In order of preference:
- Flatpak, if `flatpak` is on PATH: `flatpak install flathub md.obsidian.Obsidian`
- The official AppImage from https://obsidian.md/download - download, `chmod +x`,
  and tell the user where it landed; Claude does not silently add it to PATH
  or create a desktop entry without asking.
- A distro package if one exists (`snap install obsidian`), only if the user's
  distro is known to carry it.

Ask which the user wants rather than picking for them - a Flatpak's sandbox
changes what paths Obsidian and the Local REST API plugin can actually see,
which matters for step 3.

## 3. Community plugin: Local REST API

1. If Obsidian has never been launched against this vault, launch it once so
   `.obsidian/` exists, then close it (a real quit, not a window close - see
   the warning under Troubleshooting).
2. Community plugins must be enabled (not Restricted Mode). If
   `.obsidian/community-plugins.json` does not exist or is `[]`, this is
   likely the first run - say so and ask the user to confirm "Turn on
   community plugins" in Obsidian's Settings > Community plugins once, since
   Claude cannot click through Obsidian's own onboarding dialog.
3. Install `obsidian-local-rest-api` (from the Community Plugins browser, or
   by placing the release files under
   `.obsidian/plugins/obsidian-local-rest-api/` if scripting the install) and
   enable it in `community-plugins.json`.
4. After Obsidian has run with the plugin enabled at least once,
   `.obsidian/plugins/obsidian-local-rest-api/data.json` contains a generated
   `apiKey`. Read it - never generate or guess a key yourself.

## 4. Register the MCP server - one per vault

```
claude mcp add --scope user obsidian-<name> --transport http http://127.0.0.1:<port>/mcp \
  --header "Authorization: Bearer <apiKey from step 3.4>"
```

**Always the HTTP port, never HTTP port + 1 (HTTPS).** The HTTPS side uses a
self-signed certificate; Claude Code's Node HTTP client rejects it with
`DEPTH_ZERO_SELF_SIGNED_CERT` and there is no clean way to trust it from this
side. If `enableInsecureServer` is off in the plugin's settings, turn it on -
insecure here means "no TLS on loopback," not "no auth"; the bearer key still
gates every request.

**One MCP server per vault, never one server for two vaults.** Local REST API
is a per-vault plugin instance on a per-vault port, live only while that
specific vault is open - there is no single endpoint that could speak for
both even if you wanted one. Name each server `obsidian-<name>` (e.g.
`obsidian-memory`, `obsidian-codegraphs`) so tool names never collide:
`mcp__obsidian-memory__*` versus `mcp__obsidian-codegraphs__*`.

## 5. Write plugin config

`~/.claude/obsidian/config.json`:

```json
{
  "vaults": {
    "memory": {
      "path": "<resolved path>",
      "port": 27123,
      "default": true
    },
    "codegraphs": {
      "path": "<second vault path, if configuring one>",
      "port": 27125,
      "layout": "org/repo"
    }
  },
  "guard": {
    "asciiOnly": false,
    "requireFrontmatter": false,
    "checkCanvas": true
  }
}
```

Only ever set `default: true` on one vault - it is the only one the ASCII/
frontmatter/canvas guard and the session-capture hook apply to, and the only
one an env var or Obsidian's own "last open vault" detection can silently
resolve to. A second vault (a graphify code-graph export is the common case)
is configured but never guarded or captured into the same inbox - see
`obsidian-memory-contract`'s "Multiple vaults" section for why enforcing the
default vault's contract on a machine-generated vault would be wrong, not
just unnecessary. Record a vault's folder convention in `layout` (free text,
e.g. `"org/repo"`) when a command like `/obsidian-vault:graph` needs to know
it - this has no effect on resolution, it is just metadata other commands
read.

Before writing `guard.asciiOnly` or `guard.requireFrontmatter` as `true`, read
the *default* vault's own `CLAUDE.md` for an explicit statement of an ASCII
rule or a frontmatter contract. Turn a toggle on only when the vault says so
itself - never because this plugin's author's own vault happens to want it.
If the vault has no `CLAUDE.md` yet, leave both `false` and offer to write one
from the `obsidian-memory-contract` skill's template, explaining what each
toggle would then do.

If `~/.claude/obsidian/config.json` already exists, show the diff and confirm
before overwriting any key the user already set - adding a second vault means
merging a new key under `vaults`, never replacing the block. A config file
still in the older single-vault shape (`"vaultPath"` at the top level, no
`vaults` key) keeps working unmodified; only migrate it to the `vaults` shape
when the user is actually adding a second vault, and confirm before rewriting
it.

## 5b. Offer the starter plugin set - fresh vaults only

If step 3 found `.obsidian/community-plugins.json` absent or `[]` (a genuinely
fresh vault, not a re-run), offer this starter set - the same one this repo's
prior `vault-automation/` installer pre-enabled - one plugin at a time via
`/obsidian-vault:optimize`'s confirm-per-item rule, never all at once:

| Plugin | Why |
|---|---|
| Dataview | Queryable frontmatter - the dashboard views in a `HOME.md`, and most vault automation, depend on it |
| Obsidian Git | Version history and (optionally) a remote backup, on top of Sync |
| Excalidraw | Freehand diagrams alongside JSON Canvas, for sketches a structured canvas does not fit |
| Omnisearch | Full-text search beyond core search - **skip this on a vault expected to grow past ~50k notes**; see `obsidian-memory-contract`'s performance section, since Omnisearch's index is exactly what gets slow there |
| Kanban | Board-view task tracking inside notes |

Never install Omnisearch onto a vault already declared as a large,
machine-generated one (e.g. a codegraphs `layout` vault) - propose the
filesystem-first approach instead and skip straight to step 6.

## 6. Verify end to end

Do not report success because the steps ran. For each vault just configured,
confirm:

```
GET http://127.0.0.1:<that vault's port>/  with header  Authorization: Bearer <apiKey>
```

returns `{"authenticated": true, ...}`. If it does not, this is exactly what
`/obsidian-vault:doctor` diagnoses - point there rather than re-deriving the
diagnosis inline.

## Troubleshooting

- **Obsidian looks "up" but the bridge is down.** Obsidian reads its plugin
  list only at launch; closing the window minimizes to the tray rather than
  quitting, so a plugin enabled after launch is not actually loaded. A full
  quit from the tray icon and relaunch is required, not just closing the
  window.
- **The HTTPS port (port + 1) answers but the HTTP port does not.**
  `enableInsecureServer` is off in the plugin's settings for that vault. Turn
  it on, reload Obsidian (command `app:reload`). Do not repoint the MCP server
  at the HTTPS port to work around it - see step 4.
- **Key rejected after previously working.** The key in that vault's
  `data.json` no longer matches what its MCP server has. Re-run `claude mcp
  remove --scope user obsidian-<name>` and re-add with the current key, or run
  `/obsidian-vault:doctor`.
- **A second vault's bridge only answers while that vault's Obsidian window is
  actually open.** Unlike a single-vault setup, running two vaults commonly
  means running two Obsidian windows (or opening the second one only when
  needed) - `/obsidian-vault:doctor` reporting one vault down while another is
  up is expected, not a misconfiguration, if only one window is open.
