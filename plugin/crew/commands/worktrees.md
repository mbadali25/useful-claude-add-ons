---
description: Where worktrees go (worktrees.root), a read-only survey of them, and owner-confirmed removal
argument-hint: "[list [--days N] | root | path <branch> | remove <path> | hook]"
allowed-tools: Read, Bash
---

crew keeps worktrees in one place outside the repo: `worktrees.root` (repo or
machine layer, the repo wins; null is `~/.claude/crew/worktrees`), laid out as
`<root>/<repo>-<digest>/<name>`. Every answer comes from
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_worktrees.py"`; print its
output as it is. A refused setting (relative, not a string, inside the repo) is
printed as `refused: ...` and is never replaced by the default.

**No argument or `list`** — a read-only survey: one line per worktree of this
repository with where it is (`standard`, `in-repo`, `elsewhere`,
`unreachable`) and whether it is `REMOVABLE` or `keep` with the reasons
(uncommitted or untracked files, commits no remote has, branch not merged into
the default branch, locked, newer than `--days`, 14 by default). A probe that
failed reads `could not tell` and keeps the worktree off the removable list.
`python3 .../crew_worktrees.py list --root . [--days N] [--json]` changes
nothing.

**`root` / `path <branch>`** — print the repo's worktree directory, or where a
worktree for `<branch>` belongs (`/crew:emergency` asks for this rather than
composing a path). Creates nothing.

**`remove <path>`** — the only command here that deletes, and only one path at
a time. List first, show the owner the line for that path, and ask them to
confirm that exact path; only then run
`python3 .../crew_worktrees.py remove <path> --yes --root .`. It runs
`git worktree remove` **without** `--force` and refuses the main checkout, the
checkout it runs in, and anything the survey called `keep`. Never remove a
worktree on your own initiative, never loop over the `REMOVABLE` lines, and
never delete a directory with anything but this command. Worktrees git lists
that this OS cannot reach (for example `/mnt/c/...` seen from Windows) are
`unreachable`: tell the owner to remove them from the OS that made them.

**`hook`** — what crew can and cannot redirect. Claude Code places its own
worktrees (`claude --worktree`, an Agent with `isolation: worktree`) under
`<repo>/.claude/worktrees/` and has no setting for another place. The one
supported redirect is a `WorktreeCreate` hook, which replaces git's creation,
so it is opt-in and crew registers nothing: run
`python3 .../crew_worktrees.py hook-snippet`, show the owner the JSON and let
them put it in `~/.claude/settings.json` themselves; `crew_worktrees.py status`
says whether it is registered and whether its path still exists (a plugin
update moves the path: print the snippet again). `WorktreeRemove` does not fire
for subagent worktrees, so those stay until the owner removes them with
`remove`. Existing worktrees are never moved.
