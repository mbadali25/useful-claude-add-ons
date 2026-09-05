---
description: Bring a vault onto the bridge and up to its profile's plugin set, one confirmed plugin at a time, then register its MCP server
argument-hint: <vault-name> [vault-path]
allowed-tools: Read, Bash, PowerShell
---

Bring a vault that has no Local REST API plugin onto the bridge, and then up to
whatever plugin set its **profile** calls for. This is the one case
`/obsidian-vault:repair` cannot help with: there is no `data.json` to compare
ports against and no API key to register, because the plugin was never installed
in that vault.

`${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py` does the work. Dry-run by
default, writes only with `--apply`. If `python` is not on PATH, try `python3`
then `py`, and say which one worked. Exit 0 healthy or applied, 1 problems
found, 2 usage error.

## 1. The vault needs a name first

`enable-plugin --vault <name>` resolves that name through
`~/.claude/obsidian/config.json`. A vault Obsidian knows about but this plugin
does not has no name to pass. Run `/obsidian-vault:init <name> <path>` first to
give it one, then come back here.

Check before assuming: `scan` lists what is on the machine, including vaults
absent from config.

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" scan --json
```

If `scan` reports a vault that `enable-plugin` then refuses to resolve, that is
the missing config entry, not a script fault. Say so and run `init`.

## 2. Find out what this vault should be running

A vault is either **authored** (a person reads and edits it) or **generated**
(only Claude ever greps it), and the right plugin set is not the same. Ask
before installing anything:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" profile --vault <name>
```

That reports the detected kind, the evidence behind it, what the vault lacks and
what it carries that the profile does not want. Three kinds:

| Kind | Set | Why |
|---|---|---|
| `bridge` | `obsidian-local-rest-api` | The floor. Without it the vault is invisible to Claude - not slow, not misconfigured, invisible. |
| `graph` | `obsidian-local-rest-api`, `code-graph` | A generated codegraph vault. Deliberately no omnisearch, dataview or text-extractor: those build an index, and in a vault only Claude greps nothing ever reads it. |
| `authored` | the bridge plus dataview, templater, periodic-notes, kanban, excalidraw, breadcrumbs, linter, metadata-menu, charts, git, advanced-uri, auto-note-mover - plus omnisearch and text-extractor only below ~50,000 notes | A human's vault, where rendering matters. |

Report the evidence, not just the verdict. If detection is wrong, `--profile
KIND` overrides it for one run and `--set KIND --apply` stores the override in
config; both keep reporting what detection said, so a stale override stays
visible. Never set one to make a number come out nicer.

## 2b. Install and enable, one plugin at a time

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name>
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name> --apply
```

The dry run lists the whole profile set and prints the exact command for each
plugin the vault is missing. **`--apply` on its own writes only the Local REST
API floor** - it will not enable a profile in bulk, and that is deliberate:
enabling a plugin changes what a vault renders and what it depends on, exactly
as disabling one does, and `/obsidian-vault:optimize` has always required a
separate yes per plugin on the removal side. Same rule here.

So for everything past the floor, walk them one at a time:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name> --plugin <id>
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name> --plugin <id> --apply
```

Show that plugin's dry run, say what it is for, and get a yes for **that plugin**
before applying it. Never a single "install the set, yes/no". `--all` covers
every configured vault; ask for that one explicitly rather than defaulting to it.

Enabling writes `community-plugins.json` **inside the user's vault**, outside
this repo. Obsidian reads that file only at launch - not at `app:reload`, which
is enough for `data.json` and is not enough here. So a plugin this command
enabled is enabled *on disk* and is *not running* until the vault is quit from
the tray icon and relaunched. Say that; do not report the install as done.

Two things the script cannot do for you, because they are Obsidian's own UI:

- **Community plugins must be off Restricted Mode.** If
  `<vault>/.obsidian/community-plugins.json` is missing or `[]`, ask the user to
  turn community plugins on once in Settings > Community plugins. Claude cannot
  click through that dialog.
- **The vault must have been opened at least once** so `.obsidian/` exists, and
  opened again *after* the plugin is enabled so the plugin generates its
  `apiKey`. Reading a `data.json` that has no key yet means the vault has not
  been relaunched.

Never generate or guess an API key. Read the one the plugin wrote.

## 3. Check the new vault's ports against every other vault's

A freshly installed plugin writes whatever ports it defaults to, which is how a
duplicate gets created. Before registering anything, run `fix-ports` as a dry
run:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" fix-ports --vault <name>
```

Exit 0 means no collision and there is nothing to apply. Exit 1 means the new
vault duplicates a port already declared elsewhere - show the plan, get a yes,
and run it again with `--apply`, then `reload` that vault's window so the plugin
picks up the change.

A vault that duplicates a bound port loses the bind, and its plugin then fails
to start its server at all - no HTTP listener, an HTTPS port answering with the
other vault's API key, and the other vault's files served. One cause, three
symptoms. That is the failure this step exists to avoid creating.

There is no arithmetic relating the two ports. In `data.json`, `port` is HTTPS
and `insecurePort` is HTTP, and they are whatever each vault was configured
with. On the machine this plugin was written against: memory is HTTPS 27124 /
HTTP 27123, codegraphs 27128 / 27125, anew-codegraph 27126 / 27127. Do not
derive one from the other.

## 4. Register the MCP server

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" register --vault <name> --apply
```

One server per vault, named `obsidian-<vault-name>`, pointed at the HTTP port.
Then confirm with `diagnose`, and report what it says rather than reporting that
the steps ran.

## The two vaults on this machine that need this

Both are in Obsidian's own registry and have no
`.obsidian/plugins/obsidian-local-rest-api/` at all:

| Vault | Path |
|---|---|
| `claude-anew-theselectsource` | `C:\repos\claude-anew-theselectsource` |
| `claude-anew-thd-codegraph` | `C:\repos\claude-anew-thd-codegraph` |

Neither has an entry in `~/.claude/obsidian/config.json`, so both need step 1's
`/obsidian-vault:init` before `enable-plugin` has a name to resolve. Confirm
with `scan` rather than trusting this table - it is a snapshot of one machine,
and a vault added since will not be in it.

## Report

Per vault: the detected profile and the evidence for it, which plugins were
enabled and which the user declined, whether Obsidian needed a relaunch (and
whether it has happened yet - an enabled plugin that has not been relaunched
into is not running), what ports it ended up with and whether `fix-ports` had to
move them, whether the MCP server registered, and what `diagnose` returned
afterwards.

Name anything the profile still lacks. A vault left one plugin short of its
profile is a fine outcome if the user said no; it is a bad outcome if nobody
mentioned it.
