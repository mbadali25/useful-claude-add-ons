# settings.json keys that change default behavior

This is a curated subset — the keys people actually reach for. The full table (with per-key minimum versions) lives at `https://code.claude.com/docs/en/settings`. If a key matters and you're unsure it exists in their version, check there rather than writing it from memory; this surface ships new keys constantly.

Interactive alternative worth mentioning: `/config` opens a tabbed settings UI, and newer versions accept `/config key=value` directly.

## Model and reasoning

| Key | Notes |
|---|---|
| `model` | Default model, e.g. `"claude-sonnet-5"`. Read at session start — use `/model` to switch mid-session. `--model` and `ANTHROPIC_MODEL` override for one session. |
| `fallbackModel` | Ordered chain to fall back to when the primary is overloaded, e.g. `["claude-sonnet-5", "claude-haiku-4-5"]`. Capped at three. Unusually, this does *not* merge across files — the highest-precedence file that defines it supplies the whole chain. |
| `alwaysThinkingEnabled` | Extended thinking on by default. Usually set via `/config`. |
| `effortLevel` | Persist effort across sessions: `"low"`, `"medium"`, `"high"`, `"xhigh"`. Written automatically by `/effort`. |
| `availableModels` | Restrict the model picker, e.g. `["sonnet", "haiku"]`. Mainly a managed-settings tool. |
| `modelOverrides` | Map model IDs to provider-specific IDs (Bedrock inference profile ARNs, etc.). |

## Autonomy and friction

| Key | Notes |
|---|---|
| `permissions` | The big one — see `references/permissions.md`. |
| `autoCompactEnabled` | Default `true`. Auto-compact as context fills. |
| `fileCheckpointingEnabled` | Default `true`. Snapshots files before each edit so `/rewind` can restore them. Leave this on. |
| `askUserQuestionTimeout` | Default `"never"`. Idle time before an unanswered question dialog auto-continues: `"60s"`, `"5m"`, `"10m"`, `"never"`. User settings only. |
| `disableAutoMode` | Set to `"disable"` to remove auto mode from the Shift+Tab cycle. |

## Instructions and memory

| Key | Notes |
|---|---|
| `autoMemoryEnabled` | Default `true`. Set `false` per-project to stop Claude taking notes on that repo. |
| `autoMemoryDirectory` | Relocate auto memory. Absolute or `~/`-prefixed. |
| `claudeMdExcludes` | Globs of CLAUDE.md files to skip — the monorepo escape hatch. Arrays merge across layers. Managed policy files can't be excluded. |
| `claudeMd` | **Managed settings only.** CLAUDE.md content inline in the policy file. Ignored in user/project/local. |
| `outputStyle` | Swaps part of the system prompt. Read at session start — needs `/clear` or a restart. |
| `includeGitInstructions` | Default `true`. Set `false` to drop the built-in commit/PR instructions and git status snapshot, e.g. when using your own git skills. |

## Interface

| Key | Notes |
|---|---|
| `editorMode` | `"normal"` or `"vim"` for the prompt input. |
| `language` | Preferred response language, e.g. `"japanese"`. Also drives voice dictation and session titles. |
| `autoScrollEnabled` | Follow output to the bottom in fullscreen rendering. |
| `awaySummaryEnabled` | One-line recap when you come back after a few minutes away. |
| `emojiCompletionEnabled` | `:shortcode:` suggestions in the input. |
| `axScreenReader` | Flat, screen-reader-friendly output with no decorative borders or animation. |
| `attribution` | Customize or blank out git commit and PR attribution: `{"commit": "...", "pr": ""}`. |
| `companyAnnouncements` | Array of startup messages, cycled at random. |

A custom status line is also configurable (`statusLine`); check `https://code.claude.com/docs/en/statusline` for the current schema before writing one.

## Environment and infrastructure

| Key | Notes |
|---|---|
| `env` | Variables applied to every session and to subprocesses. **Do not put secrets here in a committed project file.** |
| `apiKeyHelper` | Command that prints an auth value, sent as `X-Api-Key` and `Authorization: Bearer`. Refresh interval via `CLAUDE_CODE_API_KEY_HELPER_TTL_MS`. |
| `awsAuthRefresh` / `awsCredentialExport` / `gcpAuthRefresh` | Credential refresh scripts for Bedrock and Vertex. |
| `autoUpdatesChannel` | `"latest"` (default) or `"stable"` (~a week behind, skips major regressions). |
| `minimumVersion` | Floor for auto-updates and `claude update`. |
| `cleanupPeriodDays` | Default 30. Age at which session transcripts and app data are deleted at startup. Minimum 1; `0` is a validation error. |
| `enableAllProjectMcpServers` / `enabledMcpjsonServers` / `disabledMcpjsonServers` | Approve or reject MCP servers from `.mcp.json`. |
| `disableClaudeAiConnectors` | Stop claude.ai MCP connectors being auto-fetched. `true` in any scope wins. |

## Hooks

