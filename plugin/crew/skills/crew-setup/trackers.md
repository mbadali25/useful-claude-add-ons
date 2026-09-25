# Trackers

_Extracted from `SKILL.md` to keep the main file under the
500-line progressive-disclosure limit. Nothing was changed in the
move._

## 3b. Jira only — wire the MCP connector

Only if the user chose Jira. Do NOT do this in files-mode repos.

1. Copy `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/templates/mcp.json` to the repo
   root as `.mcp.json`, or merge it into an existing one. It uses the `/v1/mcp`
   HTTP endpoint — the older `/v1/sse` endpoint was retired mid-2026.
2. Tell the user to run `/mcp`, approve the server, and authenticate. A
   project-scope `.mcp.json` requires explicit approval; it will not connect silently.
3. Once connected, fetch the accessible cloud resources ONCE and write `cloudId`
   and the project key into `.crew/config.json` under `jira`. Never look them up again.
4. Set `tracker: "jira"` and create `.work/cache/`.

**Why per-repo, not bundled in the plugin.** A plugin-level `.mcp.json` connects
Atlassian in every repo where the plugin is enabled, including the ones tracking
work in files. Claude Code defers MCP tool definitions once they grow large, so
the standing context cost is smaller than it once was — but the auth prompts, the
connection, and the temptation to call the API mid-task all remain. Connect it
only where Jira is actually the source of truth.

Note: plugin-shipped agents cannot declare `mcpServers` in frontmatter, for
security reasons. Jira access therefore lives at session level. If Jira calls
should be isolated in their own context window, that agent must live in
`~/.claude/agents/` outside this plugin.

## 3c. ServiceDesk Plus only — confirm the connector, then write two settings

Only if the user chose ServiceDesk Plus.

1. Confirm the `sdp_*` tools are reachable, searching for them first if tool
   search is active. Then call `sdp_whoami` once: it proves the connection is
   live and names the account whose audit trail every write will land under.
   Crew does not ship an `.mcp.json` for this - the SDP connector is normally
   registered at user or session scope, and a per-repo one would prompt for
   approval in every repository the plugin is enabled in.
2. Set `tracker: "sdp"` and create `.work/cache/`.
3. Write the two settings that are decisions rather than lookups, and say what
   each means before writing it:
   - `sdp.noteVisibility` - `"private"` (the default) keeps crew's push note off
     the requester-visible thread. `"public"` only where the requester is an
     engineer who wants it.
   - `sdp.closeOnDone` - `false` (the default) means crew transitions a request
     and leaves closure to whoever owns the queue. `true` only for a queue that
     is genuinely the user's.
   `sdp.portal` stays `null` unless the connector serves more than one instance.

Tell them the local key is `SDP-<id>`, not the bare request number: the rest of
crew - `/crew:status`, `/crew:implement`, the index - recognises a ticket by its
`LETTERS-digits` shape, and a bare number is invisible to all of it.

## 3d. Obsidian Kanban only — resolve the vault, then create the board

Only if the user chose an Obsidian Kanban board. There is no connector to probe
here, so the setup work is different in kind: it is proving a directory exists
and creating one file correctly.

1. Resolve the vault. Ask for the path, then confirm it exists and contains a
   `.obsidian/` directory. A path that is merely a folder of markdown files
   works for `memory`, but a Kanban board needs the plugin, which lives in the
   vault. If `.obsidian/plugins/obsidian-kanban/` is absent, say so - the board
   file will still be written correctly, it will just render as plain markdown
   until they install the plugin from Community Plugins.
2. Write `obsidian.vaultPath`. Leave it `null` only if it is the same vault as
   `memory.vaultPath`, which the sync command falls back to.
3. Write `obsidian.boardDir` as `Boards/<repo-name>` unless the user wants
   somewhere else. One folder per repo, holding the board and its ticket notes,
   so cards can be `[[T-0042]]` wikilinks that resolve and the graph view is
   useful. A single shared board across repos is possible and is not the
   default - lanes get crowded and cross-repo tickets mix.
4. Create the board file, `<boardDir>/<board>`, with the five lanes. Get the
   format right the first time; the three load-bearing parts are the
   frontmatter, the trailing settings block, and the `**Complete**` marker:

````markdown
---

kanban-plugin: board

---

## Backlog


## Ready


## In Progress


## Review


## Done

**Complete**




%% kanban:settings
```
{"kanban-plugin":"board"}
```
%%
````

5. Set `tracker: "obsidian"` and create `.work/cache/`.

Say two things plainly before finishing:

- **The vault is the remote, and crew does not commit it.** The board and the
  ticket notes live outside the repo, so ticket state does not travel with a
  branch and is not on a colleague's machine. That is the trade for being able
  to drag a card. If the vault is its own git repo, its history is theirs to
  manage.
- **Dragging a card is how status changes.** On pull the lane wins; on push
  crew writes the lane. `/crew:obsidian-sync` is the only thing that should
  touch the board, and only at pickup and completion.

