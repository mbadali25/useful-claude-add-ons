---
name: obsidian-setup
description: Install and configure Obsidian, the Local REST API bridge, and this plugin's config for a vault. Use when the user says set up Obsidian, configure the vault bridge, run obsidian init, or asks why mcp__obsidian__* tools are not working.
---

# Obsidian setup

The steps `/obsidian:init` follows. Read this before running that command by
hand or debugging a bridge that will not connect.

## 1. Resolve the vault

Check, in order:

1. An explicit path given to the command.
2. `~/.claude/obsidian/config.json` -> `vaultPath`, if one already exists (this
   is a re-run, not a first setup).
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

## 4. Register the MCP server

```
claude mcp add --scope user obsidian --transport http http://127.0.0.1:27123/mcp \
  --header "Authorization: Bearer <apiKey from step 3.4>"
```

**Always port 27123 (HTTP), never 27124 (HTTPS).** The HTTPS port uses a
self-signed certificate; Claude Code's Node HTTP client rejects it with
`DEPTH_ZERO_SELF_SIGNED_CERT` and there is no clean way to trust it from this
side. If `enableInsecureServer` is off in the plugin's settings, turn it on -
insecure here means "no TLS on loopback," not "no auth"; the bearer key still
gates every request.

## 5. Write plugin config

`~/.claude/obsidian/config.json`:

```json
{
  "vaultPath": "<resolved path>",
  "guard": {
    "asciiOnly": false,
    "requireFrontmatter": false,
    "checkCanvas": true
  }
}
```

Before writing `guard.asciiOnly` or `guard.requireFrontmatter` as `true`, read
the vault's own `CLAUDE.md` for an explicit statement of an ASCII rule or a
frontmatter contract. Turn a toggle on only when the vault says so itself -
never because this plugin's author's own vault happens to want it. If the
vault has no `CLAUDE.md` yet, leave both `false` and offer to write one from
the `obsidian-memory-contract` skill's template, explaining what each toggle
would then do.

If `~/.claude/obsidian/config.json` already exists, show the diff and confirm
before overwriting any key the user already set.

## 6. Verify end to end

Do not report success because the steps ran. Confirm:

```
GET http://127.0.0.1:27123/  with header  Authorization: Bearer <apiKey>
```

returns `{"authenticated": true, ...}`. If it does not, this is exactly what
`/obsidian:doctor` diagnoses - point there rather than re-deriving the
diagnosis inline.

## Troubleshooting

- **Obsidian looks "up" but the bridge is down.** Obsidian reads its plugin
  list only at launch; closing the window minimizes to the tray rather than
  quitting, so a plugin enabled after launch is not actually loaded. A full
  quit from the tray icon and relaunch is required, not just closing the
  window.
- **Port 27124 answers but 27123 does not.** `enableInsecureServer` is off in
  the plugin's settings. Turn it on, reload Obsidian (command `app:reload`).
  Do not repoint the MCP server at 27124 to work around it - see step 4.
- **Key rejected after previously working.** The key in `data.json` no longer
  matches what the MCP server has. Re-run `claude mcp remove --scope user
  obsidian` and re-add with the current key, or run `/obsidian:doctor`.
