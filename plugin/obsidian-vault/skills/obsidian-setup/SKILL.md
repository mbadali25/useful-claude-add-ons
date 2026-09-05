---
name: obsidian-setup
description: Install and configure Obsidian, the Local REST API bridge, and this plugin's config for a vault. Use when the user says set up Obsidian, configure the vault bridge, run obsidian init, or asks why mcp__obsidian__* tools are not working.
---

# Obsidian setup

The steps `/obsidian-vault:init` follows. Read this before running that command by
hand or debugging a bridge that will not connect.

## Nothing here is done by hand

`${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py` performs every action this
skill describes. It is dry-run by default and writes only with `--apply`. Exit 0
means healthy or applied, 1 means problems found, 2 means a usage error - exit 1
is a successful diagnosis, not a crash.

| Want | Run |
|---|---|
| See every vault on the machine, configured or not | `scan [--json]` |
| Find what is wrong | `diagnose [--vault NAME] [--json]` |
| Resolve a port collision | `fix-ports [--vault NAME] [--apply]` |
| Reload a stale Obsidian window | `reload [--vault NAME \| --all]` |
| Register or re-register MCP servers | `register [--vault NAME \| --all] [--apply]` |
| Install the REST plugin into a vault that lacks it | `enable-plugin [--vault NAME \| --all] [--apply]` |
| Check a code-graph vault's graph output | `graph-health [--vault NAME] [--fix]` |

`--json` is available on the read-only subcommands only. `graph-health` takes
`--fix`, not `--apply`.

The commands are thin wrappers over these: `/obsidian-vault:doctor` diagnoses
and never writes, `/obsidian-vault:repair` fixes ports, reloads, and registers,
`/obsidian-vault:install` brings a plugin-less vault onto the bridge. Reach for
those before typing a fix.

If `python` is not on PATH, try `python3` then `py`. Git Bash on Windows ships
without `python3`.

## 1. Resolve the vault

An explicit path given to the command always wins. Otherwise:

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" scan --json
```

`scan` reads both sources - `~/.claude/obsidian/config.json` and Obsidian's own
registry - and reports every vault on the machine, including ones config has
never heard of. Do not re-derive that by opening the registry file yourself.

Three things `scan` cannot decide for you:

1. **Whether this is a re-run.** A vault already in config is being updated, not
   set up. Say which, and do not overwrite its settings without showing the diff.
2. **Which vault is default.** Exactly one, and it is a choice, not a detection.
3. **Where to create a vault when nothing resolves.** Ask. Never invent a path -
   a wrong default silently pointed a hook at the wrong directory is how the
   personal version of this plugin's hooks used to fail for anyone else who
   installed them.

A vault that `scan` lists but config does not is a real vault with real bound
ports and no name this plugin can pass to `--vault`. Give it one with
`/obsidian-vault:init <name> <path>` before anything else can address it.

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

**Downloading the plugin is a manual prerequisite, and nothing here does it.**
An Obsidian community plugin is unsigned `main.js` on a GitHub release, with no
publisher signature and no authoritative checksum, running at Obsidian's own
privilege over every note in the vault - so it comes through Obsidian's own
installer or not at all. In Obsidian, with that vault open: Settings >
Community plugins > turn on community plugins > Browse > Local REST API >
Install. Never place release files by hand either.

`enable-plugin --vault <name> --apply` then enables an already-downloaded
plugin and reads back the key. On a vault whose files are absent it reports
`NOT DOWNLOADED` and stops - that is the prerequisite above, not a failure.
Three things it cannot do, because they are Obsidian's own UI:

1. **Launch the vault once** so `.obsidian/` exists, and once more after the
   plugin is enabled so the plugin generates its `apiKey`. Closing the window is
   not quitting - see Troubleshooting.
2. **Turn community plugins on.** If `.obsidian/community-plugins.json` does not
   exist or is `[]`, ask the user to confirm "Turn on community plugins" in
   Settings > Community plugins. Claude cannot click through that dialog.

The key lives in `.obsidian/plugins/obsidian-local-rest-api/data.json`. Read it;
never generate or guess one.

## 4. Register the MCP server - one per vault

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" register --vault <name> --apply
```

