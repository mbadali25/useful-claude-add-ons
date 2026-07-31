---
name: claude-code-defaults
description: Walk someone through configuring how Claude Code behaves by default in the terminal — CLAUDE.md instructions, settings.json, permission allow/deny/ask rules, permission modes, default model and effort, hooks, and which scope (user, project, local, managed) each thing belongs in. Use this skill whenever someone wants to set up, change, review, tidy, or troubleshoot Claude Code's default behavior, including phrasings like "configure Claude Code", "set up my CLAUDE.md", "stop asking me for permission every time", "make Claude always run the tests", "why is Claude ignoring my instructions", "Claude keeps doing X and I want it to stop", "settings.json for Claude Code", "set my default model", "standardize Claude Code for my team", or rolling config out to a fleet with MDM. Use it even when no specific file is named — "I want Claude Code to act differently" is enough to trigger it. Do not use it for one-off in-session requests that don't need to persist.
---

# Configure Claude Code's default behavior

This skill turns a vague wish ("I want Claude Code to stop doing that") into the right edit, in the right file, at the right scope — verified, reversible, and explained.

## The two mechanisms — get this right first

Almost every mistake in this area comes from confusing these:

| | Instructions (context) | Settings (enforcement) |
|---|---|---|
| **Files** | `CLAUDE.md`, `.claude/rules/*.md` | `settings.json`, hooks |
| **How it works** | Loaded into the context window; Claude reads and tries to comply | Enforced by the client regardless of what Claude decides |
| **Reliability** | Strong but not guaranteed | Deterministic |
| **Use for** | Conventions, architecture, "prefer X over Y", tone | Blocking commands, protecting secrets, must-run steps |

If someone says "Claude *must never*" or "Claude *always has to*", a CLAUDE.md line alone is the wrong answer — reach for `permissions.deny` or a `PreToolUse` hook. If they say "Claude should generally", CLAUDE.md is right.

## The four scopes

Picking the wrong scope is the second big failure mode: a personal preference committed to a shared repo, or a team rule that only exists on one laptop.

| Scope | Files | Applies to | Committed? |
|---|---|---|---|
| **Managed** | `managed-settings.json` + `CLAUDE.md` in the system policy dir (or MDM/registry) | Everyone on the machine/org; cannot be overridden | Deployed by IT |
| **User** | `~/.claude/settings.json`, `~/.claude/CLAUDE.md`, `~/.claude/rules/` | Just this person, every project | No |
| **Project** | `.claude/settings.json`, `./CLAUDE.md` or `.claude/CLAUDE.md`, `.claude/rules/` | Everyone on the repo | Yes |
| **Local** | `.claude/settings.local.json`, `./CLAUDE.local.md` | Just this person, just this repo | No (gitignore it) |

Precedence for scalar settings: managed > CLI flags > local > project > user. **Permission rules are different** — `allow`/`ask`/`deny` arrays *merge* across all scopes, and a `deny` anywhere beats an `allow` everywhere. That's a feature: a user-level deny is a safety net no repo can switch off.

On Windows, `~/.claude` means `%USERPROFILE%\.claude`.

## Workflow

### Step 1 — Route the request

Match what they actually want before touching anything:

| They say | Go to |
|---|---|
| "It asks permission for everything" | `references/permissions.md` — allow rules + `defaultMode` |
| "Don't let it touch X / read secrets" | `references/permissions.md` — deny rules, then hooks |
| "It keeps forgetting our conventions" | `references/claude-md.md` |
| "It ignores my CLAUDE.md" | `references/claude-md.md` → troubleshooting section |
| "Change the model / thinking / effort / language / vim keys" | `references/settings-keys.md` |
| "Run the linter after every edit" | `references/settings-keys.md` → hooks section |
| "Set this up for my team / whole fleet" | `references/templates.md` → team + managed sections |
| "Just give me a good starting setup" | `references/templates.md` |

Read only the reference files you need. They're written to be read cold.

### Step 2 — Inventory what's already there

Never write config blind — most people already have some, and silently clobbering it is the worst outcome of this whole workflow.

```bash
claude --version
ls -la ~/.claude/ 2>/dev/null
cat ~/.claude/settings.json 2>/dev/null
cat ~/.claude/CLAUDE.md 2>/dev/null | head -50
ls -la .claude/ 2>/dev/null; cat .claude/settings.json 2>/dev/null
ls CLAUDE.md .claude/CLAUDE.md CLAUDE.local.md 2>/dev/null
```

Version matters: many keys have a minimum version, and the docs mark them. If they're on an older build, say so rather than writing a key that will be ignored.

Also worth running inside a session: `/status` (which sources loaded), `/context` (which memory files actually loaded), `/doctor` (resolved settings, stripped invalid entries).

