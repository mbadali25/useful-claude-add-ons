# AI-Connect Claude Code integration

Extras for Claude Code on top of the AI-Connect MCP server: a plugin with state hooks and the hooks that run the message watcher, and behaviour rules.

## Installation

### 1. Install

`install.sh` (Linux) and `install.cmd` (Windows) do this step through `installer.py claude`; to repeat it alone, e.g. after installing Claude Code later, run `<venv python> installer.py claude` in the AI-Connect directory. It

- registers the **MCP server** (the STDIO client) with `claude mcp add -s user ai-connect`, using this installation's venv: every session joins as `Host:Project`, named after the project Claude Code runs in
- does **not** install the plugin. In this fork the plugin is this whole directory, installed from the useful-claude-add-ons marketplace with `claude plugin install ai-connect@useful-claude-add-ons` (menu row `repo-plugins` in that repo's `install-prerequisites`, off by default). Its `hooks/hooks.json` brings the hooks that run the **message watcher** (session start and every turn end) and the **state hooks**, which call `peer_set_state` on prompt submit and after each tool (busy), on a permission prompt (waiting) and when a turn ends (idle), so other peers see the state in `peer_list` and `peer_notify_when_idle` can tell them when this session is done

The MCP server is registered by the installer rather than shipped in the plugin because its Python lives at a different path on Linux and Windows. Tested with Claude Code 2.1.289; older versions such as 2.1.50 reject the plugin manifest, so check `claude --version` first, and make sure no outdated second `claude` (e.g. an old npm install) comes first in `PATH`. `claude plugin update ai-connect@useful-claude-add-ons` updates the plugin; because the venv lives inside the plugin directory and that directory changes with each version, re-run the installer after an update.

Coming from an earlier setup:

- Remove old command links in `~/.claude/commands/` (`consult.md`, `beratung.md`); the consult command is gone, see the changelog.
- Delete hooks you added by hand for `peer_set_state`, and any hook or rule of your own that tells sessions to start the watcher; the plugin brings them.
- Tool permissions are named `mcp__ai-connect__<tool>`.

### 2. Include the behaviour rules

Add one line to your global `~/.claude/CLAUDE.md` (or a project `CLAUDE.md`):

```markdown
@<absolute-path-to-repo>/integrations/claude-code/CLAUDE.md
```

Claude Code resolves `@` imports when it loads the file. A plugin cannot load such rules itself.

## Usage

### The watcher

The plugin starts the watcher as an `asyncRewake` hook at session start and after every turn (`hooks/watch.sh` on Linux/macOS, `hooks/watch.ps1` on Windows; each stands down on the other's platform so a session never runs two). When a message for the session arrives, it exits with code 2 and Claude Code wakes the session; the session calls `peer_read`. Sessions never start it themselves. One watcher per session, missed messages are reported at once, and it reconnects after a Bridge restart; see the main README. Its hooks set a 7-day timeout: Claude Code otherwise ends asyncRewake hooks after its default 600 s, and an idle session would no longer be woken.
