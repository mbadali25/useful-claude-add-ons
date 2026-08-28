---
description: Install and configure Obsidian, the Local REST API bridge, and the vault contract for this plugin
argument-hint: [vault-path]
allowed-tools: Read, Write, Edit, Bash, PowerShell, Skill
---

Set up Obsidian for Claude Code memory. Vault path: $1, or detect one.

Invoke the `obsidian-setup` skill and follow it exactly - it has the per-OS
install steps, the Local REST API configuration, and the MCP registration this
file does not repeat. In outline, so you know the shape before you load it:

1. **Resolve the vault.** $1 if given. Otherwise probe Obsidian's own registry
   (`%APPDATA%\obsidian\obsidian.json` on Windows, `~/.config/obsidian/obsidian.json`
   on Linux, `~/Library/Application Support/obsidian/obsidian.json` on macOS) for
   a vault marked open. If none exists anywhere, ask where to create one - do
   not invent a path.
2. **Install Obsidian if it is missing.** `winget install Obsidian.Obsidian` on
   Windows; on Linux, detect the package manager and offer the Flatpak
   (`flatpak install flathub md.obsidian.Obsidian`) or point at the AppImage -
   there is no universal package name across distros, so ask rather than guess.
3. **Configure the Local REST API community plugin.** Install it if absent,
   enable it, read its generated `apiKey` from
   `<vault>/.obsidian/plugins/obsidian-local-rest-api/data.json`.
4. **Register the `obsidian` MCP server** pointed at `http://127.0.0.1:27123`
   with that key - never at `:27124` (self-signed cert, Node's client rejects
   it; see the `obsidian-setup` skill for the full reasoning).
5. **Write `~/.claude/obsidian/config.json`** with `vaultPath` and any `guard`
   toggles this vault's own `CLAUDE.md` states (ASCII-only, required
   frontmatter keys) - detected, never assumed. This is the one file every hook
   in this plugin reads; get it right once here.
6. **Probe end to end**, the way `/obsidian:doctor` does, and report the result
   plainly rather than assuming the wiring worked because the steps ran.

Never overwrite an existing `~/.claude/obsidian/config.json` silently - read it
first, show what would change, and confirm before writing over a value the user
already set.
