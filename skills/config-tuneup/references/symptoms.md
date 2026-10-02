# Symptom → cause → how to confirm

Work from the symptom the user reported, not from the longest finding list.

## "Startup is slow" / "it hangs after /clear"

| Cause | Confirm | Fix |
|---|---|---|
| `SessionStart` hooks | `cc_audit.py` groups hooks by event. Each one is a process spawn *and* whatever it prints lands in context. | Drop the hooks you don't read. Note that `/clear` and `/compact` re-fire them — that's why the pause repeats mid-session. |
| Marketplace refresh | Count in the audit header. Each marketplace is a git fetch. | `claude plugin marketplace remove <name>` for any marketplace with no installed plugin left. |
| A hook with no timeout blocking | Look for the "hooks have no timeout" finding. | Add `"timeout": 10` so a wedged hook can't stall the session. |
| Plugin `Setup` hooks | Some plugins (claude-mem, context-mode) run a version check or dependency install on first session. | Expected once per version bump. If it happens every session, the check is failing — run it by hand and read the error. |

Time it directly rather than guessing:

```bash
# Windows PowerShell
Measure-Command { & "C:/Program Files/Git/usr/bin/bash.exe" "$env:USERPROFILE/.claude/hooks/<hook>" }
# Linux/macOS
time ~/.claude/hooks/<hook> </dev/null
```

Anything over ~150 ms in a `PreToolUse` hook is felt on every single tool call.

## "Every command feels laggy"

`PreToolUse` and `PostToolUse` hooks run **serially** before/after the matching tool call.
Five hooks on the `Bash` matcher at 200 ms each is a second added to every shell command.

Confirm by counting the `Bash`-matcher hooks in the audit, then:

- consolidate them into one dispatcher script that does all the checks in one process;
- on Windows, prefer `node` or `pwsh` over `bash.exe` for hot hooks — Git Bash startup is
  the single most expensive part of a trivial hook;
- narrow the matcher. A hook that only cares about `git` commands should not run on every
  `Bash` call if the check can live inside one dispatcher instead.

## "It compacts too early" / "context fills up immediately"

Two different problems that look the same:

1. **The window starts full.** Preloaded content: `CLAUDE.md` (user + project), every
   `.claude/rules/*.md` that matched, every installed skill's `description`, every
   subagent's name and description, and every MCP server's tool schemas. See
   `context-budget.md`.
2. **Autocompact fires low.** `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` below ~70 compacts often;
   each compaction is a summarisation round trip that costs latency and loses detail.

Confirm with `/context` in a fresh session — it breaks down what is resident and lists the
memory files actually loaded. Compare that against the audit's budget table; a mismatch
means a rules file didn't match its `paths:` glob, or a `CLAUDE.md` you expected wasn't
found.

## "The wrong skill keeps firing" / "a skill appears twice"

Duplicate installs. Three shapes:

| Shape | Example | Fix |
|---|---|---|
| Loose copy + plugin | `~/.claude/skills/bitbucket/` and `bitbucket@some-marketplace` | Delete the loose copy — the plugin updates, the loose copy doesn't. |
| Two marketplaces publish the same plugin | `superpowers@claude-plugins-official` and `superpowers@superpowers-marketplace` | Uninstall one, then remove the orphaned marketplace. |
| Two different skills with overlapping descriptions | an ADHD output-style plugin and an ADHD skill; three PowerPoint paths | Not a duplicate — an overlap. Only the user can say which they use. |

A loose copy usually means the setup predates a switch to marketplace installs. Check the
directory's mtime against when the plugin was installed; older loose copies are leftovers
from an `npx skills add` / manual-copy era, and nothing cleans them up automatically.

Before deleting, confirm the loose copy isn't a local edit:

```bash
diff -r ~/.claude/skills/<name> ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>
```

## "A hook is erroring on everything"

A hook command pointing at a file that no longer exists still spawns a process per matching
tool call. The audit flags missing paths inside hook commands. Also check:

- `${CLAUDE_PLUGIN_ROOT}` references in a plugin whose cached version was pruned;
- a hook installed by a plugin you uninstalled but whose `settings.json` entry stayed;
- Windows paths with the wrong slash direction inside a quoted bash invocation.

## "Too many tools / the model picks the wrong one"

Overlapping MCP servers and skills. The audit lists MCP servers and their source. Common
collisions worth raising:

- more than one browser-automation path (Playwright MCP, a devtools MCP, an in-browser
  extension, plus a Playwright-based skill);
- more than one memory/context layer, each with its own `SessionStart` injection;
- more than one document-generation path for the same file type.

Each is defensible on its own; together they add tool schemas and force the model to choose.
Scope what is project-specific into the project's `.mcp.json` instead of user settings.
