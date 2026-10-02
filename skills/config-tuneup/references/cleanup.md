# Cleanup commands

Every command here changes state. Confirm with the user first, naming the exact plugin,
marketplace, path, or key.

## Plugins

```bash
claude plugin list                                  # installed, with enabled/disabled state
claude plugin disable <plugin>@<marketplace>        # reversible, keeps it on disk
claude plugin enable  <plugin>@<marketplace>
claude plugin uninstall <plugin>@<marketplace>      # removes it; marketplace stays registered
claude plugin update  <plugin>@<marketplace>        # pull the marketplace's current version
```

Disable when unsure, uninstall when done. A disabled plugin still has its marketplace
refreshed and still occupies disk; it costs no context.

Order matters when a plugin is published by two marketplaces: uninstall the one you don't
want **first**, then remove its marketplace, or the second install silently comes back on the
next refresh.

## Marketplaces

```bash
claude plugin marketplace list
claude plugin marketplace remove <name>
claude plugin marketplace add <owner/repo>
```

Only remove a marketplace once nothing installed still comes from it — a plugin whose
marketplace is gone loses its update path and reports as unresolved.

A marketplace `version` field that never changes can block `claude plugin update`: the
client sees the same version and has nothing to fetch. If a plugin's content changed but its
version didn't, uninstall and reinstall it, and tell the marketplace's owner to bump versions
on content changes.

## Loose skills in `~/.claude/skills/`

These are plain directories. Nothing manages them — no update path, no uninstall command.

```bash
ls ~/.claude/skills                                     # what's there
diff -r ~/.claude/skills/<name> \
        ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>   # local edits?
rm -rf ~/.claude/skills/<name>                          # after confirming
```

Windows PowerShell:

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\skills" -Directory
Remove-Item "$env:USERPROFILE\.claude\skills\<name>" -Recurse -Force
```

Copy the directory somewhere first if there is any doubt — a hand-written skill living here
looks identical to a leftover copy.

## Hooks

Hooks live in `settings.json` under `hooks.<Event>[].hooks[]`, and in each plugin's
`hooks/hooks.json`. You can only edit the settings ones; a plugin's hooks come and go with
the plugin.

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak     # always
```

Then remove the offending entry by hand. Patch the minimum text; don't reformat the file
through a JSON pretty-printer, which reflows everything and buries the real change in the
diff. `hooks` hot-reloads, so the change takes effect without a restart.

To consolidate several `PreToolUse` hooks into one, write a single dispatcher script that
runs each check in-process and exits non-zero only when it means to block. One process spawn
instead of five is the whole win.

## MCP servers

```bash
claude mcp list
claude mcp remove <name>
claude mcp add <name> -- <command> [args...]           # user scope
```

Project-scoped servers belong in the repo's `.mcp.json` — that keeps their tool schemas out
of every other project. Moving a server from user scope to project scope is
`claude mcp remove <name>` followed by an entry in `.mcp.json`.

## Settings keys worth revisiting

| Key | Symptom when wrong | Sane value |
|---|---|---|
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | compacts constantly, loses detail | 80–85, or unset |
| `MAX_MCP_OUTPUT_TOKENS` | one MCP call eats the window | ≤ 25000 |
| `BASH_MAX_OUTPUT_LENGTH` | one noisy command eats the window | ≤ 50000 |
| `verbose` | unreadable long sessions | `false` unless debugging |

`env`, `permissions`, and `hooks` hot-reload. `model` needs `/model` mid-session;
`outputStyle` needs `/clear` or a restart.

## Disk

```bash
du -sh ~/.claude/plugins/cache ~/.claude/projects        # the two that grow
```

`plugins/cache` holds one directory per plugin version; Claude Code prunes old ones, and a
version marked `.orphaned_at` is already scheduled for removal. `projects/` is transcript
history — needed only for `--resume` and history search, safe to delete per project.

## Verify after

```bash
python scripts/cc_audit.py --min-severity med
```

Then in a fresh session: `/context` for the real budget, `/status` for what resolved,
`/doctor` for settings entries Claude Code rejected.
