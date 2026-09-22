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

Then validate — a settings file that fails to parse is rejected *as a whole* in user/project/local scope, which silently drops every setting in it. Two things break a naive check: a `python3` that resolves on PATH but doesn't run (Windows' Microsoft Store stub prints "Python was not found ..." and exits 9009 without ever touching the file), and a settings file that's simply missing. Both of those look exactly like invalid JSON to a bare `&& echo "valid JSON"` check. Probe the interpreter before trusting it — across every `PATH` entry, not just the first one found under each name, since a stub `python3` earlier on `PATH` shouldn't hide a working one later on it. An empty `PATH` entry is skipped outright rather than treated as the current directory — POSIX path lookup falls back to cwd for an empty segment, but silently trusting whatever executable happens to be sitting in whatever directory this was run from is the less safe reading, so this deliberately doesn't do that. Check the file exists before parsing it, and give the three failure cases distinct messages and distinct exit codes so a script (or a person) can tell them apart. Wrapped in `( ... )` so pasting this into an interactive shell doesn't close it out from under you — `exit` inside `( )` only ends the subshell:

```bash
(
  find_working() {
    local name="$1" dir IFS=:
    for dir in $PATH; do
      [ -n "$dir" ] || continue   # skip empty PATH segments on purpose, rather than
                                  # falling back to the current directory the way POSIX
                                  # path lookup does for an empty segment -- trusting
                                  # whatever's in cwd is the less safe reading
      [ -x "$dir/$name" ] || continue
      if "$dir/$name" -c 'import sys; print(sys.executable)' > /dev/null 2>&1; then
        printf '%s\n' "$dir/$name"
        return 0
      fi
    done
    return 1
  }

  SETTINGS="$HOME/.claude/settings.json"
  PY=""
  for candidate in python3 python py; do
    found=$(find_working "$candidate") && { PY="$found"; break; }
  done

  if [ -z "$PY" ]; then
    echo "No working python interpreter found on PATH (tried python3, python, py across every PATH entry — one may be a Windows Store stub that doesn't run without being installed)." >&2
    exit 3
  fi

  if [ ! -f "$SETTINGS" ]; then
    echo "settings.json not found at $SETTINGS" >&2
    exit 2
  fi

  if "$PY" -m json.tool "$SETTINGS" > /dev/null 2>&1; then
    echo "valid JSON"
  else
    echo "invalid JSON — settings.json failed to parse" >&2
    exit 1
  fi
)
```

Tested against six fixture cases: a Windows-Store-style stub `python3` that exits 9009, no python at all, a *stub `python3` earlier on `PATH` than a working one* (confirms the working interpreter is still found), a real interpreter with a valid file, a real interpreter with an invalid file, and a missing file. All six land on the intended one of the four outcomes (no working interpreter / file not found / invalid JSON / valid JSON), each with its own message and exit code, and the `( )` wrapper was confirmed not to end the calling shell — a sentinel line printed after the subshell in every case, including the `exit 3` and `exit 2` paths. Also tested with a UTF-8 BOM prepended to an otherwise-valid file: **measured** invalid here, rc 1 (`python -m json.tool` calls it out by name, "Unexpected UTF-8 BOM"). The PowerShell validator below was separately **measured** on the same input at rc 0, "valid JSON" — the two disagree, both measured, not guessed. This doc doesn't resolve which side matches Claude Code's own parser, so treat a BOM as something to strip rather than trust either validator's answer on it.

