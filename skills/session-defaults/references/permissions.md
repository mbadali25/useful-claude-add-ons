# Permissions

Everything here lives under the `permissions` key in a `settings.json`:

```json
{
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [],
    "ask": [],
    "deny": [],
    "additionalDirectories": []
  }
}
```

Or edit it interactively in a session with `/permissions`.

## How a tool call gets decided

1. **Blocking hooks** run first. A `PreToolUse` hook that exits 2 stops the call before rules are even evaluated — it beats an `allow` rule, and it beats `bypassPermissions`.
2. **`deny`** — if anything matches, blocked. Full stop.
3. **`ask`** — if anything matches, prompt the user even in an otherwise-permissive mode.
4. **Permission mode** — `bypassPermissions` approves; `acceptEdits` approves file operations; others fall through.
5. **`allow`** — if anything matches, approved silently.
6. **No match** → prompt the user (or, in `dontAsk`, deny).

Rules from every scope merge into one combined set. A deny in the user file can't be undone by an allow in a project file. That asymmetry is deliberate.

## Rule syntax

Format is `Tool` or `Tool(specifier)`. Tool names are **case-sensitive** — `bash(...)` matches nothing. Bare `Bash` (or `Bash(*)`) means every command.

### Bash

Glob matching against the whole command string. Wildcards can appear anywhere.

| Pattern | Matches |
|---|---|
| `Bash(npm run build)` | exactly that command |
| `Bash(npm run test *)` | `npm run test`, plus any arguments |
| `Bash(npm *)` | any npm command |
| `Bash(* --version)` | anything ending in `--version` |
| `Bash(git * main)` | `git checkout main`, `git merge main` |
| `Bash(* \| bash)` | anything piped into bash — useful as a deny |

**The space before `*` is load-bearing.** `Bash(ls *)` matches `ls -la` but not `lsof`; `Bash(ls*)` matches both. The trailing `:*` form is equivalent to a space-star (`Bash(ls:*)` = `Bash(ls *)`), and it's what the permission dialog writes when someone picks "Yes, don't ask again" for a command prefix. `:*` is only recognized at the *end* of a pattern — mid-pattern, the colon is a literal character and won't match.

Compound commands are split on `&&`, `||`, `;`, `|`, and newlines, and each part must match on its own. So allowing `Bash(safe-cmd *)` does not permit `safe-cmd && rm -rf /`.

Commands run through a wrapper are matched literally: `sh -c "git status"` is matched as `sh -c "git status"`, not as `git status`.

### Files

`Read(...)`, `Edit(...)`, `Write(...)` take gitignore-style path patterns, matched against the absolute path.

```json
"deny": ["Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)", "Read(~/.ssh/**)"],
"allow": ["Write(src/**)"]
```

`Edit(./src)` matches the directory itself, not the files in it — you want `Edit(./src/**)`.

### Web, MCP, subagents

- `WebFetch(domain:docs.example.com)` — the correct way to restrict network destinations.
- `mcp__servername` — the whole server. `mcp__servername__toolname` — one tool. No parentheses.
- `Agent(Explore)` — allow or block a specific subagent type.

### Reaching outside the working directory

```json
"additionalDirectories": ["../shared-lib"]
```

By default Claude Code can only touch the launch directory and below.

## Permission modes

Set as `permissions.defaultMode`, or switch mid-session with Shift+Tab.

| Mode | Behavior | Good for |
|---|---|---|
| `default` | Prompt on first use of each tool | Getting started; unfamiliar repos |
| `acceptEdits` | Auto-approve file edits and common filesystem commands; still gate other tools | The best everyday default for most people |
| `plan` | Read and explore only, no edits | Scoping work before letting it write |
| `auto` | Auto-approve with a background classifier that checks the action against your request and blocks scope escalation and prompt-injection patterns; your `deny`/`ask` rules still apply on top | Low-friction work when available on the account |
| `dontAsk` | **Denies** anything not explicitly allowed, silently | Headless CI where you want strict predictability |
| `bypassPermissions` | Skips all prompts | Disposable/isolated containers only — never a recommended default |

`dontAsk` is the most misread name in the product. It means "don't ask — deny", not "don't ask — proceed".

## Starter rule sets

Pick the smallest set that solves the stated problem, then widen as they hit friction.

**Stop the approval fatigue** — allow the everyday read-only and build commands:

```json
"allow": [
  "Bash(git status)", "Bash(git diff *)", "Bash(git log *)", "Bash(git stash *)",
  "Bash(npm run lint)", "Bash(npm run test *)", "Bash(npm run build)",
  "Bash(ls *)", "Bash(cat *)", "Bash(rg *)", "Bash(make *)"
]
```

**Protect secrets and history:**

```json
"deny": [
  "Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)", "Read(~/.ssh/**)",
  "Bash(git push --force *)", "Bash(rm -rf *)",
  "Bash(curl *)", "Bash(wget *)", "Bash(* | bash)", "Bash(* | sh)"
]
```

**Force a checkpoint on the irreversible stuff:**

```json
"ask": ["Bash(git push *)", "Bash(gh pr merge *)", "Bash(docker *)", "Bash(terraform apply *)"]
```

Adapt the toolchain to what the inventory actually showed — `pytest`/`ruff`/`uv`, `cargo`, `go test`, `pnpm`, `bundle exec`. Allowlisting npm scripts in a Python repo is a tell that nobody read the project.

## When rules aren't enough

Permission rules match strings. Once the requirement involves *logic* — "block edits to any file under a directory listed in CODEOWNERS", "reject commits without a ticket number", "let it run any command except these forty" — use a `PreToolUse` hook instead. A hook receives the tool input on stdin and can allow, deny, or modify the call; exit code 2 blocks it.

The pattern for "allow all Bash except a few things": put bare `"Bash"` in `allow` and register a `PreToolUse` hook that rejects the specific cases. That inverts the default without giving up control.

See `references/settings-keys.md` for hook wiring, and `https://code.claude.com/docs/en/hooks` for event names and the stdin/stdout contract.

## Debugging a rule that isn't firing

- Tool name capitalized correctly? `Bash`, `Read`, `Edit`, `Write`, `WebFetch`.
- Exact match where a prefix was needed? `Bash(git diff)` won't match `git diff --staged` — you want `Bash(git diff *)`.
- Directory instead of glob? `Edit(./src)` vs `Edit(./src/**)`.
- A wildcard `deny` in a broader scope shadowing the `allow`? Deny always wins; check all four files.
- Running `/doctor` shows resolved settings and any entries that were stripped as invalid.
