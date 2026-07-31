# Starting configurations

Adapt these — don't paste them verbatim. Swap the toolchain for whatever the inventory actually found. An npm allowlist in a Python repo is a tell that nobody looked.

---

## 1. Solo developer — sane personal defaults

`~/.claude/settings.json`. Applies everywhere, committed nowhere.

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git add *)",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(rg *)",
      "Bash(make *)"
    ],
    "ask": [
      "Bash(git push *)",
      "Bash(gh pr merge *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(~/.ssh/**)",
      "Read(~/.aws/credentials)",
      "Bash(rm -rf *)",
      "Bash(git push --force *)",
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(* | bash)",
      "Bash(* | sh)"
    ]
  },
  "fileCheckpointingEnabled": true,
  "autoUpdatesChannel": "stable"
}
```

The reasoning to explain when handing this over: `acceptEdits` removes the friction that makes people reach for `--dangerously-skip-permissions`, while shell commands still stop. The deny list is a safety net that no project can switch off, because deny beats allow across every scope. Push is in `ask` rather than `deny` because it's a normal thing to do — it just deserves a look.

Paired `~/.claude/CLAUDE.md` — keep it genuinely personal, since it loads in every repo:

```markdown
# Personal preferences

- Explain the plan before large refactors; small fixes can go straight to the edit.
- Prefer editing existing files over creating new ones.
- Match the surrounding code style rather than my general preferences.
- Don't add comments that restate what the code already says.
- When a command fails, show me the actual error before proposing a fix.
```

---

## 2. Shared repo — committed team config

`.claude/settings.json`, committed. This is policy that travels with the code, so keep personal taste out of it.

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(pnpm install)",
      "Bash(pnpm run lint *)",
      "Bash(pnpm run test *)",
      "Bash(pnpm run build)",
      "Bash(pnpm typecheck)"
    ],
    "ask": [
      "Bash(pnpm run migrate *)",
      "Bash(git push *)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Edit(./src/generated/**)",
      "Edit(./.github/workflows/**)",
      "Bash(pnpm publish *)"
    ]
  },
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command", "command": "pnpm prettier --write \"$CLAUDE_FILE_PATHS\"" }
        ]
      }
    ]
  }
}
```

Two things to flag to whoever ships this:

- Teammates will see a **workspace trust prompt** the first time, because the file contains hooks. That's expected; tell them in the PR description so it doesn't look like something went wrong.
- Anyone who needs a personal exception uses `.claude/settings.local.json` rather than editing the committed file. Their allow rules merge in; the team's deny rules still hold.

Add to the repo's `.gitignore`:

```
.claude/settings.local.json
CLAUDE.local.md
```

Then a project `CLAUDE.md` (see `references/claude-md.md` for the shape) and, if the repo is large, `.claude/rules/` with path-scoped frontmatter so instructions load only where they apply.

---

## 3. Locked down — regulated or production-adjacent

`.claude/settings.json`, or better, managed settings so it can't be edited. Read-only by default; nothing runs unless it's on the list.

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "defaultMode": "default",
    "allow": [
      "Bash(python -m pytest *)",
      "Bash(ruff check *)",
      "Bash(git status)",
      "Bash(git diff *)"
    ],
    "ask": [
      "Bash(git commit *)"
    ],
    "deny": [
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(ssh *)",
      "Bash(scp *)",
      "Bash(aws *)",
      "Bash(kubectl *)",
      "Bash(terraform apply *)",
      "Bash(terraform destroy *)",
      "Bash(psql *)",
      "Bash(rm -rf *)",
      "Bash(sudo *)",
      "Bash(* | bash)",
      "Bash(* | sh)",
      "Read(./.env*)",
      "Read(**/secrets/**)",
      "Read(~/.ssh/**)",
      "Read(~/.aws/**)",
      "Read(~/.kube/**)",
      "Edit(./.github/workflows/**)",
      "Edit(./infra/**)"
    ],
    "additionalDirectories": []
  },
  "disableClaudeAiConnectors": true
}
```

Where this needs to be genuinely airtight rather than merely tidy: string patterns can't express "except when", so pair it with a `PreToolUse` hook that inspects the command. And say plainly that permission rules are a guardrail against accidents and drift, not a sandbox — if the threat model includes a determined adversary rather than a distracted engineer, the answer is isolation (containers, scoped credentials, no prod access from the dev machine), not a longer deny list.

---

## 4. Fleet rollout — managed settings

Managed scope can't be overridden by users or projects, so it's the only place to put policy that has to hold. Same JSON format as any other settings file.

**Delivery options:**

| Platform | Mechanism |
|---|---|
| macOS | `com.anthropic.claudecode` managed preferences domain (Jamf, Kandji/Iru, any MDM), or `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Windows | `HKLM\SOFTWARE\Policies\ClaudeCode`, `Settings` value containing JSON (Group Policy or Intune), or `C:\Program Files\ClaudeCode\managed-settings.json` |
| Linux / WSL | `/etc/claude-code/managed-settings.json` |
| Any (remote) | Server-managed settings delivered at sign-in via the claude.ai admin console |

