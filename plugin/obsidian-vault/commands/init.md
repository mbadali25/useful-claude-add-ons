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
file does not repeat.

Every step below that touches a vault's plugin, ports, or MCP registration is
performed by `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py`, the same script
`/obsidian-vault:doctor`, `repair`, and `install` wrap. It is dry-run by default
and writes only with `--apply`, which is what makes "show the plan, then ask"
possible. Exit 0 healthy or applied, 1 problems found, 2 usage error - exit 1
from a dry run is a successful diagnosis, not a crash. If `python` is not on
PATH, try `python3` then `py`, and say which one worked; Git Bash on Windows
ships without `python3`.

In outline, so you know the shape before you load the skill:

1. **Resolve the vault.** $2 if given. Otherwise:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" scan --json
   ```
   `scan` reads both config and Obsidian's own registry and reports every vault
   on the machine, including ones config has never heard of. Do not open the
   registry file yourself. Three things it cannot decide: whether this is a
   re-run (a vault already in config is being updated - show the diff, do not
   overwrite silently), which vault is default (a choice, not a detection), and
   where to create a vault when nothing resolves. Ask rather than invent a path
   - a hook silently pointed at the wrong directory is how the personal version
   of this plugin used to fail for everyone else. For a second or later named
   vault there is nothing to detect from - always ask.
2. **Install Obsidian if it is missing.** `winget install Obsidian.Obsidian` on
   Windows; on Linux, detect the package manager and offer the Flatpak
   (`flatpak install flathub md.obsidian.Obsidian`) or point at the AppImage -
   there is no universal package name across distros, so ask rather than guess.
3. **Name the vault in config, before anything addresses it by name.** Every
   step below takes `--vault <name>`, and a vault config has never heard of is
   discovered under its *directory basename*. If the chosen name differs from
   the folder - `thd` for `claude-anew-thd-codegraph` - every one of those steps
   fails with "unknown vault" until the entry exists. So write it first:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" add-vault --name <name> --path <path>
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" add-vault --name <name> --path <path> --apply
   ```
   Add `--layout org/repo` for a code-graph vault and `--default` for the
   primary one. Show the dry run and get a yes before applying.

4. **Download the Local REST API community plugin, then enable it.** The
   download is a **manual prerequisite** and nothing in this plugin fetches it.
   An Obsidian community plugin is unsigned `main.js` on a GitHub release, with
   no publisher signature and no authoritative checksum, and it runs with
   Obsidian's own privileges over every note in the vault - so it is installed
   through Obsidian's own installer, by a person, or not at all.

   In Obsidian, with that vault open: Settings > Community plugins > turn on
   community plugins (this is what leaves Restricted Mode) > Browse > search
   Local REST API > Install. Then let the script enable it and read back the key
   - do not place release files or hand-edit a `data.json`:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name>
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" enable-plugin --vault <name> --apply
   ```
   Show the dry run and get a yes before applying. If the plugin's files are not
   there yet it says `NOT DOWNLOADED` and stops - that is the prerequisite above,
   not a failure to chase. Launching the vault is also Obsidian's own job: once
   so `.obsidian/` exists, again after the plugin is enabled so it generates its
   `apiKey`. Read that key from
   `<vault>/.obsidian/plugins/obsidian-local-rest-api/data.json`; never
   generate or guess one.

   Then check this vault's ports against every other vault's, before anything
   is registered against them:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" fix-ports --vault <name>
   ```
   Exit 0 means no collision and nothing to apply. Exit 1 means this vault
   duplicates a port another vault already declares - show the plan, get a yes,
   run it again with `--apply`, then `reload` that vault's window so the live
   plugin picks up the change. Do not choose ports yourself. Local REST API is
   per-vault: it answers only while that vault is open in its own Obsidian
   window, on that instance's own ports.