That is the whole step. It registers `obsidian-<name>` against that vault's HTTP
port with that vault's current key. Run it again after any port change or key
rotation - "key rejected, and it used to work" is always one of those two.

**Point the MCP server at the HTTP port.** The HTTPS side uses a self-signed
certificate; Claude Code's Node HTTP client rejects it with
`DEPTH_ZERO_SELF_SIGNED_CERT` and there is no clean way to trust it from this
side. `curl -k` reaches that same port happily, so a green `curl -k` proves the
vault is serving and proves nothing about whether MCP will connect. Do not
repoint a server at HTTPS because `curl -k` worked.

**Read both ports from the file; do not derive one from the other.** In
`data.json`, `port` is the HTTPS port and `insecurePort` is the HTTP one, and
they are whatever that vault was configured with - not an offset of each other.
On the machine this plugin was written against: memory is HTTPS 27124 / HTTP
27123, codegraphs 27128 / 27125, anew-codegraph 27126 / 27127. In
`~/.claude/obsidian/config.json` the key `port` means the **HTTP** port, the
opposite of what the same word means in `data.json`. Two files, one word, two
meanings - check which file you are reading.

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

`port` here is that vault's **HTTP** port - the value its `data.json` calls
`insecurePort`. The same word means the HTTPS port in `data.json`. Copy it from
the file, never from the other file's `port`.

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

Do not report success because the steps ran.

```
python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" diagnose
```

Exit 0 and every vault healthy is the only success. Exit 1 means it found
something; read the verdicts, do not re-derive them by hand. `/obsidian-vault:doctor`
is the same call with the verdicts explained.

## Troubleshooting

- **Obsidian looks "up" but the bridge is down.** Obsidian reads its plugin
  list only at launch; closing the window minimizes to the tray rather than
  quitting, so a plugin enabled after launch is not actually loaded. A full
  quit from the tray icon and relaunch is required, not just closing the
  window.
- **HTTP never answers, HTTPS answers with the wrong vault's key, and the
  bridge serves the wrong vault's files.** That is one fault, not three. Two
  vaults declared the same port; one won the bind and the loser's plugin failed
  to start its server at all, taking its HTTP listener down with it. Find it by
  comparing `port` and `insecurePort` across **every** vault's
  `.obsidian/plugins/obsidian-local-rest-api/data.json` - including vaults that
  `~/.claude/obsidian/config.json` has never heard of, because an unconfigured
  vault still binds ports. Then run `/obsidian-vault:repair fix-ports`.

  Do not reach for `enableInsecureServer`. On the machine that hit this, that
  flag was already `true` on every vault; the collision kills the server before
  either listener starts, so the flag has nothing to gate.
- **The plugin disagrees with its own `data.json`.** It reads that file only at
  load. Any edit needs an Obsidian window reload before it takes effect, so a
  stale instance is wrong about both the port and the API key at once - and a
  probe of it reports something true of neither. `/obsidian-vault:repair reload`
  (Obsidian's own `app:reload`), or a full quit and relaunch if that does not
  take.
- **Key rejected after previously working.** The key in that vault's
  `data.json` no longer matches what its MCP server has. Run
  `/obsidian-vault:repair register`; it re-registers from the current key.
- **A second vault's bridge only answers while that vault's Obsidian window is
  actually open.** Unlike a single-vault setup, running two vaults commonly
  means running two Obsidian windows (or opening the second one only when
  needed) - `/obsidian-vault:doctor` reporting one vault down while another is
  up is expected, not a misconfiguration, if only one window is open.
- **A vault with no REST plugin at all** has nothing to repair - no `data.json`
  to compare, no key to register. `/obsidian-vault:install` is the command for
  that one.