Hooks are shell commands wired to lifecycle events. They're the enforcement layer: unlike CLAUDE.md, they run regardless of what Claude decides.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "npx prettier --write \"$CLAUDE_FILE_PATHS\"" }
        ]
      }
    ]
  }
}
```

That `command` is POSIX shell (`$CLAUDE_FILE_PATHS`, no `shell` key set). On Windows, a bare `command` with no `shell` key goes to Git Bash when Git Bash is installed, and only falls back to PowerShell if Git Bash isn't present — so this single entry already covers most Windows machines, just not ones with neither.

For a hook that has to run under PowerShell specifically — the command is PowerShell syntax, or it must not depend on Git Bash being present — set `"shell": "powershell"` on a second entry for the same event rather than trying to write one command string that works in both shells. **That second registration is not an OS switch — Claude Code does not pick one entry over the other based on the host.** Both entries are attempted on every matching event. On a host with only one of the two shells, the other entry errors (expected, not a bug: a hook registration has no way to know in advance which shell a given machine actually has). On a host with *both* shells — an ordinary Windows dev machine with Git for Windows installed, or, less obviously, any machine with PowerShell 7 (`pwsh`) on PATH, which is cross-platform and installs on macOS and Linux too — **both entries run**, so an unguarded pair like this fires prettier twice per edit wherever both shells exist:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "command": "npx prettier --write \"$CLAUDE_FILE_PATHS\"" }
      ]},
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "shell": "powershell", "command": "npx prettier --write $Env:CLAUDE_FILE_PATHS" }
      ]}
    ]
  }
}
```

Give each command its own flavour guard so only one actually does the work, the way this repo's own PowerShell hook twins guard themselves against firing where `pwsh` exists but the host isn't Windows — `$OS` (POSIX) / `$env:OS` (PowerShell) reads `Windows_NT` on both Windows PowerShell 5.1 and PowerShell 7, and is unset elsewhere:

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "command": "[ \"$OS\" = \"Windows_NT\" ] || npx prettier --write \"$CLAUDE_FILE_PATHS\"" }
      ]},
      { "matcher": "Edit|Write", "hooks": [
        { "type": "command", "shell": "powershell", "command": "if ($env:OS -eq 'Windows_NT') { npx prettier --write $Env:CLAUDE_FILE_PATHS }" }
      ]}
    ]
  }
}
```

The POSIX line (`[ "$OS" = "Windows_NT" ] || ...`) was run directly, with `$OS` unset and then set to `Windows_NT`: it stands down (exit 0, nothing runs) only in the `Windows_NT` case. When it *does* run, the exit status is `npx`'s, not always 0 — a stub `npx` made to `exit 7` left the whole line at exit 7. The PowerShell line encodes the opposite condition directly rather than skipping past it with `||` — `if ($env:OS -eq 'Windows_NT') { ... }` runs the body only on Windows, where the POSIX line's `||` runs its body only off Windows — and it was measured on pwsh 7.6.5 (Linux): the same failing-`npx` case measured exit code 1, not 7, so unlike the POSIX side it does **not** pass a failing command's own exit code through. That's a measured difference, not a guess — don't depend on either exit code for anything beyond success/failure without checking which shell ran it.

- `shell` — on a hook entry, forces that command to run under the named interpreter instead of Claude Code's default OS-shell resolution for a bare `command`. `"powershell"` is the only value this repo's own hook registrations use.
- `PreToolUse` can allow, deny, or modify a call. **Exit code 2 blocks it** — before permission rules are evaluated, so it overrides `allow` rules and `bypassPermissions`.
- `PostToolUse` is where formatters, linters, and test runners go.
- `ConfigChange` fires when a settings file is detected as changed.
- `InstructionsLoaded` logs which instruction files loaded and why — the best tool for debugging path-scoped rules.

Other events exist (session lifecycle, notifications, compaction, stop). Get the current event list and the exact stdin/stdout contract from `https://code.claude.com/docs/en/hooks` before writing anything beyond the two above — don't guess event names.

Related keys: `shell` (see above — per-hook-entry, not global), `disableAllHooks` (kills all hooks and any custom status line), `allowedHttpHookUrls` (URL allowlist for HTTP hooks; empty array blocks all), `httpHookAllowedEnvVars`, and `allowManagedHooksOnly` (managed settings only).

Hooks from a project file are gated behind the workspace trust dialog, since a cloned repo could otherwise ship a command that runs on your machine. Point this out when adding hooks to a shared repo — teammates will see a prompt.

## When edits take effect

Most keys hot-reload into a running session, including `permissions`, `hooks`, and `apiKeyHelper`. Read once at startup: `model` (use `/model`) and `outputStyle` (needs `/clear` or restart).

## Validation behavior differs by scope

- **User, project, local**: strict. A file that fails validation is rejected **as a whole** and reported — one typo silently drops every setting in that file. Always validate JSON after editing.
- **Managed**: tolerant. An invalid entry is stripped with a warning and every remaining valid policy is still enforced, so one typo can't disable an org's whole policy. `/doctor` lists stripped entries with source file and field.

## Verification commands

- `/status` — the **Setting sources** line shows each file that loaded. A file missing from the list didn't parse.
- `/context` — which memory files are actually in context.
- `/doctor` (or `claude doctor`) — resolved settings, invalid entries, and a proposed trim for an oversized checked-in CLAUDE.md.
- `claude --debug` — for when something behaves and nobody knows why.
