---
name: claude-code-tuneup
description: >
  Audit a Claude Code installation for what is making it slow, bloated, or unpredictable -
  duplicate skills loaded twice, hooks firing on every tool call, SessionStart hooks
  injecting context before you type, plugins installed but disabled, overlapping MCP
  servers, oversized CLAUDE.md and rules files, marketplaces still being refreshed for
  plugins you removed - then hand back a ranked cleanup plan with the exact command per
  item. Use this skill whenever the user says Claude Code feels slow, sluggish, laggy, or
  heavy; that startup takes forever; that it compacts too early or runs out of context too
  fast; that the wrong skill keeps firing or a skill fires twice; that they have too many
  plugins/skills/agents/MCP servers and want to know what to remove; or asks to audit,
  review, clean up, slim down, tune, or de-duplicate their Claude Code setup, settings.json,
  hooks, plugins, or ~/.claude directory. Also use it when a hook is suspected of erroring
  on every command, when `/context` or `/status` looks fuller than expected, or after
  running an install script that added a batch of plugins and marketplaces at once.
---

# Diagnose a slow or bloated Claude Code setup

Claude Code performance problems are almost always one of four things, and they are all
measurable from disk without guessing:

| Symptom | Usual cause | Where it shows |
|---|---|---|
| Slow to start; slow after `/clear` | `SessionStart` hooks, marketplace refresh | hook count per event, marketplace count |
| Every Bash/Edit call has a lag | `PreToolUse`/`PostToolUse` hooks spawning processes serially | hooks with a `Bash` matcher |
| Compacts early, context feels small | preloaded skill descriptions, CLAUDE.md, agent listings, MCP tool schemas | the context budget table |
| Wrong skill fires, or a skill appears twice | the same skill installed as a loose copy *and* a plugin, or published by two marketplaces | duplicate-skill findings |

This skill is **read-only until the user approves**. Never delete a skill directory,
uninstall a plugin, or rewrite `settings.json` on your own initiative — produce the plan,
get a yes, then act.

## Step 1 — Run the audit

```bash
python scripts/cc_audit.py                     # ranked findings, user scope + cwd
python scripts/cc_audit.py --project /path/to/repo
python scripts/cc_audit.py --min-severity med  # skip the LOW noise
python scripts/cc_audit.py --json              # when you want to post-process
```

Stdlib-only Python 3.8+, no install step, and it writes nothing. It inventories:

- every settings file in scope (`~/.claude/settings.json`, `settings.local.json`, the
  project's `.claude/settings.json` and `.local.json`) and reports any it cannot parse —
  an unparseable settings file is silently ignored by Claude Code, so everything in it is
  inert;
- loose skills in `~/.claude/skills/` vs skills provided by installed plugins, in both
  plugin layouts (`skills/<name>/SKILL.md` and a plugin whose root *is* the skill);
- `enabledPlugins`, so a duplicate that is disabled is not reported as a live one;
- hooks from settings *and* from every plugin's `hooks/hooks.json`, grouped by event;
- subagents, rules files, `CLAUDE.md` sizes, MCP servers, marketplaces, plugin cache.

## Step 2 — Read the findings in this order

1. **HIGH duplicate skills.** Two copies of one skill means two descriptions in context
   every session and an ambiguous invocation. The plugin copy is the one that updates from
   its marketplace; the loose copy in `~/.claude/skills/` never updates. Removing the loose
   copy is the fix. Confirm the plugin is enabled before deleting anything.
2. **HIGH broken hooks.** A hook whose script no longer exists still spawns a process on
   every matching tool call and fails. This is pure latency for zero function.
3. **MED per-tool-call hooks.** Count the hooks with a `Bash` matcher: they run serially in
   front of every shell command. On Windows, each one that shells out to `bash.exe` pays
   Git Bash startup (~100–300 ms) per call.
4. **MED SessionStart hooks.** Anything they print is injected into the session before the
   user's first message. Two is usually deliberate; ten is an accident.
5. **The context budget table.** Skill *descriptions* are always resident — that is how
   Claude decides whether to invoke a skill — so the only lever is installing fewer skills.
   Bodies (`references/`) are read on demand and cost nothing until used.
6. **MED disabled-but-installed plugins.** These are the safest thing to remove: the user
   has already decided they don't want them, and each still gets fetched and refreshed.

## Step 3 — Reference map

| Question | Read |
|---|---|
| What does each finding actually cost, and how do I verify it in-session? | `references/symptoms.md` |
| What is loaded into context before I type, and how do I shrink it? | `references/context-budget.md` |
| Exact commands to remove a plugin, marketplace, loose skill, hook, MCP server | `references/cleanup.md` |

## Step 4 — Propose, then act

Present findings as a table: severity, what it is, what it costs, the one-line fix. Then
split them into three groups and let the user pick per group:

- **Safe now** — uninstall disabled plugins, delete loose skill copies that duplicate an
  enabled plugin, remove marketplaces with no remaining installed plugins, fix broken hook
  paths.
- **Needs a decision** — two plugins that overlap in function (two browser stacks, two
  memory layers, two PowerPoint paths). The audit reports the overlap; only the user knows
  which one they actually use.
- **Behavioural** — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, output caps, hook consolidation.
  Explain the trade-off rather than recommending a number blindly.

Then verify in-session, because disk state is not the whole story:

- `/context` — what is actually loaded, including which memory files were picked up.
- `/status` — which config sources and plugins resolved.
- `/doctor` — resolved settings and any entries Claude Code stripped as invalid.

Re-run `cc_audit.py` after the cleanup and show the before/after counts.

## Safety rails

- **Never delete without an explicit yes**, and echo the full path in the confirmation.
  `~/.claude/skills/<name>/` can contain a skill the user wrote by hand — check whether the
  loose copy differs from the plugin's before calling it redundant (`diff -r`).
- **Uninstall beats disable** for something the user is done with: a disabled plugin still
  has its marketplace refreshed. But disable first when unsure — it is reversible in one
  command.
- **Back up `settings.json` before editing it** (`cp settings.json settings.json.bak`) and
  patch the minimum text rather than round-tripping through a JSON formatter, which
  reflows the whole file and produces an unreadable diff.
- **Do not remove a marketplace that still has an installed plugin** — the plugin loses its
  update path and reports as unresolved.
- `permissions`, `hooks`, and `env` hot-reload into a running session; `model` and
  `outputStyle` do not. Tell the user which of their changes needs a restart.

## Related

`claude-code-defaults` covers *configuring* Claude Code — writing `settings.json`,
permission rules, hooks, and choosing the right scope. Use that one to make a change; use
this one to find out what to change.