The legacy Windows path `C:\ProgramData\ClaudeCode\managed-settings.json` stopped working in v2.1.75 — migrate anything still there.

**Drop-in fragments.** Alongside `managed-settings.json`, a `managed-settings.d/` directory lets separate teams ship independent policy without fighting over one file. Merge follows systemd convention: base file first, then `*.json` sorted alphabetically. Scalars override, arrays concatenate and de-duplicate, objects deep-merge. Use numeric prefixes (`10-telemetry.json`, `20-security.json`) to control order.

**Typical managed policy:**

```json
{
  "permissions": {
    "deny": [
      "Read(~/.ssh/**)",
      "Read(~/.aws/credentials)",
      "Bash(sudo *)",
      "Bash(* | bash)"
    ]
  },
  "claudeMd": "Never commit credentials. Customer data stays in approved systems — don't paste it into prompts or commit it to repos.",
  "forceLoginMethod": "claudeai",
  "forceLoginOrgUUID": "REPLACE-WITH-ORG-UUID",
  "disableAutoMode": "disable",
  "minimumVersion": "2.1.100",
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp"
  },
  "companyAnnouncements": [
    "Claude Code use is governed by the AI tooling policy — see the intranet."
  ]
}
```

Managed-only keys worth knowing for a rollout: `allowManagedPermissionRulesOnly` (users and projects can't define any rules), `allowedMcpServers` / `deniedMcpServers` / `allowManagedMcpServersOnly`, `allowManagedHooksOnly`, `disableSideloadFlags` (rejects `--plugin-dir`, `--plugin-url`, `--agents`, `--mcp-config`), `strictKnownMarketplaces`, `blockedMarketplaces`, and `forceRemoteSettingsRefresh` (fail closed at startup if managed settings can't be fetched).

**Before deploying fleet-wide**, run `claude doctor` on one test machine. Managed settings parse tolerantly — an invalid entry is stripped with a warning rather than taking the whole policy down — and `doctor` lists exactly which entries were dropped and why. `requiredMinimumVersion` and `requiredMaximumVersion` deliberately fail open, so a bad push can't stop Claude Code from starting.

Anthropic publishes starter deployment templates for Jamf, Kandji/Iru, Intune, and Group Policy at `https://github.com/anthropics/claude-code/tree/main/examples/mdm`.

Note the division of labor: managed **settings** for technical enforcement (blocked commands, sandbox, auth, env), managed **CLAUDE.md** or `claudeMd` for behavioral guidance (code style, data handling reminders). Behavioral guidance in a settings file won't be enforced, and enforcement written as prose in CLAUDE.md isn't enforcement.

---

## Quick path for "just make it better, I don't want to think about it"

1. Write the solo-developer `~/.claude/settings.json` above, adapted to their real toolchain.
2. Run `/init` in their main repo to generate a project CLAUDE.md, then trim what the codebase already makes obvious.
3. Show them three things: `/permissions` to adjust rules, `/config` to change preferences, Shift+Tab to switch permission mode mid-task.
4. Tell them the maintenance habit that matters: when you correct Claude twice on the same thing, that correction belongs in CLAUDE.md; when you approve the same command for the third time, it belongs in the allow list.