If you're not on the person's machine and can't read their files, don't guess — ask them to paste the output of the block above, or hand them copy-paste-ready snippets and say exactly which file each goes in.

### Step 3 — Interview, briefly

Ask only what you can't infer from the inventory and the conversation. Aim for three or four questions, not a form. The ones that actually change the output:

1. **Who is this for** — just you, everyone on this repo, or a whole team/fleet? (→ scope)
2. **What does Claude do now that annoys you?** Get specific examples — "it reformats files I didn't ask it to touch" is actionable, "be smarter" isn't.
3. **What should never happen?** Pushes to main, reading `.env`, `rm -rf`, touching prod, migrations. These become deny rules.
4. **How much autonomy do you want by default?** Prompt every time / auto-approve edits but gate shell / read-only planning. (→ `defaultMode`)
5. **Build, test, and lint commands** — the everyday commands that shouldn't need approval, and the ones Claude should run before claiming it's done.

If they explicitly said "just give me sane defaults", skip the interview, pick the solo-developer template from `references/templates.md`, and tell them what you assumed.

### Step 4 — Propose before writing

Show the diff or the proposed file contents, say which file it goes in and why that scope, then write it. For anything already populated, **merge, don't replace** — read the existing JSON, add keys, keep everything else.

Back up first when editing an existing file:

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak-$(date +%Y%m%d%H%M%S)
```

Include the schema line in any `settings.json` you create, so their editor autocompletes and validates it:

```json
{ "$schema": "https://json.schemastore.org/claude-code-settings.json" }
```

Then validate — a settings file that fails to parse is rejected *as a whole* in user/project/local scope, which silently drops every setting in it:

```bash
python3 -m json.tool ~/.claude/settings.json > /dev/null && echo "valid JSON"
```

If you created `.claude/settings.local.json` or `CLAUDE.local.md` by hand, add them to `.gitignore` yourself — Claude Code only does that automatically when it writes the file itself.

### Step 5 — Verify and hand off

Confirm it loaded rather than assuming:

- `/status` → the **Setting sources** line lists each file that loaded. A file with broken JSON won't appear at all.
- `/context` → **Memory files** lists the CLAUDE.md files actually in context.
- `/doctor` → flags invalid or stripped entries with their source file and field.

Most keys hot-reload into a running session, including `permissions` and `hooks`. Two don't: `model` (use `/model` mid-session) and `outputStyle` (needs `/clear` or a restart). Tell them which of their changes needs a restart.

Close with a short summary: what changed, in which files, what to try to confirm it works, and how to undo it (the `.bak` file, or delete the key). Mention `/config` — they can flip most of these interactively later without editing JSON.

## Hard rules

**Never set `bypassPermissions` or recommend `--dangerously-skip-permissions` as a default.** It skips every prompt for the whole session. If someone asks for it, offer the safe version of what they want instead: explicit `allow` rules for their real commands plus `defaultMode: "acceptEdits"`, which gets ~90% of the friction relief while shell commands still stop. If they insist, it's their machine — but say plainly what it turns off and don't write it into a committed project file where it would apply to teammates who never opted in.

**Don't use Bash patterns as network controls.** `Bash(curl https://safe.example.com *)` is trivially bypassed by reordering flags, variables, or redirects. Deny `curl`/`wget` outright and allow specific domains via `WebFetch(domain:...)`.

**Don't put secrets in a committed settings file.** `env` in `.claude/settings.json` goes into git. Tokens belong in the shell environment, `settings.local.json`, or `apiKeyHelper`.

**Don't quietly widen permissions.** Adding `Bash(git *)` to satisfy "let it commit" also allows `git push --force`. Scope rules to what was asked and name the tradeoff out loud.

**Don't inflate CLAUDE.md.** It's loaded into context every single session; every line costs tokens and dilutes the rest. Target under 200 lines. Prefer path-scoped rules in `.claude/rules/` for anything that only matters in part of the tree.

**Verify version-gated keys.** This surface changes fast. If a key matters and you're unsure it exists in their version, check the docs at `https://code.claude.com/docs/en/settings` rather than writing it from memory.

## Reference files

- `references/permissions.md` — rule syntax, the six permission modes, evaluation order, starter allow/deny sets, and when to escalate to a hook.
- `references/claude-md.md` — how CLAUDE.md loads, writing instructions that get followed, `.claude/rules/` and path scoping, imports, AGENTS.md, and troubleshooting "it's ignoring my file".
- `references/settings-keys.md` — the settings.json keys that actually change day-to-day behavior, grouped by intent, plus the hooks basics.
- `references/templates.md` — complete copy-paste starting configs: solo developer, shared repo, locked-down/regulated, and managed fleet rollout.