On Windows, PowerShell can validate without Python — but `ConvertFrom-Json` is lenient about things that should fail: it doesn't error on a trailing comma or `//`-style comments the way `python -m json.tool` does. Use `System.Text.Json.JsonDocument`, which rejects trailing commas, comments, and single-quoted keys by default, and check the file's existence and emptiness first — `Get-Content` on a missing path is non-terminating by default, so a bare `try`/`catch` around it never reaches the `catch` block for a missing file. `System.Text.Json` itself isn't guaranteed to be loaded — Windows PowerShell 5.1 runs on .NET Framework, which doesn't carry it — so check for the type before using it rather than letting a missing-type error read as "invalid JSON". Every `Write-Error` below is called with `-ErrorAction Continue` explicitly — under an ambient `$ErrorActionPreference = 'Stop'` (a ambient CI or profile setting this snippet doesn't control), `Write-Error` becomes a terminating error and the `return` right after it would never run, so the caller would get an exception instead of a code. This is written as a function that `return`s a code rather than a script block that calls `exit`: pasted directly into an interactive `pwsh` prompt, `& { exit 5 }` was measured to end the session outright ("still here" never printed) — a plain function using `return` doesn't have that problem, since only `exit` closes the host:

```powershell
function Test-ClaudeSettingsJson {
  param([string]$Path = "$HOME\.claude\settings.json")
  if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "settings.json not found at $Path" -ErrorAction Continue
    return 2
  }
  if (-not ('System.Text.Json.JsonDocument' -as [type])) {
    Write-Error "this PowerShell cannot validate strictly (Windows PowerShell 5.1); use pwsh 7 or the python check" -ErrorAction Continue
    return 3
  }
  $raw = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  if ([string]::IsNullOrWhiteSpace($raw)) {
    Write-Error "settings.json is empty — not valid JSON" -ErrorAction Continue
    return 1
  }
  try {
    [System.Text.Json.JsonDocument]::Parse($raw) | Out-Null
    Write-Host "valid JSON"
    return 0
  } catch {
    Write-Error "invalid JSON: $_" -ErrorAction Continue
    return 1
  }
}
$code = Test-ClaudeSettingsJson
Write-Host "validator exit code: $code"
```

That's the form to paste at an interactive prompt — `$code` holds the result, and the host survives regardless of outcome. It is **not** the form a CI caller can read: `$code` is just a variable, so a build step that runs this and then checks the process's own exit status still sees 0 no matter what `Test-ClaudeSettingsJson` returned (measured: saved as a `.ps1` and run via `pwsh -File`, a missing-file case printed "validator exit code: 2" but the process itself exited 0). For CI or any caller that checks a process exit code rather than console output, save the same function to a file with `exit (Test-ClaudeSettingsJson)` as its last line, and run that file rather than pasting the function — invoking it as a separate process is what lets `exit` end just that process instead of an interactive host:

```powershell
# check-settings.ps1 -- save this file, then run: pwsh -NoProfile -File check-settings.ps1
function Test-ClaudeSettingsJson {
  param([string]$Path = "$HOME\.claude\settings.json")
  if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "settings.json not found at $Path" -ErrorAction Continue
    return 2
  }
  if (-not ('System.Text.Json.JsonDocument' -as [type])) {
    Write-Error "this PowerShell cannot validate strictly (Windows PowerShell 5.1); use pwsh 7 or the python check" -ErrorAction Continue
    return 3
  }
  $raw = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  if ([string]::IsNullOrWhiteSpace($raw)) {
    Write-Error "settings.json is empty — not valid JSON" -ErrorAction Continue
    return 1
  }
  try {
    [System.Text.Json.JsonDocument]::Parse($raw) | Out-Null
    Write-Host "valid JSON"
    return 0
  } catch {
    Write-Error "invalid JSON: $_" -ErrorAction Continue
    return 1
  }
}
exit (Test-ClaudeSettingsJson)
```

Verified on pwsh 7.6.5 (Linux). Windows PowerShell 5.1 is unverified here, and it returns 3 there: `'System.Text.Json.JsonDocument' -as [type]` returns `$null` when a type isn't loaded, .NET Framework's 5.1 never carries `System.Text.Json` by default, so the guard triggers without needing a 5.1 host to confirm the specific message — on 5.1, use the bash/Python check above (from Git Bash or WSL) instead.

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