5. **Register one MCP server per vault**, never one server multiplexing two
   vaults - the bridge is per-port, so a single server config cannot serve
   both anyway:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" register --vault <name> --apply
   ```
   That is the whole step. It names each server `obsidian-<vault-name>` so
   multiple vaults never collide, and points it at that vault's HTTP port with
   that vault's current key. Run it again after any port change or key
   rotation - "key rejected, and it used to work" is always one of those two.

   **Read both ports from the vault's own `data.json`; derive neither from the
   other.** There `port` is the HTTPS port and `insecurePort` is the HTTP one,
   and they are whatever that vault was configured with. On this machine memory
   is HTTPS 27124 / HTTP 27123, codegraphs 27128 / 27125, anew-codegraph 27126
   / 27127 - HTTPS *below* HTTP. There is no arithmetic relating them. The MCP
   server goes on the HTTP port: the HTTPS side is self-signed and Claude
   Code's Node client rejects it, so a green `curl -k` proves the vault is
   serving and proves nothing about whether MCP will connect.
6. **Complete the config entry** that step 3 created. The full shape is:
   ```json
   {
     "vaults": {
       "<name>": { "path": "<resolved path>", "port": <http port>,
                   "layout": "<optional, e.g. 'org/repo'>", "default": true }
     },
     "guard": { "asciiOnly": false, "requireFrontmatter": false, "checkCanvas": true }
   }
   ```
   `add-vault` wrote `path`, and `--port`/`--layout`/`--default` if you passed
   them; the `guard` block and anything you skipped is typed here. Re-running
   `add-vault --apply` merges into the existing entry rather than replacing it,
   so either route is fine.
   `port` here is the **HTTP** port - the value that vault's `data.json` calls
   `insecurePort`. The same word means the HTTPS port in `data.json`, so check
   which file you are copying from.

   Set `default: true` on exactly one vault - the first one configured, unless
   told otherwise. Only that vault gets the ASCII/frontmatter/canvas guard,
   the capture-to-inbox hook, and env-var/detection fallback; a second vault
   (particularly a generated one like a code-graph vault, which nobody
   hand-authors frontmatter into) is deliberately not guarded the same way -
   see the `obsidian-memory-contract` skill for why. Set `guard` toggles from
   what the *default* vault's own `CLAUDE.md` states (ASCII-only, required
   frontmatter keys) - detected, never assumed.
7. **Note a vault's `layout`** if it has a structural convention worth other
   commands knowing - a code-graph vault laid out `<org>/<repo>/` should
   record `"layout": "org/repo"` so `/obsidian-vault:graph` addresses it
   correctly instead of guessing crew's own `codegraphs/<repo>/` default.
8. **Confirm with `diagnose`**, for every vault just configured:
   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/vault_ops.py" diagnose --vault <name>
   ```
   Report what it returned, not that the steps ran. `/obsidian-vault:doctor`
   explains the verdicts if one needs translating.
9. **Companions.** Offer each of the following as its own yes/no - never a
   batched "install all three." State what it adds and the exact command
   before asking; skip an item with a one-line note if its check fails (e.g.
   its marketplace is unreachable), and never add a marketplace or install a
   plugin without that item's own yes.
   - **`obsidian@obsidian-skills`** (kepano's plugin - install item 18 in this
     repo's own install script; the plugin this one is named `obsidian-vault`
     specifically to avoid colliding with). Check `claude plugin marketplace
     list` for `obsidian-skills` and `claude plugin list` for
     `obsidian@obsidian-skills` before offering; skip with a note if the
     marketplace list itself fails (unreachable). Say exactly: "Ours is
     infrastructure (bridge, multi-vault MCP, memory contract, automation);
     his is workflow skills for working inside Obsidian (markdown
     conventions, bases, canvas JSON, templates) - complementary, not
     overlapping." If accepted:
     ```
     claude plugin marketplace add kepano/obsidian-skills
     claude plugin install obsidian@obsidian-skills
     ```
     (skip the `marketplace add` if it is already listed).
   - **`graphify`** - `/obsidian-vault:graph` depends on it and cannot run
     without it. Check `graphify --version`; if missing, offer to install it
     the way this repo's own install script does (item 20): `uv tool install
     graphifyy` (package is `graphifyy`, double-y; the CLI it installs is
     `graphify`), then `graphify install --project` from inside the target
     repo.
   - **`crew@useful-claude-add-ons`** - mention only when the vault being
     configured will hold ticket boards or code-graph output (a `layout` was
     just set, or the user said as much). One line, not a pitch: "crew 0.10+
     has the Obsidian Kanban tracker, and 0.11+ exports graphs into an
     org/repo-layout vault." If accepted: `claude plugin install
     crew@useful-claude-add-ons` (same marketplace as this plugin, so no
     `marketplace add` step).

Never overwrite an existing `~/.claude/obsidian/config.json` silently - read it
first, show what would change, and confirm before writing over a value the
user already set. Adding a second vault means merging a new key into
`vaults`, never replacing the block.
