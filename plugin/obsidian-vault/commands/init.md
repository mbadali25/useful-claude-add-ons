---
description: Install and configure Obsidian, the Local REST API bridge, and one or more named vaults for this plugin
argument-hint: [vault-name] [vault-path]
allowed-tools: Read, Write, Edit, Bash, PowerShell, Skill
---

Set up Obsidian for Claude Code memory. If $1/$2 name a vault and a path, add
or update that one entry. With no arguments, set up (or verify) the default
vault; detect one if none is configured.

Invoke the `obsidian-setup` skill and follow it exactly - it has the per-OS
install steps, the Local REST API configuration, and the MCP registration this
file does not repeat. In outline, so you know the shape before you load it:

1. **Resolve the vault.** $2 if given. Otherwise, for the default vault, probe
   Obsidian's own registry (`%APPDATA%\obsidian\obsidian.json` on Windows,
   `~/.config/obsidian/obsidian.json` on Linux, `~/Library/Application
   Support/obsidian/obsidian.json` on macOS) for a vault marked open. If none
   exists anywhere, ask where to create one - do not invent a path. For a
   second or later named vault there is nothing to detect from - always ask.
2. **Install Obsidian if it is missing.** `winget install Obsidian.Obsidian` on
   Windows; on Linux, detect the package manager and offer the Flatpak
   (`flatpak install flathub md.obsidian.Obsidian`) or point at the AppImage -
   there is no universal package name across distros, so ask rather than guess.
3. **Configure the Local REST API community plugin, per vault.** Install it if
   absent in *that* vault, enable it, read its generated `apiKey` from
   `<vault>/.obsidian/plugins/obsidian-local-rest-api/data.json`. Local REST
   API is per-vault: it only answers while that vault is open in its own
   Obsidian window, on the port that vault's plugin instance was configured
   with. Ask for the port rather than assuming - `27123` for a first vault,
   the next configured vault commonly `27125` (leaving `27124`/`27126` free
   for each vault's HTTPS side), but this is a convention this plugin follows,
   not something Local REST API enforces.
4. **Register one MCP server per vault**, never one server multiplexing two
   vaults - the bridge is per-port, so a single server config cannot serve
   both anyway. Name each server `obsidian-<vault-name>` so multiple vaults
   never collide:
   ```
   claude mcp add --scope user obsidian-<name> --transport http http://127.0.0.1:<port>/mcp \
     --header "Authorization: Bearer <apiKey for that vault>"
   ```
   Always the HTTP port, never HTTP port + 1 (self-signed cert on the HTTPS
   side; Node's client rejects it - see the `obsidian-setup` skill).
5. **Write `~/.claude/obsidian/config.json`** as:
   ```json
   {
     "vaults": {
       "<name>": { "path": "<resolved path>", "port": <http port>,
                   "layout": "<optional, e.g. 'org/repo'>", "default": true }
     },
     "guard": { "asciiOnly": false, "requireFrontmatter": false, "checkCanvas": true }
   }
   ```
   Set `default: true` on exactly one vault - the first one configured, unless
   told otherwise. Only that vault gets the ASCII/frontmatter/canvas guard,
   the capture-to-inbox hook, and env-var/detection fallback; a second vault
   (particularly a generated one like a code-graph vault, which nobody
   hand-authors frontmatter into) is deliberately not guarded the same way -
   see the `obsidian-memory-contract` skill for why. Set `guard` toggles from
   what the *default* vault's own `CLAUDE.md` states (ASCII-only, required
   frontmatter keys) - detected, never assumed.
6. **Note a vault's `layout`** if it has a structural convention worth other
   commands knowing - a code-graph vault laid out `<org>/<repo>/` should
   record `"layout": "org/repo"` so `/obsidian-vault:graph` addresses it
   correctly instead of guessing crew's own `codegraphs/<repo>/` default.
7. **Probe end to end**, the way `/obsidian-vault:doctor` does, for every vault
   just configured, and report the result plainly rather than assuming the
   wiring worked because the steps ran.

Never overwrite an existing `~/.claude/obsidian/config.json` silently - read it
first, show what would change, and confirm before writing over a value the
user already set. Adding a second vault means merging a new key into
`vaults`, never replacing the block.
