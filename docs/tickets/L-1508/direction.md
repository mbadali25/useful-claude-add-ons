# L-1508 direction - a tool is run the way it was found: no bare-name subprocess on Windows

Status: direction (owner asked for this ticket 2026-10-04). Written against origin/main `f1cace4a`.

## Why
Two Windows-only bugs landed in one afternoon with one cause. A tool was *found* one way and *run* another:

- **T-0016 (#396), `crew_autocycle._tmux_pane_pid`:** the "is tmux on PATH" check used `shutil.which("tmux")`, which honours PATHEXT and found the test's `tmux.cmd`. The run was a bare `["tmux", ...]`; on native Windows that goes to CreateProcess, which only tries `tmux.exe`. The run raised OSError, the pane pid read 0, and auto-clear refused. Fixed on the branch in `cdb7b508`.
- **T-0017 (#356), `crew_autocycle._git_out`:** the wrap-up veto ran a bare `("git", ...)`. With a failing `git.cmd` ahead of the real `git.exe` on PATH (bash, pwsh and `shutil.which` all pick the `.cmd`), the veto ran a *different* git from every other caller, read a clean tree, and the armed `/clear` went ahead. **Fail-open.** Fixed on the branch in `9a34b335`.

Both were caught only by Windows CI, and only because those PRs' tests happened to stub the tool as a `.cmd`. Everywhere else the same pattern is untested.

The repo already knows the fix: `skills/intune-graph/scripts/auth.py` `_find_az` (around `:170`) explains that CreateProcess ignores PATHEXT and resolves `az` with `shutil.which` first.

## Two harms, not one
1. **Behaviour on a user's Windows machine:** a `.cmd`/`.bat` shim (old Git for Windows `cmd\git.cmd`, wrapper scripts, some package-manager shims) ahead of the `.exe` makes crew judge a different tool from the one the user's shell runs. A guard that reads that tool's answer can fail open, as the wrap-up veto did.
2. **False greens on Windows CI:** crew's tests stub tools as `<name>` plus `<name>.cmd`. A bare-name call skips the stub and runs the real tool, so a must-block test can pass for the wrong reason. #356's veto test passed on Linux and only failed on Windows because of this.

## Facts (origin/main `f1cace4a`)
- 19 bare-name `subprocess.*([...` calls in `plugin/crew/hooks/scripts/*.py`: `git` x15, `ps` x2, `xdotool` x1, `ip` x1. Seven more in skill and plugin scripts outside crew's hooks (`git` x4, `ps`, `tasklist`, plus the `az` precedent). Grep: `grep -rnE 'subprocess\.(run|Popen|check_output|check_call|call)\(\s*[\[(]\s*"[a-zA-Z]'`.
- Several of the git sites are **harness** paths (`HARNESS` in `scripts/check-tooling-pr.py:58-87`): `completion_audit.py`, `crew_ticket.py`, `review_gate.py`, `review_prompt.py`, `verify_record.py`. A harness change lands alone (T-0087), so this splits into a feature PR and a harness PR.
- `ps`, `xdotool` and `ip` are POSIX/WSL tools. Whether every call site is gated to a non-Windows path is **not yet checked** (`crew_autocycle._proc` returns early on `os.name == "nt"` before its `ps` call; the other three were not read).
- `.crew/codemap/` has no entry about this pattern.

## Options
1. **(Recommended) One shared resolver plus a lint test.** Add `resolve_tool(name)` to an existing shared module (`crew_common.py`), returning `shutil.which(name)` or `None`. Every call site runs the resolved path; `None` is "could not tell" at a guard and a clear "not on PATH" error elsewhere, never a silent pass. A test AST-scans the scripts and fails on any `subprocess` call whose first argv element is a string literal, unless the literal is on a short allowlist that names why (e.g. a POSIX-only path gated off Windows, with the gate's line cited).
2. Fix the call sites one by one and add no lint. Cheaper now, but the next new call reintroduces the bug, and today's two would not have been caught by review.
3. Set `shell=True` on Windows. Rejected: changes quoting and injection exposure everywhere, and still resolves differently from `shutil.which`.

## Recommendation
Option 1, delivered in two PRs (see spec): the feature PR (shared resolver, non-harness call sites, lint test, Windows stub tests) first, then a harness-only PR for the five harness files, which the lint test's allowlist names until then.

## Open questions for the owner
**Scope: the 6 call sites outside crew's hook scripts.** Checked one by one (origin/main `f1cace4a`):

| Site | Plugin | Tool | Finding | Suggested handling |
|---|---|---|---|---|
| `plugin/crew/skills/crew-qa-standards/scripts/qa_audit.py:331` | **crew** | git | Bare git; `stamp()` records the audited HEAD | Fix in PR A |
| `.../crew-qa-standards/scripts/qa_audit_env.py:273` | **crew** | git | Bare git | Fix in PR A |
| `.../crew-qa-standards/scripts/qa_doc.py:45` | **crew** | git | Bare git | Fix in PR A |
| `plugin/obsidian-vault/hooks/scripts/obsidian_common.py:857` | obsidian-vault | ps | Inside `_macos_obsidian_running()`, never reached on Windows | Allowlist with that reason; no change |
| `skills/notify/scripts/notifyd.py:264` | notify | tasklist | Windows-only tool that ships as `tasklist.exe`, so a bare name is correct | Allowlist with that reason; no change |
| `skills/repo-docs/scripts/git_changelog.py:71` | repo-docs | git | Bare git; changelog generation only, not a guard | Small follow-up with its own repo-docs bump |

Options:
1. **(Recommended) Crew-only fixes, plus a repo-wide lint.** The three crew-qa-standards scripts ship inside the crew plugin, so they ride PR A's crew bump at no extra cost. The lint scans every plugin and skill. obsidian-vault and notify are allowlisted because they are already correct. repo-docs gets a one-line follow-up ticket.
   - Why: every real fix lands in the plugin that is already being bumped, and the lint stops new cases anywhere.
   - Cost: one tiny extra ticket.
2. **Fix everything in this ticket.** One PR also bumps repo-docs (and touches obsidian-vault/notify only if their allowlisting needs a code comment).
   - Why: closes it in one go.
   - Cost: a multi-plugin PR with more registration places to keep in step, and a bigger review, for a non-guard script.
3. **Crew hooks only, as first written.** Leaves three bare-git calls inside crew's own plugin unfixed.
   - Not recommended: same plugin, same bump, no reason to defer.

**Owner decided 2026-10-04: option 1.** The repo-docs follow-up is L-1509.
## Next
/crew:spec is done (spec.md beside this file). /crew:plan by the implementing session.
